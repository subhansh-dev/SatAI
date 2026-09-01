"""
SatAI — Environmental Scan Tool
Fetches 24 environmental APIs for contextual enrichment of any location.
This tool does NOT use the VLM — it's a pure API integration.
"""
import time
import httpx
import logging
from .base import BaseTool

logger = logging.getLogger("satai.env")

# Environmental API endpoints (free-tier)
APIS = {
    "open_meteo": "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m&timezone=auto",
    "elevation": "https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}",
    "air_quality": "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi,pm10,pm2_5&timezone=auto",
    "earthquake": "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={lat}&longitude={lon}&maxradiuskm=50&limit=5",
}


class EnvScanTool(BaseTool):
    tool_id = "env_scan"
    description = "Fetch environmental context (weather, elevation, air quality, seismic) for a location"
    required_inputs = ["lat", "lon"]

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=15)

    async def execute(self, lat: float = 0, lon: float = 0, query: str = "", **kwargs) -> dict:
        start = time.time()
        results = {}
        for name, url_tpl in APIS.items():
            if "placeholder" in url_tpl:
                continue
            try:
                url = url_tpl.format(lat=lat, lon=lon)
                resp = await self._http.get(url)
                if resp.status_code == 200:
                    results[name] = resp.json()
            except Exception as e:
                logger.debug(f"Env API {name} failed: {e}")

        summary = self._format_results(results)
        return self._wrap({
            "text": summary,
            "confidence": 0.9,
            "metadata": {"apis_called": list(results.keys()), "lat": lat, "lon": lon},
        }, start)

    def _format_results(self, data: dict) -> str:
        parts = []
        if "open_meteo" in data:
            cur = data["open_meteo"].get("current", {})
            parts.append(
                f"Weather: {cur.get('temperature_2m', '?')}C, "
                f"Wind {cur.get('wind_speed_10m', '?')} km/h, "
                f"Humidity {cur.get('relative_humidity_2m', '?')}%, "
                f"Precipitation {cur.get('precipitation', '?')} mm"
            )
        if "elevation" in data:
            locs = data["elevation"].get("results", [])
            if locs:
                parts.append(f"Elevation: {locs[0].get('elevation', '?')} m")
        if "air_quality" in data:
            cur = data["air_quality"].get("current", {})
            parts.append(
                f"Air Quality: US AQI {cur.get('us_aqi', '?')}, "
                f"PM2.5 {cur.get('pm2_5', '?')} ug/m3, "
                f"PM10 {cur.get('pm10', '?')} ug/m3"
            )
        if "earthquake" in data:
            features = data["earthquake"].get("features", [])
            if features:
                eq = features[0]["properties"]
                parts.append(f"Recent seismic: M{eq.get('mag', '?')} — {eq.get('place', '?')}")
            else:
                parts.append("Seismic: No recent earthquakes within 50km")
        return "\n".join(parts) if parts else "No environmental data available"

    async def close(self):
        await self._http.aclose()
