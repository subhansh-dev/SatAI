import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import numpy as np
import json
from collections import defaultdict
import time as _time
from datetime import datetime, timezone

from pipeline.satellite_engine import SatelliteEngine
from pipeline.signal_processor import SignalProcessor
from pipeline.data_ingestion import DataIngestion
from pipeline.ai_reconstructor import AIReconstructor
from pipeline.gemini_analyzer import GeminiAnalyzer
from pipeline.environmental_data import EnvironmentalData
from pipeline.historical_web import HistoricalWeb
from pipeline.archaeological_db import ArchaeologicalDB


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def safe_json(data):
    return json.loads(json.dumps(data, cls=NumpyEncoder))


app = FastAPI(title="CHRONOVISOR", description="Temporal Archaeology Engine", version="0.6.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


_rate_limit_store = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = 60


def _check_rate_limit(ip: str) -> bool:
    now = _time.time()
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if now - t < RATE_WINDOW]
    if len(_rate_limit_store[ip]) >= RATE_LIMIT:
        return False
    _rate_limit_store[ip].append(now)
    return True


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded. 30 req/min.", "retry_after": RATE_WINDOW})
    return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc), "type": type(exc).__name__})


satellite = SatelliteEngine()
signal_proc = SignalProcessor()
ingestion = DataIngestion()
env_data = EnvironmentalData()
hist_web = HistoricalWeb()
arch_db = ArchaeologicalDB()
ai = AIReconstructor()
gemini = GeminiAnalyzer()

frontend_dir = Path(__file__).parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "scan_history.json"


@app.on_event("startup")
async def startup_init():
    satellite.initialize()
    gemini.initialize()
    ai.load_models()


def _load_history():
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_history(history):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(history[-200:], default=str), encoding="utf-8")
    except Exception:
        pass


scan_history = _load_history()
chat_sessions = {}


class LocationRequest(BaseModel):
    lat: float
    lon: float
    radius_m: int = 500
    start_date: str = "2017-01-01"
    end_date: Optional[str] = None
    source: str = "sentinel2"


class SignalRequest(BaseModel):
    frequencies: Optional[List[float]] = None
    amplitudes: Optional[List[float]] = None
    sample_rate: int = 44100


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    scan_index: Optional[int] = None


class CompareRequest(BaseModel):
    locations: List[Dict[str, Any]]


class AnomalyExplainRequest(BaseModel):
    anomaly: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class AIInterpretRequest(BaseModel):
    signal_data: Optional[Dict[str, Any]] = {}
    spectral_data: Optional[Dict[str, Any]] = {}
    env_data: Optional[Dict[str, Any]] = {}
    pleiades: Optional[Dict[str, Any]] = {}
    wikidata: Optional[Dict[str, Any]] = {}
    gbif: Optional[Dict[str, Any]] = {}
    magnetic: Optional[Dict[str, Any]] = {}
    other: Optional[Dict[str, Any]] = {}


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>CHRONOVISOR</h1>")


@app.get("/api/health")
async def health():
    satellite._ensure_init()
    return {
        "status": "operational",
        "version": "0.3.0",
        "engines": {
            "satellite": satellite.initialized,
            "signal_processor": True,
            "data_ingestion": True,
            "ai_reconstructor": ai.models_loaded,
            "gemini_ai": gemini.initialized,
            "environmental": True,
            "historical_web": True,
        },
        "scan_history_count": len(scan_history),
    }


@app.post("/api/satellite/timeseries")
async def satellite_timeseries(req: LocationRequest):
    return satellite.get_satellite_timeseries(
        lat=req.lat,
        lon=req.lon,
        radius_m=req.radius_m,
        start_date=req.start_date,
        end_date=req.end_date,
        source=req.source,
    )


@app.post("/api/satellite/anomalies")
async def satellite_anomalies(req: LocationRequest):
    ts = satellite.get_satellite_timeseries(
        lat=req.lat, lon=req.lon, radius_m=req.radius_m,
        start_date=req.start_date, end_date=req.end_date, source=req.source
    )
    timeseries = ts.get("timeseries", [])
    anomalies = satellite.detect_anomalies(timeseries)
    structural = {}
    if timeseries:
        ndvi = [t["ndvi"] for t in timeseries]
        thermal = [t["thermal"] for t in timeseries]
        dates = [t["date"] for t in timeseries]
        structural = ai.detect_buried_structures(ndvi, thermal, dates)
    return safe_json({
        "location": {"lat": req.lat, "lon": req.lon},
        "data_points": len(timeseries),
        "satellite_anomalies": anomalies,
        "structural_analysis": structural,
    })


@app.post("/api/satellite/spectral")
async def satellite_spectral(req: LocationRequest):
    return safe_json(satellite.compute_spectral_indices(req.lat, req.lon, req.radius_m))


@app.post("/api/signal/analyze")
async def signal_analyze(req: SignalRequest):
    if not req.frequencies or not req.amplitudes:
        return {"error": "No signal data provided. Send frequencies and amplitudes arrays.", "required": {"frequencies": [100, 200, 300], "amplitudes": [0.5, 0.3, 0.1], "sample_rate": 44100}}
    return safe_json(signal_proc.analyze_spectrum(np.array(req.amplitudes), sample_rate=req.sample_rate))


