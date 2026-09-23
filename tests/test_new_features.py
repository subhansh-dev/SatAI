"""
SatAI — Tests for the 2026-09 feature batch:
- area/quantity task routing + QuantityTool (band-math hectares, VLM fallback)
- blind-test hallucination gate (imageless control, flag + confidence ding)
- evidence-citation verification ([EV-n] footer + invalid-id warning)
- multilingual query support (script detection, language note)
Uses the deterministic mock VLM (no network).
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from vlm.controller import Controller, _blind_verdict
from vlm.lang import is_non_latin
from vlm.schemas import ImageInput, VisualEvidenceItem
from vlm.tool_registry import TASK_LABELS, TASK_TOOLS, registry, select_model


# ===========================================================================
# Fixtures
# ===========================================================================
def make_png(w: int = 128, h: int = 128, color=(40, 90, 60)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def geotiff_b64(w: int = 32, h: int = 32, bands: int = 4) -> str:
    """Synthetic multispectral GeoTIFF with 10 m pixel scale (hectares math)."""
    import numpy as np
    import tifffile
    rng = np.random.default_rng(7)
    data = rng.integers(0, 4000, (h, w, bands), dtype=np.uint16)
    geokeys = [1, 1, 0, 2,
               2048, 0, 1, 4326,
               3072, 0, 1, 32633]
    buf = io.BytesIO()
    tifffile.imwrite(
        buf, data, photometric="minisblack", planarconfig="contig",
        resolution=(10.0, 10.0), metadata=None,
        extratags=[
            (33550, 12, 3, (10.0, 10.0, 0.0), False),
            (33922, 12, 6, (0.0, 0.0, 0.0, 442000.0, 4420000.0, 0.0), False),
            (34735, 3, len(geokeys), geokeys, False),
        ])
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def png_b64() -> str:
    return make_png()


@pytest.fixture()
def controller(monkeypatch):
    from tests.mock_vlm import MockVLM
    from vlm.tool_registry import registry as reg
    from vlm.tools.caption_tool import CaptionTool
    from vlm.tools.change_tool import ChangeDescTool
    from vlm.tools.ground_tool import GroundTool
    from vlm.tools.numeric_tool import NumericTool
    from vlm.tools.quantity_tool import QuantityTool
    from vlm.tools.sar_fusion_tool import SARFusionTool
    from vlm.tools.vqa_tool import VQATool

    ctrl = Controller()
    mock = MockVLM()
    monkeypatch.setattr(ctrl, "vlm", mock)
    # registry tools hold their own vlm reference — rebind to the mock
    reg.register(VQATool(mock))
    reg.register(NumericTool(mock))
    reg.register(CaptionTool(mock))
    reg.register(GroundTool(mock))
    reg.register(ChangeDescTool(mock))
    reg.register(SARFusionTool(mock))
    reg.register(QuantityTool(mock))     # VLM fallback path must hit the mock
    yield ctrl


def img(data_b64: str, **kw) -> ImageInput:
    return ImageInput(data=data_b64, **kw)


# ===========================================================================
# Area classification rules
# ===========================================================================
class TestAreaClassification:
    def test_hectares_question_routes_to_area(self, controller):
        assert controller._rule_classify(
            "What is the area of the water body in hectares?", 1) == \
            "single_vqa_area"

    def test_how_much_area_routes_to_area(self, controller):
        assert controller._rule_classify(
            "How much area of the scene is flooded?", 1) == "single_vqa_area"

    def test_percentage_of_scene_routes_to_area(self, controller):
        assert controller._rule_classify(
            "What percentage of the scene is vegetation?", 1) == \
            "single_vqa_area"

    def test_devanagari_area_routes_to_area(self, controller):
        assert controller._rule_classify(
            "इस दृश्य में क्षेत्रफल कितना है?", 1) == "single_vqa_area"

    def test_count_rule_still_wins(self, controller):
        assert controller._rule_classify(
            "How many ships are visible?", 1) == "single_vqa_count"

    def test_bare_areas_noun_is_not_area_task(self, controller):
        # "built-up areas" must never trigger the quantifier rule
        assert controller._rule_classify(
            "Identify built-up areas and water bodies", 1) == "single_vqa"

    def test_this_area_agricultural_still_vqa(self, controller):
        assert controller._rule_classify(
            "Is this area agricultural?", 1) == "single_vqa"

    def test_two_image_change_with_area_stays_compound(self, controller):
        assert controller._rule_classify(
            "What changed between the dates and how much area changed?",
            2) == "compound"


class TestAreaRegistry:
    def test_task_maps_to_quantity_tool(self):
        assert TASK_TOOLS["single_vqa_area"] == ["quantity"]
        assert "single_vqa_area" in TASK_LABELS

    def test_quantity_registered(self, controller):
        assert "quantity" in registry.tool_ids()

    def test_model_registry_general_scope(self):
        hint, _ = select_model("single_vqa_area", "cloud")
        assert hint == "flagship"


# ===========================================================================
# QuantityTool — algorithmic band-math path
# ===========================================================================
class TestQuantityAlgorithmic:
    @pytest.fixture()
    def tool(self):
        from tests.mock_vlm import MockVLM
        from vlm.tools.quantity_tool import QuantityTool
        return QuantityTool(MockVLM())

    async def test_water_area_in_hectares(self, tool):
        raw = base64.b64decode(geotiff_b64())
        out = await tool.execute(
            query="How much area of the scene is water?",
            images=["unused"],
            metadata={"_rasters": [{"raw": raw,
                                    "geo": {"ground_sample_dist_m": 10.0}}]})
        assert out["confidence_source"] == "algorithmic_deterministic"
        assert out["confidence"] == pytest.approx(0.93)
        assert "ANSWER:" in out["text"]
        assert "hectare" in out["text"].lower()
        assert out["metadata"]["method"] == "band_math"
        assert out["metadata"]["primary_index"] == "ndwi"
        assert out["metadata"]["spectral"]["preview_b64"]
        # 32x32 @ 10 m/px = 10.24 ha scene — reported area must fit inside
        ha = out["metadata"]["quantity"]["ndwi"]["area_ha"]
        assert ha is not None and 0.0 <= ha <= 10.24

    async def test_vegetation_class_detected(self, tool):
        raw = base64.b64decode(geotiff_b64())
        out = await tool.execute(
            query="What area is covered by vegetation?",
            images=["unused"],
            metadata={"_rasters": [{"raw": raw,
                                    "geo": {"ground_sample_dist_m": 10.0}}]})
        assert out["metadata"]["primary_index"] == "ndvi"

    async def test_unnamed_class_reports_all_three(self, tool):
        raw = base64.b64decode(geotiff_b64())
        out = await tool.execute(
            query="What is the total area breakdown of this scene?",
            images=["unused"],
            metadata={"_rasters": [{"raw": raw,
                                    "geo": {"ground_sample_dist_m": 10.0}}]})
        q = out["metadata"]["quantity"]
        # 4-band (B,G,R,NIR) raster: NDWI + NDVI computable, NDBI needs a
        # SWIR band and is honestly skipped rather than faked.
        assert set(q) == {"ndwi", "ndvi"}
        low = out["text"].lower()
        assert "water" in low and "vegetation" in low
        assert out["metadata"]["primary_index"] == "ndwi"

    async def test_no_gsd_gives_percent_only(self, tool):
        raw = base64.b64decode(geotiff_b64())
        out = await tool.execute(
            query="How much area of the scene is water?",
            images=["unused"],
            metadata={"_rasters": [{"raw": raw, "geo": {}}]})
        assert "% of the scene" in out["text"]
        assert "hectare" not in out["text"].lower()

    async def test_vlm_fallback_without_raster(self, tool, png_b64):
        out = await tool.execute(
            query="How much area is flooded here?",
            images=[png_b64], metadata={})
        assert out["metadata"]["method"] == "vlm_scale_estimate"
        assert out["metadata"]["fallback"] is True
        assert "ANSWER: 5" in out["text"]          # mock counting specialist
        assert out["confidence_source"] in (
            "parsed_answer+model_self_report", "model_self_report")


# ===========================================================================
# Area task end-to-end through the agentic loop
# ===========================================================================
class TestAreaEndToEnd:
    async def test_png_area_uses_vlm_fallback_not_refused(
            self, controller, png_b64):
        resp = await controller.execute(
            "How much area of the scene is water?", [img(png_b64)],
            metadata={"force_task": "single_vqa_area"})
        assert resp.status == "ok"                 # never gate-refused
        assert resp.task_type == "single_vqa_area"
        assert resp.trace.tools_invoked == ["quantity"]
        assert "ANSWER:" in resp.response
        md = resp.trace.tool_outputs[0].metadata
        assert md["method"] == "vlm_scale_estimate"
        assert md["fallback"] is True
        assert md["band_math_errors"]           # reason band-math was skipped

    async def test_geotiff_area_is_measured_bandmath(self, controller):
        resp = await controller.execute(
            "How much area of the scene is water?", [img(geotiff_b64())],
            metadata={"force_task": "single_vqa_area"})
        assert resp.status == "ok"
        assert "hectare" in resp.response.lower()
        assert resp.trace.tool_outputs[0].confidence_source == \
            "algorithmic_deterministic"
        kinds = [e.kind for e in resp.visual_evidence]
        assert "index_map" in kinds                # colour-ramped evidence

    async def test_rule_classification_e2e(self, controller, png_b64):
        resp = await controller.execute(
            "What is the area of the water body in hectares?", [img(png_b64)])
        assert resp.status == "ok"
        assert resp.task_type == "single_vqa_area"
        assert resp.trace.tools_invoked == ["quantity"]


# ===========================================================================
# Blind-test hallucination gate
# ===========================================================================
class TestBlindVerdict:
    def test_exact_reproduction_flags(self):
        assert _blind_verdict("5", "5") == "flag"

    def test_numeric_inside_primary_flags(self):
        assert _blind_verdict("There are 5 ships near the pier.",
                              "5") == "flag"

    def test_short_phrase_reproduction_flags(self):
        assert _blind_verdict(
            "The scene is predominantly agricultural with a water channel.",
            "agricultural") == "flag"

    def test_honest_refusal_passes(self):
        assert _blind_verdict(
            "5 ships visible",
            "I cannot tell without seeing the image.") == "refusal"

    def test_different_answer_passes(self):
        assert _blind_verdict("urban scene with roads and buildings",
                              "agricultural land") == "pass"

    def test_empty_blind_passes(self):
        assert _blind_verdict("something", "") == "pass"


class TestBlindGateEndToEnd:
    async def test_default_run_passes_with_mock_control(
            self, controller, png_b64):
        resp = await controller.execute(
            "How many ships are in this image?", [img(png_b64)])
        assert resp.status == "ok"
        assert any("Blind-test passed" in n for n in resp.trace.notes)
        assert resp.confidence > 0.85              # no penalty on a pass
        md = resp.trace.tool_outputs[0].metadata
        assert md["blind_test"]["flagged"] is False

    async def test_reproducible_answer_is_flagged_and_dinged(
            self, controller, monkeypatch, png_b64):
        async def fake_probe(query: str) -> str:
            return "5"                             # blind control reproduces it
        monkeypatch.setattr(controller, "_run_blind_probe", fake_probe)
        resp = await controller.execute(
            "How many ships are in this image?", [img(png_b64)])
        assert resp.status == "ok"
        assert any("Blind-test FLAG" in n for n in resp.trace.notes)
        assert resp.confidence < 0.85              # 0.897 * 0.8 ≈ 0.72
        md = resp.trace.tool_outputs[0].metadata
        assert md["blind_test"]["flagged"] is True
        assert md["blind_test"]["blind_answer"] == "5"

    async def test_opt_out_skips_probe(self, controller, monkeypatch,
                                       png_b64):
        async def boom(query: str) -> str:
            raise AssertionError("blind probe must not run when disabled")
        monkeypatch.setattr(controller, "_run_blind_probe", boom)
        resp = await controller.execute(
            "How many ships are in this image?", [img(png_b64)],
            metadata={"blind_test": False})
        assert resp.status == "ok"
        assert not any("Blind-test" in n for n in resp.trace.notes)

    async def test_caption_task_has_no_probe(self, controller, monkeypatch,
                                             png_b64):
        async def boom(query: str) -> str:
            raise AssertionError("caption is not a blind-gate target")
        monkeypatch.setattr(controller, "_run_blind_probe", boom)
        resp = await controller.execute("Describe this image", [img(png_b64)])
        assert resp.status == "ok"
        assert not any("Blind-test" in n for n in resp.trace.notes)


# ===========================================================================
# Evidence-citation verification
# ===========================================================================
def _ev(title: str) -> VisualEvidenceItem:
    return VisualEvidenceItem(kind="input_view", title=title,
                              image_base64="")


class TestEvidenceCitations:
    def test_uncited_answer_gets_ev_footer(self):
        notes: list = []
        out = Controller._link_evidence("The answer is clear.",
                                        [_ev("Input 1")], notes)
        assert out.endswith("**Evidence:** [EV-1] Input 1")
        assert notes == []

    def test_valid_citation_left_untouched(self):
        notes: list = []
        src = "Water detected [EV-2] near the north bank."
        out = Controller._link_evidence(src, [_ev("A"), _ev("B")], notes)
        assert out == src
        assert notes == []

    def test_invalid_citation_warned(self):
        notes: list = []
        src = "See EV-9 for proof."
        out = Controller._link_evidence(src, [_ev("A")], notes)
        assert out == src                          # model prose preserved
        assert any("EV-9" in n and "do not exist" in n for n in notes)

    def test_no_evidence_no_footer(self):
        notes: list = []
        out = Controller._link_evidence("Plain answer.", [], notes)
        assert out == "Plain answer."

    async def test_footer_appears_in_live_response(self, controller, png_b64):
        resp = await controller.execute("Describe this image", [img(png_b64)])
        assert "**Evidence:**" in resp.response
        assert "[EV-1]" in resp.response


# ===========================================================================
# Multilingual queries
# ===========================================================================
class TestMultilingual:
    def test_hindi_detected(self):
        assert is_non_latin("इस छवि में क्या है?")

    def test_gujarati_detected(self):
        assert is_non_latin("આ છબીમાં શું છે?")

    def test_english_not_flagged(self):
        assert not is_non_latin("Describe the land cover")

    def test_empty_safe(self):
        assert not is_non_latin("")

    async def test_hindi_query_gets_language_note(self, controller, png_b64):
        resp = await controller.execute(
            "इस छवि में कितने जहाज़ हैं?", [img(png_b64)])
        assert resp.status == "ok"
        assert any("Non-Latin script detected" in n for n in resp.trace.notes)

    async def test_hindi_area_query_routes_and_answers(
            self, controller, png_b64):
        resp = await controller.execute(
            "इस दृश्य में क्षेत्रफल कितना है?", [img(png_b64)])
        assert resp.status == "ok"
        assert resp.task_type == "single_vqa_area"
        assert resp.trace.tools_invoked == ["quantity"]
