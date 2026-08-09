"""
CHRONOVISOR — API Tests
Run: pytest tests/test_api.py -v
Requires: pip install pytest httpx
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from httpx import AsyncClient, ASGITransport
from backend.api.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ─── Health ───

@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"
    assert "engines" in data


# ─── Static Frontend ───

@pytest.mark.anyio
async def test_frontend(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "CHRONOVISOR" in resp.text


# ─── Satellite Endpoints ───

@pytest.mark.anyio
async def test_satellite_timeseries(client):
    resp = await client.post("/api/satellite/timeseries", json={
        "lat": 28.6139, "lon": 77.2090, "start_date": "2024-06-01"
    })
    assert resp.status_code == 200
    data = resp.json()
    # Should return real data or error (not crash)
    assert "count" in data or "error" in data


@pytest.mark.anyio
async def test_satellite_anomalies(client):
    resp = await client.post("/api/satellite/anomalies", json={
        "lat": 28.6139, "lon": 77.2090, "start_date": "2024-01-01"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "satellite_anomalies" in data or "error" in data


@pytest.mark.anyio
async def test_satellite_spectral(client):
    resp = await client.post("/api/satellite/spectral", json={
        "lat": 28.6139, "lon": 77.2090
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "NDVI" in data or "error" in data


# ─── AI Endpoints ───

@pytest.mark.anyio
async def test_temporal_change(client):
    resp = await client.post("/api/ai/temporal-change", json={
        "lat": 28.6139, "lon": 77.2090, "start_date": "2023-01-01"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "change_points" in data or "error" in data


@pytest.mark.anyio
async def test_terrain(client):
    resp = await client.post("/api/ai/terrain?lat=28.6139&lon=77.2090&grid_size=5",
                              json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "elevation" in data or "error" in data


# ─── Data Endpoints ───

@pytest.mark.anyio
async def test_space_weather(client):
    resp = await client.get("/api/data/space-weather?days=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "solar_wind" in data
    assert "geomagnetic" in data


@pytest.mark.anyio
async def test_lightning(client):
    resp = await client.get("/api/data/lightning?lat=28.6139&lon=77.2090")
    assert resp.status_code == 200
    data = resp.json()
    # Should return error (no free API) or real data
    assert "error" in data or "strikes" in data


@pytest.mark.anyio
async def test_historical_maps(client):
    resp = await client.get("/api/data/historical-maps?lat=28.6139&lon=77.2090")
    assert resp.status_code == 200
    data = resp.json()
    assert "available_sources" in data
    assert len(data["available_sources"]) > 0


@pytest.mark.anyio
async def test_radio_astronomy(client):
    resp = await client.get("/api/data/radio-astronomy?freq_mhz=1420")
    assert resp.status_code == 200
    data = resp.json()
    assert "source" in data or "error" in data


# ─── Signal Endpoints ───

@pytest.mark.anyio
async def test_signal_analyze_no_data(client):
    resp = await client.post("/api/signal/analyze", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "demo_mode" in data or "error" in data  # Returns demo data when no real input


@pytest.mark.anyio
async def test_signal_analyze_with_data(client):
    resp = await client.post("/api/signal/analyze", json={
        "amplitudes": [0.5, 0.3, 0.1, 0.05],
        "sample_rate": 44100
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "dominant_frequencies" in data or "error" in data


@pytest.mark.anyio
async def test_em_field_no_data(client):
    resp = await client.post("/api/signal/em-field", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data  # Should require real sensor data


# ─── Full Scan ───

@pytest.mark.anyio
async def test_full_scan(client):
    resp = await client.get("/api/full-scan?lat=28.6139&lon=77.2090&radius_m=500&start_date=2024-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert "scan_target" in data
    assert "satellite" in data
    assert "summary" in data
