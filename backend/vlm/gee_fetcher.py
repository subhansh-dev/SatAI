"""
SatAI — GEE Satellite Image Fetcher
Fetches Sentinel-2 (optical) and Sentinel-1 (SAR) imagery from Google Earth Engine.
Returns base64-encoded images ready for VLM analysis.
"""
import base64
import io
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("satai.gee")

try:
    import ee
    EE_AVAILABLE = True
except ImportError:
    EE_AVAILABLE = False


class GEEFetcher:
    """Fetch satellite imagery from Google Earth Engine for VLM analysis."""

    def __init__(self):
        self.initialized = False
        self._init_gee()

    def _init_gee(self):
        if not EE_AVAILABLE:
            logger.warning("earthengine-api not installed. GEE fetch disabled.")
            return
        try:
            from google.oauth2 import service_account

            creds = None
            creds_json = os.getenv("GOOGLE_APPLICATION_CONTENTS", "")
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
            project_id = os.getenv("GEE_PROJECT_ID", "chronovisor-498714")

            if creds_json:
                import json
                creds_dict = json.loads(creds_json)
                creds = service_account.Credentials.from_service_account_info(
                    creds_dict, scopes=["https://www.googleapis.com/auth/earthengine.readonly"]
                )
            elif creds_path and os.path.exists(creds_path):
                creds = service_account.Credentials.from_service_account_file(
                    creds_path, scopes=["https://www.googleapis.com/auth/earthengine.readonly"]
                )

            if creds:
                ee.Initialize(creds, project=project_id)
            else:
                ee.Initialize(project=project_id)

            self.initialized = True
            logger.info("GEE initialized successfully")
        except Exception as e:
            logger.warning(f"GEE init failed: {e}")

    def fetch_sentinel2(
        self,
        lat: float,
        lon: float,
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        cloud_max: int = 20,
        scale: int = 256,
    ) -> dict:
        """Fetch Sentinel-2 optical image (true color composite)."""
        if not self.initialized:
            return self._fallback_response("Sentinel-2", lat, lon)

        try:
            point = ee.Geometry.Point([lon, lat])
            buffer = point.buffer(5000)  # 5km radius

            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(buffer)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
                .sort("CLOUDY_PIXEL_PERCENTAGE")
            )

            count = collection.size().getInfo()
            if count == 0:
                return self._fallback_response("Sentinel-2", lat, lon)

            image = collection.first()

            # True color: B4(R), B3(G), B2(B)
            vis = image.select(["B4", "B3", "B2"]).divide(10000)

            # Get thumbnail
            thumb_url = vis.getThumbURL({
                "min": 0,
                "max": 0.3,
                "dimensions": f"{scale}x{scale}",
                "region": buffer,
            })

            # Fetch the image bytes
            import urllib.request
            img_bytes = urllib.request.urlopen(thumb_url).read()
            b64 = base64.b64encode(img_bytes).decode()

            # Get metadata
            date = image.date().format("YYYY-MM-dd").getInfo()
            cloud = image.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

            return {
                "base64": b64,
                "source": "Sentinel-2",
                "type": "optical",
                "date": date,
                "cloud_pct": round(cloud, 1),
                "lat": lat,
                "lon": lon,
                "scale_m": 10,
            }
        except Exception as e:
            logger.error(f"Sentinel-2 fetch failed: {e}")
            return self._fallback_response("Sentinel-2", lat, lon)

    def fetch_sentinel1(
        self,
        lat: float,
        lon: float,
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        scale: int = 256,
    ) -> dict:
        """Fetch Sentinel-1 SAR image (VV polarization)."""
        if not self.initialized:
            return self._fallback_response("Sentinel-1", lat, lon)

        try:
            point = ee.Geometry.Point([lon, lat])
            buffer = point.buffer(5000)

            collection = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(buffer)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
                .sort("system:time_start", opt_end=False)
            )

            count = collection.size().getInfo()
            if count == 0:
                return self._fallback_response("Sentinel-1", lat, lon)

            image = collection.first()

            # VV polarization
            vis = image.select("VV")

            thumb_url = vis.getThumbURL({
                "min": -25,
                "max": 0,
                "dimensions": f"{scale}x{scale}",
                "region": buffer,
            })

            import urllib.request
            img_bytes = urllib.request.urlopen(thumb_url).read()
            b64 = base64.b64encode(img_bytes).decode()

            date = image.date().format("YYYY-MM-dd").getInfo()

            return {
                "base64": b64,
                "source": "Sentinel-1",
                "type": "sar",
                "date": date,
                "lat": lat,
                "lon": lon,
                "scale_m": 10,
            }
        except Exception as e:
            logger.error(f"Sentinel-1 fetch failed: {e}")
            return self._fallback_response("Sentinel-1", lat, lon)

    def fetch_pair(
        self,
        lat: float,
        lon: float,
        date1: str = "2024-01-01",
        date2: str = "2024-06-01",
        cloud_max: int = 20,
        scale: int = 256,
    ) -> dict:
        """Fetch two Sentinel-2 images for bi-temporal change detection."""
        if not self.initialized:
            return {
                "before": self._fallback_response("Sentinel-2", lat, lon),
                "after": self._fallback_response("Sentinel-2", lat, lon),
            }

        try:
            point = ee.Geometry.Point([lon, lat])
            buffer = point.buffer(5000)

            # Before image
            col1 = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(buffer)
                .filterDate(date1, date1[:8] + "31")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
                .sort("CLOUDY_PIXEL_PERCENTAGE")
            )

            # After image
            col2 = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(buffer)
                .filterDate(date2, date2[:8] + "31")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
                .sort("CLOUDY_PIXEL_PERCENTAGE")
            )

            import urllib.request

            def _fetch_img(collection, fallback_date):
                count = collection.size().getInfo()
                if count == 0:
                    return self._fallback_response("Sentinel-2", lat, lon)
                img = collection.first()
                vis = img.select(["B4", "B3", "B2"]).divide(10000)
                url = vis.getThumbURL({
                    "min": 0, "max": 0.3,
                    "dimensions": f"{scale}x{scale}",
                    "region": buffer,
                })
                bytes_data = urllib.request.urlopen(url).read()
                return {
                    "base64": base64.b64encode(bytes_data).decode(),
                    "source": "Sentinel-2",
                    "type": "optical",
                    "date": img.date().format("YYYY-MM-dd").getInfo(),
                    "cloud_pct": round(img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo(), 1),
                    "lat": lat, "lon": lon, "scale_m": 10,
                }

            return {
                "before": _fetch_img(col1, date1),
                "after": _fetch_img(col2, date2),
            }
        except Exception as e:
            logger.error(f"Bi-temporal fetch failed: {e}")
            return {
                "before": self._fallback_response("Sentinel-2", lat, lon),
                "after": self._fallback_response("Sentinel-2", lat, lon),
            }

    def fetch_crossmodal(
        self,
        lat: float,
        lon: float,
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        scale: int = 256,
    ) -> dict:
        """Fetch co-registered optical (Sentinel-2) + SAR (Sentinel-1) pair."""
        optical = self.fetch_sentinel2(lat, lon, start_date, end_date, scale=scale)
        sar = self.fetch_sentinel1(lat, lon, start_date, end_date, scale=scale)
        return {"optical": optical, "sar": sar}

    def _fallback_response(self, source: str, lat: float, lon: float) -> dict:
        return {
            "base64": "",
            "source": source,
            "type": "optical" if "2" in source else "sar",
            "date": "",
            "lat": lat,
            "lon": lon,
            "error": "GEE not connected — upload images manually",
            "mock": True,
        }


# Singleton
gee = GEEFetcher()
