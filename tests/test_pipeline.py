"""
SatAI — End-to-end pipeline tests (mock VLM).

Covers the PS-mandated agentic loop without any network/model dependency:
input validation, task classification, registry routing, specialist tools,
visual evidence, GeoJSON, auditable trace, reports and the HTTP API layer.
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image

from vlm.controller import Controller, _controller
from vlm.schemas import ImageInput


# ===========================================================================
# Fixtures
# ===========================================================================
def make_png(w: int = 128, h: int = 128, color=(40, 90, 60)) -> str:
    """Tiny synthetic 'satellite' image as base64 PNG."""
    img = Image.new("RGB", (w, h), color)
    for x in range(0, w, 16):                      # grid texture for change maps
        for y in range(0, h, 16):
            if (x + y) // 16 % 2 == 0:
                img.putpixel((x, y), (90, 120, 70))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def png_b64() -> str:
    return make_png()


@pytest.fixture()
def controller(monkeypatch):
    """Controller with a deterministic mock VLM (no network)."""
    from tests.mock_vlm import MockVLM
    from vlm.tool_registry import registry
    from vlm.tools.caption_tool import CaptionTool
    from vlm.tools.change_tool import ChangeDescTool
    from vlm.tools.ground_tool import GroundTool
    from vlm.tools.numeric_tool import NumericTool
    from vlm.tools.sar_fusion_tool import SARFusionTool
    from vlm.tools.vqa_tool import VQATool

    ctrl = Controller()
    mock = MockVLM()
    monkeypatch.setattr(ctrl, "vlm", mock)
    # registry tools hold their own vlm reference — rebind to the mock
    registry.register(VQATool(mock))
    registry.register(NumericTool(mock))
    registry.register(CaptionTool(mock))
    registry.register(GroundTool(mock))
    registry.register(ChangeDescTool(mock))
    registry.register(SARFusionTool(mock))
    yield ctrl


@pytest.fixture()
def api_client(controller, monkeypatch):
    """httpx AsyncClient wired to the FastAPI app with the mocked controller."""
    import httpx
    from api.main import app
    monkeypatch.setattr("vlm.controller._controller", controller)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def img(data_b64: str, **kw) -> ImageInput:
    return ImageInput(data=data_b64, **kw)


# ===========================================================================
# Validation
# ===========================================================================
class TestValidation:
    async def test_no_images_rejected(self, controller):
        resp = await controller.execute("Describe", [])
        assert resp.status == "rejected"
        assert "no-images" in [i.code for i in resp.validation.issues]

    async def test_single_png_accepted(self, controller, png_b64):
        resp = await controller.execute("Describe this image", [img(png_b64)])
        assert resp.status == "ok"
        meta = resp.validation.images[0]
        assert meta.format == "png"
        assert meta.width == 128 and meta.height == 128
        assert meta.num_bands == 3

    async def test_bitemporal_needs_two(self, controller, png_b64):
        resp = await controller.execute("What changed?", [img(png_b64)],
                                        mode="bitemporal")
        assert resp.status == "rejected"

    async def test_too_many_images(self, controller, png_b64):
        resp = await controller.execute(
            "q", [img(png_b64)] * 5)
        assert resp.status == "rejected"
        assert any(i.code == "too-many" for i in resp.validation.issues)

    async def test_undecodable_image(self, controller):
        bad = base64.b64encode(b"not an image at all").decode()
        resp = await controller.execute("q", [img(bad)])
        assert resp.status == "rejected"

    async def test_pair_compat_note(self, controller):
        a = make_png(128, 128)
        b = make_png(128, 128, (10, 20, 30))
        resp = await controller.execute("What changed?", [img(a), img(b)],
                                        mode="bitemporal")
        assert resp.status == "ok"
        assert resp.validation.pair_compatibility


# ===========================================================================
# Classification (rules)
# ===========================================================================
class TestClassification:
    def test_count_rule(self, controller):
        assert controller._rule_classify("How many ships are visible?", 1) == \
            "single_vqa_count"

    def test_ground_rule(self, controller):
        assert controller._rule_classify("Highlight the water bodies", 1) == \
            "single_ground"

    def test_caption_rule(self, controller):
        assert controller._rule_classify("Describe the land cover", 1) == \
            "single_caption"

    def test_change_rule(self, controller):
        assert controller._rule_classify("What changed between these two dates?", 2) \
            in ("bi_change", "bi_change_vqa")

    def test_compound_rule(self, controller):
        assert controller._rule_classify(
            "What changed between the dates and where is the new road?", 2) == \
            "compound"

    async def test_force_task_endpoint_respected(self, controller, png_b64):
        resp = await controller.execute("anything", [img(png_b64)],
                                        metadata={"force_task": "single_caption"})
        assert resp.task_type == "single_caption"
        assert resp.trace.tools_selected == ["caption"]


# ===========================================================================
# Specialist tools end-to-end (through the agentic loop)
# ===========================================================================
class TestAgenticFlows:
    async def test_single_vqa(self, controller, png_b64):
        resp = await controller.execute("Is this area agricultural?",
                                        [img(png_b64)])
        assert resp.status == "ok"
        assert resp.task_type == "single_vqa"
        assert resp.trace.tools_invoked == ["vqa"]
        assert "agricultural" in resp.response.lower()
        assert 0 < resp.confidence <= 1.0
        # PS: auditable trace
        t = resp.trace
        assert t.classification_reason and t.model and t.timestamps

    async def test_counting(self, controller, png_b64):
        resp = await controller.execute("How many ships are in this image?",
                                        [img(png_b64)])
        assert resp.task_type == "single_vqa_count"
        assert resp.trace.tools_invoked == ["numeric"]
        assert "5" in resp.response

    async def test_grounding(self, controller, png_b64):
        resp = await controller.execute("Highlight the water bodies",
                                        [img(png_b64)])
        assert resp.task_type == "single_ground"
        tool_out = resp.trace.tool_outputs[0]
        assert tool_out.bounding_boxes, "grounding must return boxes"
        for b in tool_out.bounding_boxes:
            assert all(0 <= v <= 1000 for v in b["bbox"])   # normalised grid
        # GeoJSON output (PS: spatial output)
        assert resp.geojson and resp.geojson["type"] == "FeatureCollection"
        feat = resp.geojson["features"][0]
        assert feat["geometry"]["type"] == "Polygon"
        assert feat["properties"]["coordinate_system"]
        # visual evidence (PS: visual results)
        kinds = [e.kind for e in resp.visual_evidence]
        assert "annotated_boxes" in kinds

    async def test_change_analysis(self, controller):
        a = make_png(128, 128, (30, 80, 50))
        b = make_png(128, 128, (120, 120, 120))          # visually different
        resp = await controller.execute(
            "What changed between these two dates?", [img(a), img(b)],
            mode="bitemporal")
        assert resp.status == "ok"
        assert resp.task_type in ("bi_change", "bi_change_vqa")
        assert resp.trace.tools_invoked == ["change_desc"]
        kinds = [e.kind for e in resp.visual_evidence]
        assert "change_map" in kinds       # optional spatial change map
        assert "side_by_side" in kinds
        cm = next(e for e in resp.visual_evidence if e.kind == "change_map")
        assert cm.stats["changed_pixels_pct"] >= 0

    async def test_cross_modal(self, controller, png_b64):
        sar = make_png(128, 128, (70, 70, 70))
        resp = await controller.execute(
            "Identify built-up areas and water bodies",
            [img(png_b64, modality="optical"), img(sar, modality="sar")],
            mode="crossmodal")
        assert resp.task_type == "cross_modal"
        assert resp.trace.tools_selected == ["sar_fusion", "ground"]
        kinds = [e.kind for e in resp.visual_evidence]
        assert "side_by_side" in kinds
        # classification via modality detection works without mode hint too
        resp2 = await controller.execute(
            "Identify built-up areas and water",
            [img(png_b64, modality="optical"), img(sar, modality="sar")])
        assert resp2.task_type == "cross_modal"

    async def test_compound_two_images(self, controller):
        a = make_png(128, 128)
        b = make_png(128, 128, (200, 200, 200))
        resp = await controller.execute(
            "What changed between the dates and describe the new buildings?",
            [img(a), img(b)])
        assert resp.task_type == "compound"
        assert set(resp.trace.tools_invoked) >= {"change_desc", "vqa", "caption"}


# ===========================================================================
# Evidence + reports
# ===========================================================================
class TestEvidenceAndReports:
    async def test_input_view_evidence_present(self, controller, png_b64):
        resp = await controller.execute("Describe", [img(png_b64)])
        kinds = [e.kind for e in resp.visual_evidence]
        assert "input_view" in kinds

    async def test_report_html_and_json(self, api_client, png_b64):
        r = await api_client.post("/vlm/query", json={
            "query": "Describe this image",
            "images": [{"data": png_b64}],
            "mode": "auto"})
        assert r.status_code == 200
        body = r.json()
        qid = body["query_id"]

        rj = await api_client.get(f"/vlm/report/{qid}?format=json")
        assert rj.status_code == 200
        doc = rj.json()
        assert doc["query_id"] == qid or doc.get("id") == qid

        rh = await api_client.get(f"/vlm/report/{qid}")
        assert rh.status_code == 200
        assert "text/html" in rh.headers["content-type"]

        rd = await api_client.get(f"/vlm/report/{qid}/download?format=json")
        assert "attachment" in rd.headers.get("content-disposition", "")

    async def test_history(self, api_client, png_b64):
        await api_client.post("/vlm/query", json={
            "query": "Highlight the water",
            "images": [{"data": png_b64}]})
        r = await api_client.get("/vlm/history")
        assert r.status_code == 200
        queries = r.json()["queries"]
        assert queries and queries[0]["task_type"] == "single_ground"

    async def test_status_lists_registry(self, api_client):
        r = await api_client.get("/vlm/status")
        assert r.status_code == 200
        body = r.json()
        ids = {t["id"] for t in body["tools"]}
        assert {"vqa", "caption", "ground", "change_desc", "sar_fusion",
                "numeric"} <= ids
        assert body["limits"]["max_images"] == 4

    async def test_validate_endpoint(self, api_client, png_b64):
        r = await api_client.post("/vlm/validate", json={
            "query": "x", "images": [{"data": png_b64}], "mode": "single"})
        assert r.status_code == 200
        assert r.json()["accepted"] is True

    async def test_change_endpoint_requires_pair(self, api_client, png_b64):
        r = await api_client.post("/vlm/change", json={
            "query": "what changed", "images": [{"data": png_b64}]})
        assert r.status_code == 400


# ===========================================================================
# Eval helpers (used by benchmark harness)
# ===========================================================================
class TestEvalHelpers:
    def test_answers_match(self):
        from vlm.eval.common import answers_match
        assert answers_match("The Urban", "urban")
        assert answers_match("2", "2.0")
        assert answers_match("There are 12 cars.", "12")
        assert not answers_match("yes", "no")

    def test_box_iou(self):
        from vlm.eval.common import box_iou
        assert abs(box_iou([0, 0, 10, 10], [5, 5, 15, 15]) - 25 / 175) < 1e-9
        assert box_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0

    def test_caption_metrics_sanity(self):
        from vlm.eval.eval_metrics import caption_report
        same = "a satellite image shows urban buildings and a river"
        rep = caption_report([same], [[same]])
        assert rep["BLEU-4"] == 1.0 and rep["CIDEr"] == 1.0
        rep2 = caption_report(["the cat sat"], [["totally different words"]])
        assert rep2["BLEU"] == 0.0

    def test_extract_pred_boxes_scales_grid(self, png_b64):
        from vlm.eval.common import extract_pred_boxes
        from vlm.schemas import ExecutionTrace, ToolOutput

        # fake response-shaped object with a 0-1000-grid ground tool output
        class O:
            validation = None
            geojson = None
            trace = ExecutionTrace(tools_invoked=["ground"], tool_outputs=[
                ToolOutput(tool_id="ground", bounding_boxes=[
                    {"label": "water", "bbox": [0, 0, 500, 500],
                     "confidence": 0.9}])])
        boxes = extract_pred_boxes(O())
        assert boxes == [[0, 0, 500, 500]]   # no validation dims → passthrough
