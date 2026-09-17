"""
SatAI — Satellite Fetch Routes
Endpoints to fetch Sentinel-2 (optical) and Sentinel-1 (SAR) from GEE.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from .gee_fetcher import gee

logger = logging.getLogger("satai.sat_routes")
router = APIRouter(prefix="/vlm", tags=["Satellite"])


class SingleFetchRequest(BaseModel):
    lat: float = Field(description="Latitude")
    lon: float = Field(description="Longitude")
    start_date: str = Field(default="2024-01-01", description="Start date YYYY-MM-DD")
    end_date: str = Field(default="2024-12-31", description="End date YYYY-MM-DD")
    cloud_max: int = Field(default=20, description="Max cloud percentage")
    scale: int = Field(default=256, description="Image dimensions (px)")


class BitemporalFetchRequest(BaseModel):
    lat: float
    lon: float
    date1: str = Field(default="2024-01-01", description="Before date")
    date2: str = Field(default="2024-06-01", description="After date")
    cloud_max: int = 20
    scale: int = 256


class CrossmodalFetchRequest(BaseModel):
    lat: float
    lon: float
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    scale: int = 256


@router.post("/fetch-sentinel2")
async def fetch_sentinel2(req: SingleFetchRequest):
    """Fetch a Sentinel-2 optical image from GEE."""
    result = gee.fetch_sentinel2(
        lat=req.lat, lon=req.lon,
        start_date=req.start_date, end_date=req.end_date,
        cloud_max=req.cloud_max, scale=req.scale,
    )
    if result.get("error"):
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/fetch-sentinel1")
async def fetch_sentinel1(req: SingleFetchRequest):
    """Fetch a Sentinel-1 SAR image from GEE."""
    result = gee.fetch_sentinel1(
        lat=req.lat, lon=req.lon,
        start_date=req.start_date, end_date=req.end_date,
        scale=req.scale,
    )
    if result.get("error"):
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/fetch-bitemporal")
async def fetch_bitemporal(req: BitemporalFetchRequest):
    """Fetch two Sentinel-2 images for change detection."""
    result = gee.fetch_pair(
        lat=req.lat, lon=req.lon,
        date1=req.date1, date2=req.date2,
        cloud_max=req.cloud_max, scale=req.scale,
    )
    return result


@router.post("/fetch-crossmodal")
async def fetch_crossmodal(req: CrossmodalFetchRequest):
    """Fetch co-registered optical + SAR pair."""
    result = gee.fetch_crossmodal(
        lat=req.lat, lon=req.lon,
        start_date=req.start_date, end_date=req.end_date,
        scale=req.scale,
    )
    return result


@router.get("/gee-status")
async def gee_status():
    """Check if GEE is connected."""
    return {
        "available": gee.initialized,
        "message": "GEE connected" if gee.initialized else "GEE not connected — upload images manually",
    }
