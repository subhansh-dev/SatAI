"""
SatAI — Capability-aware refusal gate (GPT-brainstorm feature #3).

A satellite-analyst assistant must know when the evidence is insufficient.
Instead of manufacturing an answer, the gate refuses infeasible tasks
*before* execution with a specific repair instruction, and surfaces
disagreement / parse warnings *after* execution.

Wiring (see controller.execute):
  - pre_check()  -> right after task classification; a refusal returns a
                    `rejected` VLMResponse carrying the repair advice.
  - post_check() -> right after confidence merging; warnings join the
                    trace notes (visible in the report + trace drawer).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .schemas import ToolOutput, ValidationReport
from .tool_registry import TASK_LABELS

# Spectral band-math needs real multispectral rasters, never 8-bit previews.
SPECTRAL_FORMATS = ("tiff", "geotiff")
MIN_SPECTRAL_BANDS = 4

# GPT constraint: our merged score is a heuristic reliability signal built
# from tool self-reports — it must never be presented as a calibrated
# probability, and 3 samples from one model are not 3 independent experts.
HEURISTIC_CONF_NOTE = (
    "Confidence is a heuristic reliability score from weighted tool "
    "self-reports (single-model samples, uncalibrated) — not a calibrated "
    "probability. Treat low values as 'verify before acting'."
)


def pre_check(task_type: str, validation: ValidationReport,
              metadata: Optional[dict] = None) -> Tuple[bool, Optional[str]]:
    """Answer gate before any tool runs.

    Returns (allowed, repair_message). When allowed is False the caller
    must refuse with repair_message instead of executing the workflow.
    """
    if task_type not in TASK_LABELS:
        return False, (
            f"Unsupported request '{task_type}'. I handle single-image "
            "analysis (VQA, counting, captioning, grounding, spectral "
            "indices), bi-temporal change, optical+SAR fusion, and "
            "multi-part combinations of those. Rephrase into one of these.")

    n = len(validation.images)

    if task_type in ("bi_change", "bi_change_vqa", "compound") and n < 2:
        return False, (
            "Change analysis needs two images of the same area from "
            "different dates. Re-send with [before, after] attached, or "
            "switch to single-image mode for one-image questions.")

    if task_type == "cross_modal":
        mods = [m.detected_modality for m in validation.images]
        if not ("optical" in mods and "sar" in mods):
            return False, (
                "Cross-modal fusion needs one optical + one SAR image of "
                "the same area "
                f"(detected: {', '.join(mods) or 'unknown'}). Re-upload the "
                "pair with modalities tagged explicitly "
                "(modality='optical' / 'sar').")

    if task_type == "spectral_index" and n >= 1:
        meta = validation.images[0]
        if (meta.format not in SPECTRAL_FORMATS
                or (meta.num_bands and meta.num_bands < MIN_SPECTRAL_BANDS)):
            return False, (
                "Spectral indices (NDVI/NDWI/NDBI) need the original "
                "multispectral GeoTIFF/TIFF with 4+ bands including NIR "
                f"(got: {meta.format}, {meta.num_bands} band(s)). "
                "Re-upload the GeoTIFF — PNG/JPEG previews carry no "
                "spectral bands for band-math.")

    return True, None


def post_check(outputs: List[ToolOutput]) -> List[str]:
    """Disagreement / failure warnings after tools run (advisory only)."""
    warnings: List[str] = []
    for o in outputs or []:
        md = o.metadata or {}
        if (o.tool_id == "numeric" and md.get("parse_ok")
                and md.get("agreement", 1.0) < 0.5):
            warnings.append(
                "Counting disagreement across self-consistency samples "
                f"(agreement {md.get('agreement')}) — treat the reported "
                "number as uncertain and verify visually.")
        if o.tool_id == "ground" and md.get("parsed_cleanly") is False:
            warnings.append(
                "Grounding model output could not be parsed into boxes — "
                "reported regions are unverified; rephrase the referring "
                "expression with a more distinctive description.")
        if o.confidence_source == "error":
            warnings.append(
                f"Step '{o.tool_id}' failed at the model backend — its "
                "section is omitted, not estimated.")
    if outputs and not any(o.text for o in outputs):
        warnings.append(
            "No specialist produced an answer — narrow the question to one "
            "image region or check that the upload is readable imagery.")
    return warnings
