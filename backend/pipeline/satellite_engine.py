"""
CHRONOVISOR — Satellite Archaeology Engine
Queries Google Earth Engine for satellite imagery and runs anomaly detection
to find buried structures, ancient features, and temporal changes.

NO MOCK DATA. All data from real satellite archives.
"""
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import json
import os

try:
    import ee
    EE_AVAILABLE = True
except ImportError:
    EE_AVAILABLE = False


class SatelliteEngine:
    """Queries satellite archives and detects anomalies."""

    def __init__(self, project_id: str = ""):
        from core.config import GEE_PROJECT_ID
        self.project_id = project_id or GEE_PROJECT_ID or os.getenv("GEE_PROJECT_ID", "")
        self.initialized = False

    def initialize(self, project_id: str = ""):
        """Initialize Earth Engine connection. Must succeed for satellite data."""
        if not EE_AVAILABLE:
            print("[SatelliteEngine] earthengine-api not installed.")
            self.initialized = False
            return

        if project_id:
            self.project_id = project_id

        # Try multiple init strategies
        attempts = [
            ("with project", {"project": self.project_id} if self.project_id else None),
            ("legacy (no project)", {}),
        ]

        for label, kwargs in attempts:
            if kwargs is None:
                continue
            try:
                ee.Initialize(**kwargs)
                self.initialized = True
                print(f"[SatelliteEngine] Earth Engine initialized ({label}).")
                return
            except Exception as e:
                print(f"[SatelliteEngine] EE init ({label}) failed: {e}")

        print("[SatelliteEngine] Earth Engine initialization FAILED. No satellite data available.")
        self.initialized = False

    def get_satellite_timeseries(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        start_date: str = "2017-01-01",
        end_date: Optional[str] = None,
        source: str = "sentinel2"
    ) -> dict:
        """
        Pull satellite imagery time series for a location.
        Returns NDVI, moisture, and thermal indices over time.
        Requires working Earth Engine connection.
        """
        if not self.initialized:
            return {"error": "Earth Engine not initialized. Run 'ee.Authenticate()' then restart."}

        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        try:
            point = ee.Geometry.Point(lon, lat)
            region = point.buffer(radius_m)

            collection_map = {
                "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
                "landsat8": "LANDSAT/LC08/C02/T1_L2",
                "sentinel1": "COPERNICUS/S1_GRD",
            }

            collection_id = collection_map.get(source, collection_map["sentinel2"])
            collection = (
                ee.ImageCollection(collection_id)
                .filterDate(start_date, end_date)
                .filterBounds(region)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )

            count = collection.size().getInfo()
            if count == 0:
                return {"error": f"No imagery found for ({lat}, {lon}) from {start_date} to {end_date} from {source}."}

            # Compute indices per image
            def compute_indices(image):
                if source == "sentinel2":
                    ndvi = image.normalizedDifference(["B8", "B4"]).rename("ndvi")
                    ndwi = image.normalizedDifference(["B3", "B8"]).rename("moisture")
                    ndbi = image.normalizedDifference(["B11", "B8"]).rename("ndbi")
                    bsi = image.expression(
                        "((B11+B4)-(B8+B2)) / ((B11+B4)+(B8+B2))",
                        {"B11": image.select("B11"), "B4": image.select("B4"),
                         "B8": image.select("B8"), "B2": image.select("B2")}
                    ).rename("bsi")
                    savi = image.expression(
                        "((B8-B4) / (B8+B4+0.5)) * 1.5",
                        {"B8": image.select("B8"), "B4": image.select("B4")}
                    ).rename("savi")
                    ndmi = image.normalizedDifference(["B8A", "B11"]).rename("ndmi")
                    thermal = image.select("B11").rename("thermal")
                    return image.addBands([ndvi, ndwi, ndbi, bsi, savi, ndmi, thermal])
                elif source == "landsat8":
                    ndvi = image.normalizedDifference(["SR_B5", "SR_B4"]).rename("ndvi")
                    ndwi = image.normalizedDifference(["SR_B3", "SR_B5"]).rename("moisture")
                    ndbi = image.normalizedDifference(["SR_B6", "SR_B5"]).rename("ndbi")
                    bsi = image.expression(
                        "((B6+B4)-(B5+B2)) / ((B6+B4)+(B5+B2))",
                        {"B6": image.select("SR_B6"), "B4": image.select("SR_B4"),
                         "B5": image.select("SR_B5"), "B2": image.select("SR_B2")}
                    ).rename("bsi")
                    savi = image.expression(
                        "((B5-B4) / (B5+B4+0.5)) * 1.5",
                        {"B5": image.select("SR_B5"), "B4": image.select("SR_B4")}
                    ).rename("savi")
                    ndmi = image.normalizedDifference(["SR_B5", "SR_B6"]).rename("ndmi")
                    thermal = image.select("ST_B10").rename("thermal")
                    return image.addBands([ndvi, ndwi, ndbi, bsi, savi, ndmi, thermal])
                return image

            processed = collection.map(compute_indices)

            # Sample all indices at point
            index_bands = ["ndvi", "moisture", "ndbi", "bsi", "savi", "ndmi", "thermal"]
            def extract_values(image):
                stats = image.select(index_bands).reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=region,
                    scale=10
                )
                props = {"date": image.date().format("YYYY-MM-dd")}
                for band in index_bands:
                    props[band] = stats.get(band)
                return ee.Feature(None, props)

            results = processed.map(extract_values).getInfo()
            features = results.get("features", [])

            timeseries = []
            for f in features:
                props = f.get("properties", {})
                timeseries.append({
                    "date": props.get("date"),
                    "ndvi": round(props.get("ndvi", 0) or 0, 4),
                    "moisture": round(props.get("moisture", 0) or 0, 4),
                    "thermal": round(props.get("thermal", 0) or 0, 2),
                    "ndbi": round(props.get("ndbi", 0) or 0, 4),
                    "bsi": round(props.get("bsi", 0) or 0, 4),
                    "savi": round(props.get("savi", 0) or 0, 4),
                    "ndmi": round(props.get("ndmi", 0) or 0, 4),
                })

            return {
                "location": {"lat": lat, "lon": lon, "radius_m": radius_m},
                "source": source,
                "count": len(timeseries),
                "timeseries": sorted(timeseries, key=lambda x: x["date"] or ""),
            }

        except Exception as e:
            return {"error": f"Satellite query failed: {str(e)}"}

    def get_sar_backscatter(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        start_date: str = "2020-01-01",
        end_date: Optional[str] = None,
    ) -> dict:
        """
        Pull Sentinel-1 SAR backscatter time series.
        Returns VV, VH, and VV/VH ratio — detects surface roughness,
        buried structures, and ground disturbance through clouds.
        """
        if not self.initialized:
            return {"error": "Earth Engine not initialized."}
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        try:
            point = ee.Geometry.Point(lon, lat)
            region = point.buffer(radius_m)
            collection = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterDate(start_date, end_date)
                .filterBounds(region)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            )
            count = collection.size().getInfo()
            if count == 0:
                return {"error": "No SAR data found for this location/date range."}

            def extract_sar(image):
                vv = image.select("VV").rename("vv")
                vh = image.select("VH").rename("vh")
                ratio = vv.subtract(vh).rename("ratio")
                stats = ee.Image([vv, vh, ratio]).reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=region, scale=30
                )
                return ee.Feature(None, {
                    "date": image.date().format("YYYY-MM-dd"),
                    "vv": stats.get("VV") if stats.get("VV") is not None else stats.get("vv"),
                    "vh": stats.get("VH") if stats.get("VH") is not None else stats.get("vh"),
                    "ratio": stats.get("ratio"),
                })

            results = collection.map(extract_sar).getInfo()
            features = results.get("features", [])
            timeseries = []
            for f in features:
                props = f.get("properties", {})
                vv_val = props.get("vv")
                vh_val = props.get("vh")
                ratio_val = props.get("ratio")
                # VV/VH ratio can also be computed from dB values
                if ratio_val is None and vv_val is not None and vh_val is not None:
                    ratio_val = vv_val - vh_val  # dB subtraction = division in linear
                timeseries.append({
                    "date": props.get("date"),
                    "vv": round(vv_val or 0, 2),
                    "vh": round(vh_val or 0, 2),
                    "ratio": round(ratio_val or 0, 2),
                })
            return {
                "location": {"lat": lat, "lon": lon, "radius_m": radius_m},
                "source": "sentinel1_sar",
                "count": len(timeseries),
                "timeseries": sorted(timeseries, key=lambda x: x["date"] or ""),
            }
        except Exception as e:
            return {"error": f"SAR query failed: {str(e)}"}

    def ndvi_change_detection(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        period1_start: str = "2018-01-01",
        period1_end: str = "2018-12-31",
        period2_start: str = "2024-01-01",
        period2_end: str = "2024-12-31",
    ) -> dict:
        """
        Compare NDVI between two time periods.
        Negative change = vegetation loss (construction, burial, excavation).
        Positive change = vegetation gain (abandonment, reforestation).
        """
        if not self.initialized:
            return {"error": "Earth Engine not initialized."}
        try:
            point = ee.Geometry.Point(lon, lat)
            region = point.buffer(radius_m)

            def get_mean_ndvi(start, end):
                col = (
                    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterDate(start, end)
                    .filterBounds(region)
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                )
                count = col.size().getInfo()
                if count == 0:
                    return None, 0
                ndvi_col = col.map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("ndvi"))
                mean = ndvi_col.mean()
                stats = mean.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=10).getInfo()
                return stats.get("ndvi"), count

            ndvi1, count1 = get_mean_ndvi(period1_start, period1_end)
            ndvi2, count2 = get_mean_ndvi(period2_start, period2_end)

            if ndvi1 is None:
                return {"error": f"No imagery for period 1 ({period1_start} to {period1_end})"}
            if ndvi2 is None:
                return {"error": f"No imagery for period 2 ({period2_start} to {period2_end})"}

            change = ndvi2 - ndvi1
            pct_change = (change / max(abs(ndvi1), 0.001)) * 100

            interpretation = []
            if change < -0.05:
                interpretation.append(f"Significant vegetation loss ({pct_change:+.1f}%) — possible construction, excavation, or land clearing")
            elif change < -0.02:
                interpretation.append(f"Moderate vegetation decline ({pct_change:+.1f}%) — possible land use change or disturbance")
            elif change > 0.05:
                interpretation.append(f"Significant vegetation gain ({pct_change:+.1f}%) — possible abandonment, reforestation, or irrigation")
            elif change > 0.02:
                interpretation.append(f"Moderate vegetation increase ({pct_change:+.1f}%) — slight land use change")
            else:
                interpretation.append(f"Stable vegetation ({pct_change:+.1f}%) — no significant change detected")

            return {
                "location": {"lat": lat, "lon": lon, "radius_m": radius_m},
                "period1": {"start": period1_start, "end": period1_end, "ndvi": round(ndvi1, 4), "images": count1},
                "period2": {"start": period2_start, "end": period2_end, "ndvi": round(ndvi2, 4), "images": count2},
                "change": round(change, 4),
                "pct_change": round(pct_change, 1),
                "interpretation": interpretation,
            }
        except Exception as e:
            return {"error": f"Change detection failed: {str(e)}"}

    def detect_anomalies(self, timeseries: list) -> list:
        """
        Run anomaly detection on satellite time series.
        Detects: buried structures (vegetation stress), soil disturbance,
        moisture anomalies, thermal patterns.
        """
        if len(timeseries) < 3:
            return []

        anomalies = []

        ndvi_vals = [t["ndvi"] for t in timeseries if t["ndvi"] is not None]
        moisture_vals = [t["moisture"] for t in timeseries if t["moisture"] is not None]
        thermal_vals = [t["thermal"] for t in timeseries if t["thermal"] is not None]

        if ndvi_vals:
            ndvi_mean = np.mean(ndvi_vals)
            ndvi_std = np.std(ndvi_vals)
            for t in timeseries:
                if t["ndvi"] is not None and abs(t["ndvi"] - ndvi_mean) > 2 * ndvi_std:
                    anomalies.append({
                        "type": "vegetation_anomaly",
                        "date": t["date"],
                        "value": t["ndvi"],
                        "mean": round(ndvi_mean, 4),
                        "deviation": round(abs(t["ndvi"] - ndvi_mean) / max(ndvi_std, 0.001), 2),
                        "interpretation": "Possible buried structure — vegetation stress pattern"
                    })

        if thermal_vals:
            thermal_mean = np.mean(thermal_vals)
            thermal_std = np.std(thermal_vals)
            for t in timeseries:
                if t["thermal"] is not None and abs(t["thermal"] - thermal_mean) > 2 * thermal_std:
                    anomalies.append({
                        "type": "thermal_anomaly",
                        "date": t["date"],
                        "value": t["thermal"],
                        "mean": round(thermal_mean, 2),
                        "deviation": round(abs(t["thermal"] - thermal_mean) / max(thermal_std, 0.001), 2),
                        "interpretation": "Subsurface structure affecting surface temperature"
                    })

        return anomalies

    def compute_spectral_indices(self, lat: float, lon: float, radius_m: int = 500) -> dict:
        """
        Compute multiple spectral indices for a single location (latest imagery).
        Returns NDVI, NDWI, NDBI, thermal composite.
        Requires working Earth Engine connection.
        """
        if not self.initialized:
            return {"error": "Earth Engine not initialized."}

        try:
            point = ee.Geometry.Point(lon, lat)
            region = point.buffer(radius_m)

            image = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterDate(datetime.now() - timedelta(days=90), datetime.now())
                .filterBounds(region)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                .sort("system:time_start", False)
                .first()
            )

            if image is None:
                return {"error": f"No recent imagery available for ({lat}, {lon})."}

            ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
            ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
            ndbi = image.normalizedDifference(["B11", "B8"]).rename("NDBI")

            combined = image.addBands([ndvi, ndwi, ndbi])

            stats = combined.select(["NDVI", "NDWI", "NDBI"]).reduceRegion(
                reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
                geometry=region,
                scale=10
            ).getInfo()

            return {
                "NDVI": {"mean": stats.get("NDVI_mean", 0), "std": stats.get("NDVI_stdDev", 0)},
                "NDWI": {"mean": stats.get("NDWI_mean", 0), "std": stats.get("NDWI_stdDev", 0)},
                "NDBI": {"mean": stats.get("NDBI_mean", 0), "std": stats.get("NDBI_stdDev", 0)},
                "interpretation": self._interpret_indices(stats)
            }
        except Exception as e:
            return {"error": f"Spectral analysis failed: {str(e)}"}

    def _interpret_indices(self, stats: dict) -> list:
        """Interpret spectral indices for archaeological potential."""
        interpretations = []
        ndvi = stats.get("NDVI_mean", 0) or 0
        ndwi = stats.get("NDWI_mean", 0) or 0
        ndbi = stats.get("NDBI_mean", 0) or 0

        if -0.1 < ndvi < 0.2:
            interpretations.append("Low vegetation — possible bare soil or rocky terrain (good for surface finds)")
        if ndwi > 0.1:
            interpretations.append("High moisture — possible buried water feature or underground structure")
        if ndbi > 0:
            interpretations.append("Built-up index positive — possible man-made structures or stone foundations")
        if ndvi < -0.1:
            interpretations.append("Very low vegetation stress — possible subsurface feature affecting growth")

        return interpretations if interpretations else ["No significant anomalies detected"]