@app.post("/api/signal/em-field")
async def em_field(lat: float = 28.6139, lon: float = 77.2090, radius_m: int = 500, grid_res: int = 10):
    """Real EM field map from NOAA WMM magnetic intensity grid."""
    import concurrent.futures
    from scipy.interpolate import griddata

    grid_res = min(max(grid_res, 5), 20)
    deg_step_lat = (radius_m / 111320)
    deg_step_lon = (radius_m / (111320 * max(np.cos(np.radians(lat)), 0.01)))

    lats = np.linspace(lat - deg_step_lat, lat + deg_step_lat, grid_res)
    lons = np.linspace(lon - deg_step_lon, lon + deg_step_lon, grid_res)

    def fetch_mag(lat_val, lon_val):
        try:
            r = arch_db.magnetic_anomaly(lat_val, lon_val)
            ti = r.get("total_intensity_nt")
            if ti is not None:
                return (lat_val, lon_val, float(ti))
        except Exception:
            pass
        return None

    points = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_mag, lt, ln): (lt, ln) for lt in lats for ln in lons}
        for f in concurrent.futures.as_completed(futures):
            result = f.result()
            if result:
                points.append(result)

    if len(points) < 4:
        return {"error": f"Not enough magnetic data points ({len(points)}/{grid_res*grid_res}). Try a different location."}

    pts_lat = np.array([p[0] for p in points])
    pts_lon = np.array([p[1] for p in points])
    pts_val = np.array([p[2] for p in points])

    grid_lat = np.linspace(pts_lat.min(), pts_lat.max(), grid_res)
    grid_lon = np.linspace(pts_lon.min(), pts_lon.max(), grid_res)
    grid_xx, grid_yy = np.meshgrid(grid_lon, grid_lat)

    field = griddata(
        np.column_stack([pts_lon, pts_lat]),
        pts_val,
        (grid_xx, grid_yy),
        method="cubic",
        fill_value=float(np.mean(pts_val)),
    )

    hotspots = []
    for i in range(field.shape[0]):
        for j in range(field.shape[1]):
            val = field[i, j]
            neighbors = field[max(0,i-1):min(field.shape[0],i+2), max(0,j-1):min(field.shape[1],j+2)]
            if val == np.max(neighbors) and val > np.mean(pts_val) + np.std(pts_val):
                hotspots.append({"lat": float(grid_lat[i]), "lon": float(grid_lon[j]), "intensity_nt": round(float(val), 1)})

    interpretation = []
    gradient = float(np.max(field) - np.min(field))
    if gradient > 100:
        interpretation.append(f"High magnetic gradient ({gradient:.0f} nT) — possible buried ferrous structures or geological contact")
    elif gradient > 50:
        interpretation.append(f"Moderate gradient ({gradient:.0f} nT) — subsurface variation detected")
    else:
        interpretation.append(f"Low gradient ({gradient:.0f} nT) — magnetically uniform area")

    return safe_json({
        "source": "NOAA WMM",
        "location": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "grid_size": grid_res,
        "field_values": field.tolist(),
        "hotspots": hotspots,
        "hotspot_count": len(hotspots),
        "max_intensity": round(float(np.max(field)), 1),
        "min_intensity": round(float(np.min(field)), 1),
        "mean_intensity": round(float(np.mean(field)), 1),
        "gradient_nt": round(gradient, 1),
        "data_points": len(points),
        "interpretation": interpretation,
    })


@app.get("/api/signal/fft")
async def signal_fft(lat: float = 28.6139, lon: float = 77.2090, radius_m: int = 500):
    """Real FFT analysis of spatial magnetic field variation along a transect."""
    import concurrent.futures

    n_samples = 64
    deg_step_lat = (radius_m / 111320)
    deg_step_lon = (radius_m / (111320 * max(np.cos(np.radians(lat)), 0.01)))

    transect_lats = np.linspace(lat - deg_step_lat, lat + deg_step_lat, n_samples)
    transect_lons = np.full(n_samples, lon)
    transect_dists = np.linspace(-radius_m, radius_m, n_samples)

    def fetch_mag(lat_val):
        try:
            r = arch_db.magnetic_anomaly(lat_val, lon)
            ti = r.get("total_intensity_nt")
            if ti is not None:
                return float(ti)
        except Exception:
            pass
        return None

    readings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_mag, lt): i for i, lt in enumerate(transect_lats)}
        results = [None] * n_samples
        for f in concurrent.futures.as_completed(futures):
            idx = futures[f]
            val = f.result()
            if val is not None:
                results[idx] = val

    valid = [(transect_dists[i], results[i]) for i in range(n_samples) if results[i] is not None]
    if len(valid) < 8:
        return {"error": f"Not enough magnetic data points ({len(valid)}/{n_samples}). Try a different location."}

    distances = np.array([v[0] for v in valid])
    values = np.array([v[1] for v in valid])

    mean_val = np.mean(values)
    detrended = values - mean_val

    fft_result = np.fft.rfft(detrended)
    freqs = np.fft.rfftfreq(len(detrended), d=(distances[1] - distances[0]) if len(distances) > 1 else 1.0)
    mags = np.abs(fft_result)

    if len(freqs) > 1:
        sampling_interval = distances[1] - distances[0]
        spatial_freqs = freqs[1:]
        spatial_mags = mags[1:]
    else:
        spatial_freqs = np.array([])
        spatial_mags = np.array([])

    dominant = []
    if len(spatial_mags) > 0:
        sorted_idx = np.argsort(spatial_mags)[::-1]
        for i in sorted_idx[:3]:
            if spatial_mags[i] > np.mean(spatial_mags) * 2:
                period_m = 1.0 / spatial_freqs[i] if spatial_freqs[i] > 0 else float('inf')
                dominant.append({
                    "frequency": round(float(spatial_freqs[i]), 4),
                    "magnitude": round(float(spatial_mags[i]), 2),
                    "period_m": round(float(period_m), 1),
                })

    patterns = signal_proc._detect_patterns(detrended, np.abs(np.fft.rfft(detrended)), np.fft.rfftfreq(len(detrended), d=1.0))

    interpretation = []
    if dominant:
        interpretation.append(f"{len(dominant)} dominant spatial frequency peaks detected")
        for d in dominant:
            interpretation.append(f"  Period {d['period_m']}m (freq {d['frequency']} cycles/m) — magnitude {d['magnitude']}")
    if patterns.get("harmonics"):
        interpretation.append(f"Harmonic series detected ({patterns.get('harmonics_count', '?')} harmonics)")
    if patterns.get("periodic"):
        interpretation.append(f"Periodic signal detected — period: {patterns.get('period', '?')} samples")
    if not interpretation:
        interpretation.append("No significant spatial frequency patterns — magnetically uniform transect")

    return safe_json({
        "source": "NOAA WMM",
        "location": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "transect": {"distances": distances.tolist(), "values": values.tolist()},
        "fft": {"frequencies": spatial_freqs.tolist(), "magnitudes": spatial_mags.tolist()},
        "dominant_frequencies": dominant,
        "mean_intensity_nt": round(float(mean_val), 1),
        "gradient_nt": round(float(np.max(values) - np.min(values)), 1),
        "data_points": len(valid),
        "patterns": patterns,
        "interpretation": interpretation,
    })


