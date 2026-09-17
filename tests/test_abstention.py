"""
SatAI — Capability-gate tests (GPT-brainstorm feature #3).

The gate must refuse infeasible tasks with repair advice instead of
manufacturing an answer, warn on disagreement/failure, and label
confidence as heuristic. Uses the deterministic mock VLM (no network).
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from vlm.capability_gate import HEURISTIC_CONF_NOTE, post_check, pre_check
from vlm.controller import Controller
from vlm.input_validator import validate_inputs
from vlm.schemas import ImageInput, ImageMeta, ToolOutput, ValidationReport


# ===========================================================================
# Fixtures (mirrors test_pipeline.py)
# ===========================================================================
def make_png(w: int = 128, h: int = 128, color=(40, 90, 60)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def img(data_b64: str, **kw) -> ImageInput:
    return ImageInput(data=data_b64, **kw)


@pytest.fixture(scope="module")
def png_b64() -> str:
    return make_png()


@pytest.fixture()
def controller(monkeypatch):
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
    registry.register(VQATool(mock))
    registry.register(NumericTool(mock))
    registry.register(CaptionTool(mock))
    registry.register(GroundTool(mock))
    registry.register(ChangeDescTool(mock))
    registry.register(SARFusionTool(mock))
    yield ctrl


# ===========================================================================
# Pre-check refusals (controller level — repair advice, not made-up answers)
# ===========================================================================
class TestPreCheckRefusals:
    async def test_spectral_png_refused_with_geotiff_repair(
            self, controller, png_b64):
        resp = await controller.execute(
            "Compute NDVI for this scene", [img(png_b64)],
            metadata={"force_task": "spectral_index"})
        assert resp.status == "rejected"
        assert resp.trace.classification_reason == "capability gate refusal"
        assert "GeoTIFF" in resp.response
        assert "NIR" in resp.response
        assert resp.report_url is not None  # refusal is still auditable

    async def test_crossmodal_same_modality_refused(
            self, controller, png_b64):
        resp = await controller.execute(
            "Fuse the pair", [img(png_b64), img(png_b64)],
            metadata={"force_task": "cross_modal"})
        assert resp.status == "rejected"
        assert "one optical + one SAR" in resp.response
        assert "modality=" in resp.response  # tells analyst how to repair

    async def test_valid_crossmodal_still_passes(
            self, controller, png_b64):
        sar = make_png(color=(70, 70, 70))
        resp = await controller.execute(
            "Identify built-up areas and water",
            [img(png_b64, modality="optical"), img(sar, modality="sar")],
            mode="crossmodal")
        assert resp.status == "ok"
        assert resp.task_type == "cross_modal"


# ===========================================================================
# Pre-check unit tests (branches unreachable via the mock classifier)
# ===========================================================================
class TestPreCheckUnits:
    def test_unknown_task_refused(self, png_b64):
        validation = validate_inputs([img(png_b64)], "auto", {})
        ok, repair = pre_check("teleport", validation)
        assert not ok and "Unsupported" in (repair or "")

    def test_pair_task_needs_two(self, png_b64):
        validation = validate_inputs([img(png_b64)], "auto", {})
        ok, repair = pre_check("bi_change", validation)
        assert not ok and "two images" in (repair or "")

    def test_spectral_geotiff_allowed(self):
        meta = ImageMeta(index=0, format="geotiff", width=64, height=64,
                         num_bands=6)
        validation = ValidationReport(ok=True, accepted=True, images=[meta])
        ok, repair = pre_check("spectral_index", validation)
        assert ok and repair is None


# ===========================================================================
# Post-check warnings + honesty note
# ===========================================================================
class TestPostCheck:
    def test_numeric_disagreement_warns(self):
        outs = [ToolOutput(tool_id="numeric", text="ANSWER: 5",
                           confidence=0.5, confidence_source="test",
                           metadata={"parse_ok": True, "agreement": 0.34})]
        notes = post_check(outs)
        assert any("uncertain" in w for w in notes)

    def test_ground_unparsed_warns(self):
        outs = [ToolOutput(tool_id="ground", text="No region found.",
                           confidence=0.3,
                           metadata={"parsed_cleanly": False})]
        notes = post_check(outs)
        assert any("unverified" in w for w in notes)

    def test_error_step_marked_omitted(self):
        outs = [ToolOutput(tool_id="vqa", confidence=0.0,
                           confidence_source="error")]
        notes = post_check(outs)
        assert any("omitted, not estimated" in w for w in notes)

    def test_total_silence_warns(self):
        outs = [ToolOutput(tool_id="vqa", text=None, confidence=0.0)]
        notes = post_check(outs)
        assert any("narrow the question" in w for w in notes)

    async def test_ok_response_carries_heuristic_note(
            self, controller, png_b64):
        resp = await controller.execute(
            "Describe this image", [img(png_b64)])
        assert resp.status == "ok"
        assert HEURISTIC_CONF_NOTE in (resp.trace.notes or [])
