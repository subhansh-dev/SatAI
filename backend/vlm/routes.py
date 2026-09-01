"""
SatAI — VLM API Routes
FastAPI router for vision-language queries.
"""
import base64
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional

from vlm.controller import Controller
from vlm.tool_registry import registry
from vlm.schemas import (
    VLMQuery, VLMResponse, VLMStatus,
    CaptionRequest, GroundRequest, ChangeRequest, SARFusionRequest,
)

logger = logging.getLogger("satai.api")
router = APIRouter(prefix="/vlm", tags=["VLM"])

_controller: Optional[Controller] = None


async def get_controller() -> Controller:
    global _controller
    if _controller is None:
        _controller = Controller()
        logger.info("VLM Controller initialized")
    return _controller


@router.get("/status")
async def vlm_status():
    """Check VLM backend status."""
    ctrl = await get_controller()
    health = await ctrl.vlm.health_check()
    return VLMStatus(
        mode=ctrl.vlm.mode,
        model=ctrl.vlm.active_model,
        available=health,
        tools=registry.list_tools(),
    )


@router.post("/query")
async def vlm_query(query: VLMQuery):
    """Main agentic query endpoint."""
    ctrl = await get_controller()
    try:
        result = await ctrl.execute(
            query=query.query,
            images=query.images,
            mode=query.mode.value,
            metadata=query.metadata,
        )
        return result.model_dump()
    except Exception as e:
        logger.error(f"VLM query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/caption")
async def caption(req: CaptionRequest):
    """Generate a caption for satellite images."""
    await get_controller()
    tool = registry.get("caption")
    result = await tool.execute(images=req.images)
    return result


@router.post("/ground")
async def ground(req: GroundRequest):
    """Locate objects with bounding boxes."""
    await get_controller()
    tool = registry.get("ground")
    result = await tool.execute(query=req.query, images=req.images, output_format=req.output_format)
    return result


@router.post("/change")
async def change(req: ChangeRequest):
    """Describe changes between two images."""
    await get_controller()
    tool = registry.get("change_desc")
    result = await tool.execute(query=req.query, images=req.images)
    return result


@router.post("/sar-fusion")
async def sar_fusion(req: SARFusionRequest):
    """Analyze optical + SAR pair."""
    await get_controller()
    tool = registry.get("sar_fusion")
    result = await tool.execute(query=req.query, images=[req.optical_image, req.sar_image])
    return result


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image and return base64 for use in queries."""
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20MB)")
    b64 = base64.b64encode(data).decode()
    return {"base64": b64, "filename": file.filename, "size_bytes": len(data)}