@app.get("/api/signal/magnetic-gradient")
async def magnetic_gradient(lat: float = Query(...), lon: float = Query(...), radius_m: int = 500):
    import concurrent.futures

    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 0), (0, 1), (1, -1), (1, 0), (1, 1)]
    deg_step = (radius_m / 111320) * 0.8

    def fetch_mag(dlat, dlon):
        return arch_db.magnetic_anomaly(lat + dlat, lon + dlon)

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as ex:
        futures = {ex.submit(fetch_mag, o[0] * deg_step, o[1] * deg_step): o for o in offsets}

    points = []
    for fut, offset in futures.items():
        r = fut.result()
        ti = r.get("total_intensity_nt")
        if ti is not None:
            points.append({"offset_x": offset[1], "offset_y": offset[0], "total_intensity_nt": ti})

    if not points:
        return safe_json({
            "error": "Magnetic data unavailable",
            "interpretation": ["Use on-site magnetometer for detailed survey."],
        })

    vals = [p["total_intensity_nt"] for p in points]
    center = next((p for p in points if p["offset_x"] == 0 and p["offset_y"] == 0), None)
    center_val = center["total_intensity_nt"] if center else vals[len(vals) // 2]

    interpretation = []
    gradient = max(vals) - min(vals)
    if gradient > 100:
        interpretation.append(f"High magnetic gradient ({gradient:.0f} nT) — possible buried ferrous structures or geological contact")
    elif gradient > 50:
        interpretation.append(f"Moderate gradient ({gradient:.0f} nT) — subsurface variation detected")
    else:
        interpretation.append(f"Low gradient ({gradient:.0f} nT) — magnetically uniform area")

    return safe_json({
        "source": "NOAA WMM",
        "center": {"lat": lat, "lon": lon, "total_intensity_nt": center_val},
        "profile": points,
        "gradient_nt": round(gradient, 1),
        "mean_nt": round(float(np.mean(vals)), 1),
        "std_nt": round(float(np.std(vals)), 1),
        "interpretation": interpretation,
    })


@app.get("/api/sar/backscatter")
async def sar_backscatter(lat: float = Query(...), lon: float = Query(...), radius_m: int = 500, start_date: str = "2020-01-01"):
    return safe_json(satellite.get_sar_backscatter(lat, lon, radius_m, start_date))


@app.post("/api/ai/temporal-change")
async def temporal_change(req: LocationRequest):
    ts = satellite.get_satellite_timeseries(
        lat=req.lat, lon=req.lon, radius_m=req.radius_m, start_date=req.start_date, end_date=req.end_date
    )
    timeseries = ts.get("timeseries", [])
    if not timeseries:
        return {"error": "No data"}
    ndvi = [t["ndvi"] for t in timeseries]
    dates = [t["date"] for t in timeseries]
    return safe_json(ai.analyze_temporal_change(ndvi, dates))


@app.post("/api/ai/terrain")
async def terrain_3d(lat: float = 28.6139, lon: float = 77.2090, grid_size: int = 20):
    terrain_data = ingestion.get_terrain_grid(lat, lon, grid_size=min(grid_size, 30))
    if "error" in terrain_data:
        return terrain_data
    return safe_json(ai.reconstruct_3d_terrain(np.array(terrain_data["elevation"]), lat, lon))


@app.get("/api/site/ndvi-change")
async def ndvi_change(
    lat: float = Query(...), lon: float = Query(...), radius_m: int = 500,
    p1_start: str = "2018-01-01", p1_end: str = "2018-12-31",
    p2_start: str = "2024-01-01", p2_end: str = "2024-12-31",
):
    return safe_json(satellite.ndvi_change_detection(lat, lon, radius_m, p1_start, p1_end, p2_start, p2_end))


@app.get("/api/site/elevation-profile")
async def elevation_profile(lat: float = Query(...), lon: float = Query(...), radius_m: int = 500, direction: str = "E-W"):
    return safe_json(ingestion.get_elevation_profile(lat, lon, radius_m, direction))


@app.get("/api/site/water")
async def water_proximity(lat: float = Query(...), lon: float = Query(...), radius_m: int = 2000):
    return safe_json(ingestion.get_water_proximity(lat, lon, radius_m))


@app.get("/api/site/geology")
async def geology(lat: float = Query(...), lon: float = Query(...)):
    return safe_json(ingestion.get_geological_context(lat, lon))


@app.get("/api/site/places")
async def nearby_places(lat: float = Query(...), lon: float = Query(...), radius_km: int = 50):
    return safe_json(ingestion.get_nearby_places(lat, lon, radius_km))


@app.get("/api/data/space-weather")
async def space_weather(days: int = 7):
    return safe_json({"solar_wind": ingestion.get_noaa_space_weather(days), "geomagnetic": ingestion.get_geomagnetic_indices(days)})


@app.get("/api/data/lightning")
async def lightning(lat: float = 28.6139, lon: float = 77.2090, radius_km: int = 100):
    return safe_json(ingestion.get_lightning_data(lat, lon, radius_km))


@app.get("/api/data/historical-maps")
async def historical_maps(lat: float = 28.6139, lon: float = 77.2090):
    return safe_json(ingestion.get_historical_maps(lat, lon))


@app.get("/api/data/radio-astronomy")
async def radio_astronomy(freq_mhz: float = 1420, lat: float = 28.6139, lon: float = 77.2090):
    return safe_json(ingestion.get_radio_astronomy_archive(freq_mhz, lat=lat, lon=lon))


@app.get("/api/full-scan")
async def full_scan(lat: float = Query(...), lon: float = Query(...), radius_m: int = 500, start_date: str = "2017-01-01"):
    ts_task = asyncio.create_task(asyncio.to_thread(satellite.get_satellite_timeseries, lat, lon, radius_m, start_date))
    weather_task = asyncio.create_task(asyncio.to_thread(ingestion.get_noaa_space_weather, 3))
    maps_task = asyncio.create_task(asyncio.to_thread(ingestion.get_historical_maps, lat, lon))
    spectral_task = asyncio.create_task(asyncio.to_thread(satellite.compute_spectral_indices, lat, lon, radius_m))
    lightning_task = asyncio.create_task(asyncio.to_thread(ingestion.get_lightning_data, lat, lon))

    ts = await ts_task
    timeseries = ts.get("timeseries", [])
    anomalies = satellite.detect_anomalies(timeseries)
    structural = {}
    temporal = {}
    if timeseries:
        ndvi = [t["ndvi"] for t in timeseries]
        thermal = [t["thermal"] for t in timeseries]
        dates = [t["date"] for t in timeseries]
        structural = ai.detect_buried_structures(ndvi, thermal, dates)
        temporal = ai.analyze_temporal_change(ndvi, dates)

    space_weather_r = await weather_task
    maps_r = await maps_task
    spectral_r = await spectral_task
    lightning_r = await lightning_task

    scan_result = safe_json({
        "scan_target": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "satellite": {"source": ts.get("source", "unknown"), "data_points": len(timeseries), "timeseries": timeseries, "error": ts.get("error")},
        "anomalies": anomalies,
        "structural_analysis": structural,
        "temporal_changes": temporal,
        "spectral_indices": spectral_r,
        "environmental": {},
        "historical_web": {},
        "archaeological_db": {},
        "space_weather": {"interpretation": space_weather_r.get("interpretation", []), "error": space_weather_r.get("error")},
        "lightning": {"strikes": lightning_r.get("strike_count"), "error": lightning_r.get("error"), "sources": lightning_r.get("sources")},
        "historical_maps": maps_r.get("available_sources", []),
        "summary": generate_summary(anomalies, structural, temporal, spectral_r),
    })

    scan_history.append({
        "lat": lat, "lon": lon, "radius_m": radius_m,
        "anomaly_count": len(anomalies),
        "structural_probability": structural.get("structural_probability", 0),
        "data_points": len(timeseries),
        "result": scan_result,
    })
    _save_history(scan_history)
    return scan_result


@app.post("/api/gemini/analyze")
async def gemini_analyze(req: LocationRequest):
    if not gemini.initialized:
        return {"error": "Gemini not initialized. Set GEMINI_API_KEY in .env"}
    ts = satellite.get_satellite_timeseries(req.lat, req.lon, req.radius_m, req.start_date, req.end_date, req.source)
    timeseries = ts.get("timeseries", [])
    anomalies = satellite.detect_anomalies(timeseries)
    structural = {}
    temporal = {}
    if timeseries:
        ndvi = [t["ndvi"] for t in timeseries]
        thermal = [t["thermal"] for t in timeseries]
        dates = [t["date"] for t in timeseries]
        structural = ai.detect_buried_structures(ndvi, thermal, dates)
        temporal = ai.analyze_temporal_change(ndvi, dates)
    spectral = satellite.compute_spectral_indices(req.lat, req.lon, req.radius_m)
    weather = ingestion.get_noaa_space_weather(3)
    scan_data = {
        "scan_target": {"lat": req.lat, "lon": req.lon, "radius_m": req.radius_m},
        "satellite": {"source": ts.get("source", "unknown"), "data_points": len(timeseries), "timeseries": timeseries, "error": ts.get("error")},
        "anomalies": anomalies,
        "structural_analysis": structural,
        "temporal_changes": temporal,
        "spectral_indices": spectral,
        "space_weather": weather,
        "summary": generate_summary(anomalies, structural, temporal, spectral),
    }
    ai_result = await gemini.analyze_scan_results(scan_data)
    return {"scan": safe_json(scan_data), "ai_analysis": ai_result}


@app.post("/api/gemini/report")
async def gemini_report(req: LocationRequest, location_name: str = ""):
    if not gemini.initialized:
        return {"error": "Gemini not initialized"}
    ts = satellite.get_satellite_timeseries(req.lat, req.lon, req.radius_m, req.start_date)
    timeseries = ts.get("timeseries", [])
    anomalies = satellite.detect_anomalies(timeseries)
    structural = {}
    temporal = {}
    if timeseries:
        ndvi = [t["ndvi"] for t in timeseries]
        thermal = [t["thermal"] for t in timeseries]
        dates = [t["date"] for t in timeseries]
        structural = ai.detect_buried_structures(ndvi, thermal, dates)
        temporal = ai.analyze_temporal_change(ndvi, dates)
    scan_data = {
        "scan_target": {"lat": req.lat, "lon": req.lon},
        "satellite": {"data_points": len(timeseries)},
        "anomalies": anomalies,
        "structural_analysis": structural,
        "temporal_changes": temporal,
    }
    return await gemini.generate_report(scan_data, location_name)


@app.post("/api/gemini/explain-anomaly")
async def gemini_explain_anomaly(req: AnomalyExplainRequest):
    if not gemini.initialized:
        return {"error": "Gemini not initialized"}
    return await gemini.explain_anomaly(req.anomaly, req.context)


@app.get("/api/gemini/history")
async def gemini_history(lat: float, lon: float, name: str = ""):
    if not gemini.initialized:
        return {"error": "Gemini not initialized"}
    return await gemini.historical_context(lat, lon, name)


@app.post("/api/gemini/compare")
async def gemini_compare(req: CompareRequest):
    if not gemini.initialized:
        return {"error": "Gemini not initialized"}
    return await gemini.compare_locations(req.locations)


@app.post("/api/gemini/chat")
async def gemini_chat(req: ChatRequest):
    if not gemini.initialized:
        return {"error": "Gemini not initialized"}
    if req.session_id not in chat_sessions:
        chat_sessions[req.session_id] = []
    scan_context = None
    if req.scan_index is not None and 0 <= req.scan_index < len(scan_history):
        scan_context = scan_history[req.scan_index].get("result", {})
    elif scan_history:
        scan_context = scan_history[-1].get("result", {})
    result = await gemini.chat(req.message, scan_context, chat_sessions[req.session_id])
    chat_sessions[req.session_id].append({"role": "user", "content": req.message})
    if "reply" in result:
        chat_sessions[req.session_id].append({"role": "assistant", "content": result["reply"]})
    chat_sessions[req.session_id] = chat_sessions[req.session_id][-20:]
    return result


@app.post("/api/gemini/investigate")
async def gemini_investigate(req: LocationRequest):
    if not gemini.initialized:
        return {"error": "Gemini not initialized"}
    ts = satellite.get_satellite_timeseries(req.lat, req.lon, req.radius_m, req.start_date)
    timeseries = ts.get("timeseries", [])
    anomalies = satellite.detect_anomalies(timeseries)
    structural = {}
    if timeseries:
        ndvi = [t["ndvi"] for t in timeseries]
        thermal = [t["thermal"] for t in timeseries]
        dates = [t["date"] for t in timeseries]
        structural = ai.detect_buried_structures(ndvi, thermal, dates)
    return await gemini.suggest_investigation({
        "scan_target": {"lat": req.lat, "lon": req.lon},
        "anomalies": anomalies,
        "structural_analysis": structural,
    })


@app.get("/api/env/soil")
async def env_soil(lat: float, lon: float, depth: str = "0-5cm"):
    return safe_json(env_data.get_soil_data(lat, lon, depth))


@app.get("/api/env/faults")
async def env_faults(lat: float, lon: float, radius_km: int = 100):
    return safe_json(env_data.get_fault_lines(lat, lon, radius_km))


@app.get("/api/env/population")
async def env_population(lat: float, lon: float):
    return safe_json(env_data.get_population_density(lat, lon))


@app.get("/api/env/water-table")
async def env_water(lat: float, lon: float):
    return safe_json(env_data.get_water_table(lat, lon))


@app.get("/api/env/full")
async def env_full(lat: float, lon: float, radius_km: int = 100):
    return safe_json(env_data.full_environmental_scan(lat, lon, radius_km))


@app.get("/api/web/wayback")
async def web_wayback(lat: float, lon: float, place_name: str = ""):
    return safe_json(hist_web.wayback_search(lat, lon, place_name))


@app.get("/api/web/osm")
async def web_osm(lat: float, lon: float, radius_m: int = 500):
    return safe_json(hist_web.osm_history(lat, lon, radius_m))


@app.get("/api/web/full")
async def web_full(lat: float, lon: float, place_name: str = "", radius_m: int = 500):
    return safe_json(hist_web.full_web_scan(lat, lon, place_name, radius_m))


@app.get("/api/arch/pleiades")
async def arch_pleiades(lat: float, lon: float, radius_km: int = 50):
    return safe_json(arch_db.pleiades_nearby(lat, lon, radius_km))


@app.get("/api/arch/wikidata")
async def arch_wikidata(lat: float, lon: float, radius_km: int = 50):
    return safe_json(arch_db.wikidata_sites(lat, lon, radius_km))


@app.get("/api/arch/gbif")
async def arch_gbif(lat: float, lon: float, radius_km: int = 10):
    return safe_json(arch_db.gbif_species(lat, lon, radius_km))


@app.get("/api/arch/magnetic")
async def arch_magnetic(lat: float, lon: float):
    return safe_json(arch_db.magnetic_anomaly(lat, lon))


@app.get("/api/arch/nightlights")
async def arch_nightlights(lat: float, lon: float):
    return safe_json(arch_db.nighttime_lights(lat, lon))


@app.get("/api/arch/lidar")
async def arch_lidar(lat: float, lon: float):
    return safe_json(arch_db.terrain_analysis(lat, lon))


@app.get("/api/arch/full")
async def arch_full(lat: float, lon: float, radius_km: int = 50):
    return safe_json(arch_db.full_db_scan(lat, lon, radius_km))


@app.get("/api/arch/climate")
async def arch_climate(lat: float, lon: float):
    return safe_json(arch_db.climate_data(lat, lon))


@app.get("/api/arch/landcover")
async def arch_landcover(lat: float, lon: float):
    return safe_json(arch_db.land_cover(lat, lon))


@app.get("/api/arch/suitability")
async def arch_suitability(lat: float, lon: float, radius_km: int = 50):
    return safe_json(arch_db.site_suitability(lat, lon, radius_km))


@app.get("/api/geocode")
async def geocode(q: str = Query(..., description="Place name to search")):
    return safe_json(arch_db.geocode(q))


@app.get("/api/arch/crossref")
async def arch_crossref(lat: float, lon: float, radius_km: int = 50):
    return safe_json(arch_db.cross_reference(lat, lon, radius_km))


@app.get("/api/arch/temporal")
async def arch_temporal(lat: float, lon: float):
    return safe_json(arch_db.temporal_changes(lat, lon))


@app.post("/api/arch/batch")
async def arch_batch(locations: list = Body(...)):
    return safe_json(arch_db.batch_scan(locations))


@app.get("/api/compare")
async def compare_scans(indices: str = Query(..., description="Comma-separated scan history indices")):
    try:
        idx_list = [int(i.strip()) for i in indices.split(",")]
        scans = []
        for i in idx_list:
            if 0 <= i < len(scan_history):
                s = scan_history[i]
                summary = s.get("result", {}).get("summary", {})
                scans.append({
                    "index": i,
                    "lat": s.get("lat"),
                    "lon": s.get("lon"),
                    "place_name": s.get("place_name", ""),
                    "anomaly_count": s.get("anomaly_count", 0),
                    "structural_probability": s.get("structural_probability", 0),
                    "confidence": summary.get("confidence", "unknown"),
                    "score": summary.get("archaeological_potential", 0),
                })
        if not scans:
            return {"error": "No valid scan indices found"}
        best = max(scans, key=lambda x: x.get("score", 0))
        return safe_json({"scans": scans, "best": best, "count": len(scans)})
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/export/json")
async def export_json(lat: float, lon: float):
    scan = None
    for s in reversed(scan_history):
        if abs(s.get("lat", 0) - lat) < 0.01 and abs(s.get("lon", 0) - lon) < 0.01:
            scan = s.get("result", {})
            break
    if not scan:
        return {"error": "No scan found. Run a scan first."}
    return JSONResponse(content=scan)


@app.get("/api/export/csv")
async def export_csv(lat: float, lon: float):
    scan = None
    for s in reversed(scan_history):
        if abs(s.get("lat", 0) - lat) < 0.01 and abs(s.get("lon", 0) - lon) < 0.01:
            scan = s.get("result", {})
            break
    if not scan:
        return {"error": "No scan found. Run a scan first."}
    result = arch_db.export_scan(scan, "csv")
    return PlainTextResponse(
        content=result.get("data", ""),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chronovisor_scan.csv"},
    )


@app.get("/api/mega-scan")
async def mega_scan(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: int = 500,
    start_date: str = "2017-01-01",
    place_name: str = "",
):
    ts = satellite.get_satellite_timeseries(lat, lon, radius_m, start_date)
    timeseries = ts.get("timeseries", [])
    anomalies = satellite.detect_anomalies(timeseries)
    structural = {}
    temporal = {}
    if timeseries:
        ndvi = [t["ndvi"] for t in timeseries]
        thermal = [t["thermal"] for t in timeseries]
        dates = [t["date"] for t in timeseries]
        structural = ai.detect_buried_structures(ndvi, thermal, dates)
        temporal = ai.analyze_temporal_change(ndvi, dates)
    spectral = satellite.compute_spectral_indices(lat, lon, radius_m)

    import concurrent.futures

    def safe_call(fn, *args):
        import time as _t
        for attempt in range(2):
            try:
                result = fn(*args)
                if isinstance(result, dict) and "error" not in result:
                    return result
                if attempt == 0:
                    _t.sleep(1)
                    continue
                return result
            except Exception as e:
                if attempt == 0:
                    _t.sleep(1)
                    continue
                return {"error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        soil_f = ex.submit(safe_call, env_data.get_soil_data, lat, lon)
        fault_f = ex.submit(safe_call, env_data.get_fault_lines, lat, lon, 100)
        pop_f = ex.submit(safe_call, env_data.get_population_density, lat, lon)
        water_f = ex.submit(safe_call, env_data.get_water_table, lat, lon)
        wayback_f = ex.submit(safe_call, hist_web.wayback_search, lat, lon, place_name)
        osm_f = ex.submit(safe_call, hist_web.osm_history, lat, lon, radius_m)
        weather_f = ex.submit(safe_call, ingestion.get_noaa_space_weather, 3)
        maps_f = ex.submit(safe_call, ingestion.get_historical_maps, lat, lon)
        pleiades_f = ex.submit(safe_call, arch_db.pleiades_nearby, lat, lon, 50)
        wikidata_f = ex.submit(safe_call, arch_db.wikidata_sites, lat, lon, 50)
        gbif_f = ex.submit(safe_call, arch_db.gbif_species, lat, lon, 50)
        nightlight_f = ex.submit(safe_call, arch_db.nighttime_lights, lat, lon)
        magnetic_f = ex.submit(safe_call, arch_db.magnetic_anomaly, lat, lon)
        climate_f = ex.submit(safe_call, arch_db.climate_data, lat, lon)
        landcover_f = ex.submit(safe_call, arch_db.land_cover, lat, lon)
        suitability_f = ex.submit(safe_call, arch_db.site_suitability, lat, lon, 50)

    soil_r = soil_f.result()
    fault_r = fault_f.result()
    water_r = water_f.result()
    pop_r = pop_f.result()
    wayback_r = wayback_f.result()
    osm_r = osm_f.result()
    weather_r = weather_f.result()
    maps_r = maps_f.result()
    pleiades_r = pleiades_f.result()
    wikidata_r = wikidata_f.result()
    gbif_r = gbif_f.result()
    nightlight_r = nightlight_f.result()
    magnetic_r = magnetic_f.result()
    climate_r = climate_f.result()
    landcover_r = landcover_f.result()
    suitability_r = suitability_f.result()

    sources_ok = sum(
        1
        for r in [
            soil_r, fault_r, water_r, pop_r, wayback_r, osm_r, weather_r,
            pleiades_r, wikidata_r, gbif_r, nightlight_r, magnetic_r, climate_r,
            landcover_r, suitability_r,
        ]
        if isinstance(r, dict) and "error" not in r
    )
    sources_total = 15

    fused = ai.fuse_all_data(
        structural=structural,
        anomalies=anomalies,
        temporal=temporal,
        spectral=spectral,
        soil=soil_r,
        faults=fault_r,
        water_table=water_r,
        population=pop_r,
        osm=osm_r,
        wayback=wayback_r,
    )

    ai_interpretation = ai.ai_interpret_fusion(fused) if ai._llm_client else ""
    if ai_interpretation:
        fused["ai_expert_interpretation"] = ai_interpretation

    result = safe_json({
        "scan_target": {"lat": lat, "lon": lon, "radius_m": radius_m, "place_name": place_name},
        "data_sources": {"ok": sources_ok, "total": sources_total, "status": f"{sources_ok}/{sources_total} sources available"},
        "satellite": {"source": ts.get("source", "unknown"), "data_points": len(timeseries), "timeseries": timeseries, "error": ts.get("error")},
        "anomalies": anomalies,
        "structural_analysis": structural,
        "temporal_changes": temporal,
        "spectral_indices": spectral,
        "environmental": {
            "soil": soil_r,
            "faults": fault_r,
            "population": pop_r,
            "water_table": water_r,
        },
        "historical_web": {
            "wayback": wayback_r,
            "osm": osm_r,
        },
        "archaeological_db": {
            "pleiades": pleiades_r,
            "wikidata": wikidata_r,
            "gbif": gbif_r,
            "nighttime_lights": nightlight_r,
            "magnetic": magnetic_r,
            "climate": climate_r,
            "land_cover": landcover_r,
            "suitability": suitability_r,
        },
        "space_weather": weather_r,
        "historical_maps": maps_r.get("available_sources", []) if isinstance(maps_r, dict) else [],
        "fused_assessment": fused,
        "summary": {
            "findings": fused.get("findings", []),
            "warnings": fused.get("warnings", []),
            "confidence": fused.get("confidence", "unknown"),
            "recommendation": fused.get("recommendation", ""),
            "archaeological_potential": fused.get("fused_score", 0),
        },
    })

    scan_history.append({
        "lat": lat, "lon": lon, "radius_m": radius_m, "place_name": place_name,
        "anomaly_count": len(anomalies),
        "structural_probability": structural.get("structural_probability", 0),
        "data_points": len(timeseries),
        "result": result,
        "type": "mega",
    })
    _save_history(scan_history)
    return result


@app.get("/api/export/report")
async def export_report(lat: float, lon: float, place_name: str = "", format: str = "html"):
    scan = None
    for s in reversed(scan_history):
        if abs(s.get("lat", 0) - lat) < 0.01 and abs(s.get("lon", 0) - lon) < 0.01:
            scan = s.get("result", {})
            break

    if not scan:
        return {"error": "No scan found for this location. Run a scan first."}

    report_md = ""
    if gemini.initialized:
        report = await gemini.generate_report(scan, place_name)
        report_md = report.get("report", "")

    target = scan.get("scan_target", {})
    fused = scan.get("fused_assessment", {})
    summary = scan.get("summary", {})
    env = scan.get("environmental", {})
    web = scan.get("historical_web", {})
    anomalies = scan.get("anomalies", [])
    structural = scan.get("structural_analysis", {})
    components = fused.get("component_scores", {})

    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>CHRONOVISOR Report - """ + str(place_name or f"{lat},{lon}") + """</title>
<style>
body{font-family:Georgia,serif;max-width:900px;margin:40px auto;padding:0 20px;color:#222;line-height:1.7;}
h1{color:#1a5c3a;border-bottom:3px solid #1a5c3a;padding-bottom:10px;}
h2{color:#2d7a4f;margin-top:30px;border-bottom:1px solid #c3e6cb;padding-bottom:6px;}
h3{color:#3d8b5e;margin-top:20px;}
.metric{display:inline-block;background:#f0f7f3;border:1px solid #c3e6cb;padding:10px 20px;margin:5px;border-radius:4px;text-align:center;}
.metric .val{font-size:24px;font-weight:bold;color:#1a5c3a;display:block;}
.metric .lbl{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:1px;}
.finding{background:#f8f9fa;border-left:4px solid #1a5c3a;padding:12px;margin:8px 0;font-size:14px;}
.warning{border-left-color:#f0ad4e;background:#fdf8f0;}
.error{border-left-color:#d9534f;}
table{width:100%;border-collapse:collapse;margin:15px 0;font-size:13px;}
th,td{border:1px solid #ddd;padding:8px 12px;text-align:left;}
th{background:#1a5c3a;color:white;font-size:12px;letter-spacing:1px;}
.score-bar{height:20px;background:#eee;border-radius:4px;margin:8px 0;overflow:hidden;}
.score-fill{height:100%;border-radius:4px;text-align:center;color:white;font-size:11px;line-height:20px;}
.modifier{display:inline-block;padding:4px 10px;margin:3px;border-radius:3px;font-size:11px;}
.positive{background:#d4edda;color:#155724;}
.negative{background:#f8d7da;color:#721c24;}
.footer{margin-top:40px;padding-top:20px;border-top:2px solid #eee;font-size:11px;color:#999;}
@media print{body{margin:0;padding:0 15px;}h1{font-size:20px;}}
</style></head><body>
<h1>CHRONOVISOR Archaeological Report</h1>
<p><strong>Location:</strong> """ + str(place_name or f"{lat}, {lon}") + """ (""" + str(lat) + """, """ + str(lon) + """)</p>
<p><strong>Date:</strong> """ + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + """</p>
<p><strong>Scan Radius:</strong> """ + str(target.get("radius_m", 500)) + """m</p>
<p><strong>Data Points:</strong> """ + str(scan.get("satellite", {}).get("data_points", 0)) + """ satellite observations</p>

<h2>1. Assessment Summary</h2>
<div class="metric"><span class="val">""" + str(fused.get("fused_score", 0)) + """%</span><span class="lbl">Fused Score</span></div>
<div class="metric"><span class="val">""" + str(fused.get("confidence", "N/A")).upper() + """</span><span class="lbl">Confidence</span></div>
<div class="metric"><span class="val">""" + str(len(anomalies)) + """</span><span class="lbl">Anomalies</span></div>
<div class="metric"><span class="val">""" + str(structural.get("structural_probability", 0)) + """%</span><span class="lbl">Structural Prob</span></div>
<div style="margin:15px 0;">
<div class="score-bar"><div class="score-fill" style="width:""" + str(fused.get("fused_score", 0)) + """%;background:""" + ("#28a745" if fused.get("fused_score", 0) > 70 else "#f0ad4e" if fused.get("fused_score", 0) > 40 else "#6c757d") + """;">""" + str(fused.get("fused_score", 0)) + """%</div></div>
</div>
"""

    rec = fused.get("recommendation", summary.get("recommendation", ""))
    if rec:
        html += '<div class="finding" style="border-left-color:#6f42c1;"><strong>RECOMMENDATION:</strong> ' + rec + '</div>\n'

    html += '<h3>Key Findings</h3>\n'
    for f in fused.get("findings", summary.get("findings", [])):
        html += '<div class="finding">' + f + '</div>\n'

    for w in fused.get("warnings", []):
        html += '<div class="finding warning">WARNING: ' + w + '</div>\n'

    if components:
        html += '<h2>2. Component Scores</h2>\n<table><tr><th>Factor</th><th>Score</th><th>Weight</th><th>Contribution</th></tr>\n'
        weights = fused.get("weights", {})
        for k, v in components.items():
            w = weights.get(k, 0)
            html += '<tr><td>' + k.replace("_", " ").title() + '</td><td>' + str(v) + '%</td><td>' + str(int(w * 100)) + '%</td><td>' + str(round(v * w, 1)) + '</td></tr>\n'
        html += '</table>\n'

    mods = fused.get("modifiers", [])
    if mods:
        html += '<h3>Score Modifiers</h3>\n'
        for m in mods:
            cls = "positive" if "+" in m.get("effect", "") else "negative"
            html += '<span class="modifier ' + cls + '">' + m.get("factor", "") + ': ' + m.get("effect", "") + ' (' + m.get("reason", "") + ')</span>\n'

    if anomalies:
        html += '<h2>3. Satellite Anomalies</h2>\n'
        for a in anomalies[:10]:
            html += '<div class="finding warning"><strong>' + str(a.get("type", "")) + '</strong> - ' + str(a.get("date", "")) + '<br>' + str(a.get("interpretation", "")) + '</div>\n'

    if env:
        html += '<h2>4. Environmental Context</h2>\n'
        soil = env.get("soil", {})
        if soil and "properties" in soil:
            html += '<h3>Soil Analysis (ISRIC SoilGrids)</h3>\n<table><tr><th>Property</th><th>Value</th><th>Unit</th></tr>\n'
            for k, v in soil["properties"].items():
                html += '<tr><td>' + k + '</td><td>' + str(v.get("value", "")) + '</td><td>' + str(v.get("unit", "")) + '</td></tr>\n'
            html += '</table>\n'
            for i in soil.get("interpretation", []):
                html += '<div class="finding">' + i + '</div>\n'

        faults = env.get("faults", {})
        if faults and "count" in faults:
            html += '<h3>Seismic Activity (USGS)</h3>\n'
            html += '<p>' + str(faults.get("count", 0)) + ' earthquakes since 2020. Activity: ' + str(faults.get("fault_activity", "?")) + '</p>\n'
            for i in faults.get("interpretation", []):
                html += '<div class="finding">' + i + '</div>\n'

        water = env.get("water_table", {})
        if water and "water_table" in water:
            html += '<h3>Water Table</h3>\n<p>Estimate: ' + str(water.get("water_table", "?")) + ' (elevation: ' + str(water.get("elevation_m", "?")) + 'm)</p>\n'
            for i in water.get("interpretation", []):
                html += '<div class="finding">' + i + '</div>\n'

    if web:
        html += '<h2>5. Historical Web Data</h2>\n'
        wb = web.get("wayback", {})
        if wb and wb.get("archives"):
            html += '<h3>Wayback Machine (' + str(wb.get("count", 0)) + ' archived pages)</h3>\n<ul>\n'
            for a in wb.get("archives", [])[:10]:
                html += '<li><a href="' + str(a.get("archived", a.get("archived_url", "#"))) + '">' + str(a.get("url", ""))[:80] + '</a> (' + str(a.get("timestamp", ""))[:4] + ')</li>\n'
            html += '</ul>\n'
        osm = web.get("osm", {})
        if osm and osm.get("historic"):
            html += '<h3>OpenStreetMap Historic Features</h3>\n<ul>\n'
            for h in osm.get("historic", [])[:10]:
                html += '<li>' + str(h.get("name", "Unnamed")) + ' (' + str(h.get("historic", h.get("heritage", "historic"))) + ')</li>\n'
            html += '</ul>\n'

    if report_md:
        html += '<h2>6. AI Analysis</h2>\n<div style="white-space:pre-wrap;font-size:14px;">' + report_md + '</div>\n'

    html += '<div class="footer">Generated by CHRONOVISOR Temporal Archaeology Engine v0.3.0 | Fused Score: ' + str(fused.get("fused_score", 0)) + '% | Confidence: ' + str(fused.get("confidence", "N/A")) + '</div></body></html>'

    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": "attachment; filename=chronovisor_report.html"},
    )


@app.get("/api/history")
async def get_history():
    return {"count": len(scan_history), "scans": [{k: v for k, v in s.items() if k != "result"} for s in scan_history]}


@app.get("/api/history/{index}")
async def get_history_scan(index: int):
    if 0 <= index < len(scan_history):
        return scan_history[index]["result"]
    raise HTTPException(status_code=404, detail="Scan not found")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_sessions = {}
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "chat":
                session_id = msg.get("session_id", "ws_default")
                if session_id not in ws_sessions:
                    ws_sessions[session_id] = []
                scan_context = None
                scan_idx = msg.get("scan_index")
                if scan_idx is not None and 0 <= scan_idx < len(scan_history):
                    scan_context = scan_history[scan_idx].get("result", {})
                elif scan_history:
                    scan_context = scan_history[-1].get("result", {})
                result = await gemini.chat(msg.get("message", ""), scan_context, ws_sessions[session_id])
                if "reply" in result:
                    ws_sessions[session_id].append({"role": "user", "content": msg.get("message", "")})
                    ws_sessions[session_id].append({"role": "assistant", "content": result["reply"]})
                    ws_sessions[session_id] = ws_sessions[session_id][-20:]
                await websocket.send_json(result)
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass


@app.post("/api/gemini/interpret-signal")
async def interpret_signal(req: AIInterpretRequest):
    if not gemini.initialized:
        return {"error": "LLM not initialized. Set LLM_PROVIDER and API key in .env"}
    return await gemini.interpret_signal_patterns(req.signal_data, req.spectral_data)


@app.post("/api/gemini/interpret-environmental")
async def interpret_environmental(req: AIInterpretRequest):
    if not gemini.initialized:
        return {"error": "LLM not initialized. Set LLM_PROVIDER and API key in .env"}
    return await gemini.interpret_environmental(req.env_data)


@app.post("/api/gemini/synthesize-crossref")
async def synthesize_crossref(req: AIInterpretRequest):
    if not gemini.initialized:
        return {"error": "LLM not initialized. Set LLM_PROVIDER and API key in .env"}
    return await gemini.synthesize_crossref(
        pleiades=req.pleiades,
        wikidata=req.wikidata,
        gbif=req.gbif,
        magnetic=req.magnetic,
        other_db=req.other,
    )


@app.get("/api/llm/status")
async def llm_status():
    import os
    provider = gemini.provider
    from pipeline.gemini_analyzer import PROVIDERS
    cfg = PROVIDERS.get(provider, PROVIDERS["cerebras"])
    env_val = os.getenv(cfg["env_key"], "")
    return {
        "initialized": gemini.initialized,
        "provider": gemini.provider,
        "model": gemini.model_name,
        "env_key": cfg["env_key"],
        "env_len": len(env_val),
        "env_empty": not env_val,
        "env_starts_your": env_val.startswith("your-"),
    }


def generate_summary(anomalies, structural, temporal, spectral):
    findings = []
    confidence = "low"
    struct_score = structural.get("structural_probability", 0)
    if struct_score > 70:
        findings.append("HIGH probability of buried structures detected")
        confidence = "high"
    elif struct_score > 40:
        findings.append("Moderate anomaly signatures - possible buried features")
        confidence = "medium"
    if anomalies:
        findings.append(str(len(anomalies)) + " satellite anomalies detected")
        veg = [a for a in anomalies if a.get("type") == "vegetation_anomaly"]
        th = [a for a in anomalies if a.get("type") == "thermal_anomaly"]
        if veg:
            findings.append("Vegetation stress pattern - possible subsurface structure")
        if th:
            findings.append("Thermal anomalies - possible stone/void beneath surface")
    change_points = temporal.get("change_points", [])
    if change_points:
        findings.append(str(len(change_points)) + " temporal change events detected")
    interp = spectral.get("interpretation", [])
    findings.extend(interp[:2])
    return {
        "findings": findings,
        "confidence": confidence,
        "recommendation": "Deploy ground-penetrating radar" if confidence in ["high", "medium"] else "Collect more data",
        "archaeological_potential": struct_score,
    }


if __name__ == "__main__":
    import uvicorn
    from core.config import API_HOST, API_PORT
    satellite.initialize()
    ai.load_models()
    gemini.initialize()
    print(f"Starting CHRONOVISOR on http://localhost:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)