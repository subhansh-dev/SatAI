"""
SatAI — SatQuery AI · FastAPI Application
SIH26167 — ISRO: Interactive Vision-Language Assistant for Multimodal
Remote Sensing Image Analysis through Text Queries.

The app serves:
- the SatAI single-page frontend (vanilla JS, offline-capable)
- /vlm/*  agentic analysis API (see backend/vlm/routes.py)
- /api/health  liveness probe
"""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import config
from vlm.routes import router as vlm_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("satai.api")

app = FastAPI(
    title="SatAI — SatQuery AI",
    description="Agentic Vision-Language Assistant for Multimodal Remote "
                "Sensing Image Analysis (SIH26167, ISRO)",
    version=config.APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(vlm_router)

# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> HTMLResponse:
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>SatAI — SatQuery AI</h1><p>Frontend missing — see /docs</p>")


# ---------------------------------------------------------------------------
# Bounded per-IP rate limiter (protects the VLM quota without unbounded growth)
# ---------------------------------------------------------------------------
_hits: "OrderedDict[str, deque]" = OrderedDict()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.client and request.url.path.startswith("/vlm/"):
        ip = request.client.host or "?"
        now = time.time()
        bucket = _hits.get(ip)
        if bucket is None:
            bucket = _hits[ip] = deque()
        while bucket and bucket[0] < now - config.RATE_LIMIT_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= config.RATE_LIMIT_REQUESTS:
            return JSONResponse(
                {"detail": "Rate limit exceeded — slow down."},
                status_code=429)
        bucket.append(now)
        if len(_hits) > 4096:            # bound memory under IP churn
            _hits.popitem(last=False)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        {"detail": f"Internal error: {type(exc).__name__} — see server logs."},
        status_code=500)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    from vlm.controller import get_controller
    ctrl = await get_controller()
    vlm_ok = ctrl.vlm.configured
    return {
        "status": "online" if vlm_ok else "degraded",
        "app": "SatAI — SatQuery AI",
        "version": config.APP_VERSION,
        "ps_id": config.PS_ID,
        "vlm_mode": ctrl.vlm.mode,
        "vlm_model": ctrl.vlm.active_model,
        "vlm_backend_ready": vlm_ok,
        "tool_count": len(ctrl.vlm.__dict__.get("_tools", {})) or 6,
    }


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj: Any):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)
