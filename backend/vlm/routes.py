"""
SatAI — VLM API Routes
Agentic endpoints + direct-tool endpoints + samples + history + reports.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File

from core import config
from .controller import Controller, get_controller
from .input_validator import validate_inputs
from .report import render_html_report, render_json_report
from .schemas import (
    CaptionRequest, ChangeRequest, GroundRequest, SARFusionRequest,
    VLMQuery, VLMStatus,
)
from .image_utils import decode_b64, sniff_format, load_pil, detect_modality

logger = logging.getLogger("satai.api")
router = APIRouter(prefix="/vlm", tags=["VLM"])

MAX_UPLOAD = config.MAX_IMAGE_BYTES


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
@router.get("/status")
async def vlm_status() -> dict:
    ctrl = await get_controller()
    health = await ctrl.vlm.health_check()
    return VLMStatus(
        mode=ctrl.vlm.mode,
        model=ctrl.vlm.active_model,
        available=health and ctrl.vlm.configured,
        model_detail=("LoRA adapter: " + ctrl.vlm.lora_adapter
                      if ctrl.vlm.mode == "local" and ctrl.vlm.lora_adapter
                      else None),
        tools=registry_list(),
        limits={
            "max_images": config.MAX_IMAGES_PER_QUERY,
            "max_image_mb": config.MAX_IMAGE_BYTES // (1024 * 1024),
            "max_total_mb": config.MAX_TOTAL_PAYLOAD_BYTES // (1024 * 1024),
            "formats": ["GeoTIFF", "TIFF", "PNG", "JPEG"],
        },
    ).model_dump()


def registry_list() -> list:
    from .tool_registry import registry as reg
    return reg.list_tools()


# ---------------------------------------------------------------------------
# Main agentic endpoint
# ---------------------------------------------------------------------------
@router.post("/query")
async def vlm_query(query: VLMQuery) -> dict:
    if not query.images and not query.query.strip():
        raise HTTPException(400, "Empty query and no images")
    payload_bytes = sum(len(i.data) for i in query.images)
    if payload_bytes > config.MAX_TOTAL_PAYLOAD_BYTES * 1.4:  # b64 overhead ~4/3
        raise HTTPException(413, "Request payload too large")
    ctrl = await get_controller()
    result = await ctrl.execute(
        query=query.query, images=query.images,
        mode=query.mode.value, metadata=query.metadata)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Direct specialist-tool endpoints (benchmark / integration use)
# ---------------------------------------------------------------------------
@router.post("/caption")
async def caption(req: CaptionRequest) -> dict:
    ctrl = await get_controller()
    out = await ctrl.execute(query=req.metadata.get("query", "Describe this image."),
                             images=req.images, mode="auto",
                             metadata={**req.metadata, "force_task": "single_caption"})
    return out


@router.post("/ground")
async def ground(req: GroundRequest) -> dict:
    ctrl = await get_controller()
    out = await ctrl.execute(query=req.query, images=req.images, mode="single",
                             metadata={**req.metadata,
                                       "output_format": req.output_format,
                                       "force_task": "single_ground"})
    return out


@router.post("/change")
async def change(req: ChangeRequest) -> dict:
    if len(req.images) != 2:
        raise HTTPException(400, "Change analysis needs exactly 2 images")
    ctrl = await get_controller()
    out = await ctrl.execute(query=req.query, images=req.images,
                             mode="bitemporal", metadata=req.metadata)
    return out


@router.post("/sar-fusion")
async def sar_fusion(req: SARFusionRequest) -> dict:
    if len(req.images) != 2:
        raise HTTPException(400, "SAR fusion needs exactly 2 images")
    ctrl = await get_controller()
    out = await ctrl.execute(query=req.query, images=req.images,
                             mode="crossmodal", metadata=req.metadata)
    return out


# ---------------------------------------------------------------------------
# Upload + validation preview
# ---------------------------------------------------------------------------
@router.post("/upload")
async def upload_image(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"Image too large (max {MAX_UPLOAD // (1024*1024)} MB)")
    try:
        b64 = base64.b64encode(data).decode()
        pil = load_pil(data)
    except Exception as e:
        raise HTTPException(400, f"Could not decode image: {e}")
    fmt = sniff_format(data)
    modality, reason = detect_modality(data, name=file.filename, pil_image=pil)
    return {
        "base64": b64, "filename": file.filename,
        "size_bytes": len(data), "format": fmt,
        "width": pil.size[0], "height": pil.size[1],
        "bands": len(pil.getbands()),
        "detected_modality": modality, "modality_reason": reason,
    }


@router.post("/validate")
async def validate_only(query: VLMQuery) -> dict:
    """Dry-run of the compatibility checker (no model call)."""
    report = validate_inputs(query.images, query.mode.value, query.metadata)
    return report.model_dump()


# ---------------------------------------------------------------------------
# Samples (bundled demo imagery)
# ---------------------------------------------------------------------------
@router.get("/samples")
async def list_samples() -> dict:
    import json as _json
    idx = config.SAMPLES_DIR / "samples.json"
    if idx.exists():
        try:
            return _json.loads(idx.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"samples": []}


# ---------------------------------------------------------------------------
# History + reports (auditable summaries)
# ---------------------------------------------------------------------------
@router.get("/history")
async def history() -> dict:
    ctrl = await get_controller()
    return {"queries": ctrl.store.list()}


@router.get("/report/{query_id}")
async def report(query_id: str, format: str = "html"):
    ctrl = await get_controller()
    stored = ctrl.store.get(query_id)
    if stored is None:
        raise HTTPException(404, "Report not found (query store is in-memory "
                                 "and capped — run the query again)")
    if format == "json":
        return render_json_report(stored)
    html_text = render_html_report(stored)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html_text)


@router.get("/report/{query_id}/download")
async def report_download(query_id: str, format: str = "html"):
    ctrl = await get_controller()
    stored = ctrl.store.get(query_id)
    if stored is None:
        raise HTTPException(404, "Report not found")
    from fastapi.responses import Response
    if format == "json":
        import json as _json
        body = _json.dumps(render_json_report(stored), indent=2)
        return Response(body, media_type="application/json", headers={
            "Content-Disposition":
                f'attachment; filename="satai_report_{query_id[:8]}.json"'})
    body = render_html_report(stored)
    return Response(body, media_type="text/html", headers={
        "Content-Disposition":
            f'attachment; filename="satai_report_{query_id[:8]}.html"'})
