"""
CHRONOVISOR — Data Ingestion Layer
Pulls data from public sources: NOAA, NASA POWER, WWLLN, and historical records.

NO MOCK DATA. All data from real APIs. Errors returned when sources unavailable.
"""
import json
import os
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path


class DataIngestion:
    """Ingest electromagnetic and environmental data from public APIs."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        import requests as _requests
        self.session = _requests.Session()
        self.session.headers.update({"User-Agent": "Chronovisor/0.3"})

    def get_noaa_space_weather(self, days_back: int = 7) -> dict:
        """
        Fetch NOAA space weather data — solar wind density, speed, temperature
        from the DSCOVR satellite at L1 Lagrange point.
        Real data from https://services.swpc.noaa.gov/
        """
        import requests

        try:
            url = "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return {"error": f"NOAA API returned HTTP {resp.status_code}"}

            raw = resp.json()
            if not raw or len(raw) < 2:
                return {"error": "NOAA API returned empty data"}

            headers = raw[0]
            data = raw[1:]

            # Filter to requested time range
            cutoff = datetime.utcnow() - timedelta(days=days_back)
            solar_wind = []
            for row in data:
                if len(row) >= 4:
                    try:
                        ts = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                        if ts.replace(tzinfo=None) < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass
                    solar_wind.append({
                        "timestamp": row[0],
                        "density": float(row[1]) if row[1] else None,
                        "speed": float(row[2]) if row[2] else None,
                        "temperature": float(row[3]) if row[3] else None,
                    })

            return {
                "source": "NOAA DSCOVR (L1 Lagrange Point)",
                "type": "solar_wind",
                "count": len(solar_wind),
                "data": solar_wind[-200:],  # Last 200 readings
                "interpretation": self._interpret_solar_wind(solar_wind)
            }
        except requests.exceptions.Timeout:
            return {"error": "NOAA DSCOVR API timed out (15s). NOAA servers may be slow."}
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot reach NOAA SWPC API. Check internet connection."}
        except Exception as e:
            return {"error": f"NOAA data fetch failed: {str(e)}"}

    def get_geomagnetic_indices(self, days_back: int = 7) -> dict:
        """
        Fetch Kp index (planetary geomagnetic activity) from NOAA.
        Kp ranges 0-9: 0-2 quiet, 3-4 unsettled, 5+ storm.
        """
        import requests

        try:
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return {"error": f"NOAA Kp API returned HTTP {resp.status_code}"}

            raw = resp.json()
            if not raw:
                return {"error": "NOAA Kp API returned empty data"}

            kp_data = []
            for row in raw:
                if isinstance(row, dict) and "kp" in row:
                    kp_data.append({
                        "time_tag": row.get("time_tag"),
                        "kp_index": float(row["kp"]) if row["kp"] is not None else None,
                        "observed": row.get("observed"),
                        "noaa_scale": row.get("noaa_scale"),
                    })

            return {
                "source": "NOAA SWPC (Planetary K-index)",
                "type": "geomagnetic_kp",
                "count": len(kp_data),
                "data": kp_data,
                "current_kp": kp_data[-1]["kp_index"] if kp_data else None,
                "interpretation": self._interpret_kp(kp_data)
            }
        except requests.exceptions.Timeout:
            return {"error": "NOAA Kp API timed out."}
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot reach NOAA SWPC API."}
        except Exception as e:
            return {"error": f"Kp index fetch failed: {str(e)}"}

    def get_lightning_data(self, lat: float, lon: float, radius_km: int = 100) -> dict:
        """
        Get real lightning strike data from PocketWorld (Blitzortung community network).
        Free, no API key required.
        """
        import requests

        try:
            resp = requests.get("https://pocketworld.org/api/lightning", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                strikes = data.get("lightning", data.get("strikes", data.get("data", [])))
                if isinstance(strikes, list):
                    nearby = []
                    for s in strikes:
                        slat = s.get("lat", 0)
                        slon = s.get("lon", 0)
                        dist = np.sqrt((slat - lat)**2 + (slon - lon)**2) * 111
                        if dist <= radius_km:
                            nearby.append({
                                "lat": slat, "lon": slon,
                                "time": s.get("datetime", s.get("time", "")),
                                "quality": s.get("quality", "unknown"),
                                "distance_km": round(dist, 1),
                            })
                    return {
                        "source": "Blitzortung/PocketWorld (real-time)",
                        "location": {"lat": lat, "lon": lon, "radius_km": radius_km},
                        "strikes": sorted(nearby, key=lambda x: x["distance_km"])[:50],
                        "total_strikes": len(nearby),
                        "interpretation": self._interpret_lightning(len(nearby)),
                    }
        except Exception:
            pass

        return {
            "source": "Blitzortung/PocketWorld",
            "location": {"lat": lat, "lon": lon, "radius_km": radius_km},
            "strikes": [],
            "total_strikes": 0,
            "error": "Lightning data temporarily unavailable.",
            "interpretation": ["No lightning data available at this time."],
        }

    def _interpret_lightning(self, count: int) -> list:
        if count > 20:
            return ["High lightning activity — strong electrical storms. EM interference expected.", "Natural EM noise may mask subtle archaeological signals."]
        elif count > 5:
            return ["Moderate lightning activity — some EM noise expected in signal data."]
        elif count > 0:
            return ["Low lightning activity — minimal EM interference."]
        return ["No recent lightning — clean EM conditions for signal analysis."]
            },
            "recommendation": "Apply for WWLLN research access (free) or integrate Vaisala GLD360 API key."
        }

    def get_radio_astronomy_archive(self, freq_mhz: float = 1420, lat: float = None, lon: float = None) -> dict:
        """
        Fetch real solar/EM environmental data from NASA POWER API.
        NASA POWER provides solar radiation, surface EM, and atmospheric data
        for any coordinate on Earth. Real data, no mock.
        """
        import requests

        # Use the last 30 days for environmental data
        end = datetime.now()
        start = end - timedelta(days=30)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        # Use provided coordinates or default to None (caller must provide)
        if lat is None or lon is None:
            return {"error": "Coordinates required. Pass lat and lon parameters.", "freq_mhz": freq_mhz}

        try:
            url = (
                f"https://power.larc.nasa.gov/api/temporal/daily/point?"
                f"parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DIFF,"
                f"ALLSKY_SFC_LW_DWN,T2M,T2M_MAX,T2M_MIN,WS2M,PRECTOTCORR"
                f"&community=RE&longitude={lon}&latitude={lat}"
                f"&start={start_str}&end={end_str}&format=JSON"
            )
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                return {"error": f"NASA POWER API returned HTTP {resp.status_code}"}

            data = resp.json()
            params = data.get("properties", {}).get("parameter", {})

            # Extract solar radiation data (closest to radio astronomy)
            solar = params.get("ALLSKY_SFC_SW_DWN", {})
            clear_sky = params.get("CLRSKY_SFC_SW_DWN", {})

            dates = sorted(solar.keys())[-30:]  # Last 30 days
            solar_values = [solar.get(d, None) for d in dates]
            clear_values = [clear_sky.get(d, None) for d in dates]

            # Filter out fill values (-999)
            solar_clean = [v for v in solar_values if v is not None and v > -900]
            clear_clean = [v for v in clear_values if v is not None and v > -900]

            return {
                "source": "NASA POWER API (LARC)",
                "type": "solar_radiation_environmental",
                "center_frequency_mhz": freq_mhz,
                "location": {"lat": lat, "lon": lon},
                "period": f"{start_str} to {end_str}",
                "data_points": len(dates),
                "solar_radiation": {
                    "dates": dates,
                    "allsky_sw_dn_wm2": [round(v, 2) if v and v > -900 else None for v in solar_values],
                    "clearsky_sw_dn_wm2": [round(v, 2) if v and v > -900 else None for v in clear_values],
                    "mean_wm2": round(float(np.mean(solar_clean)), 2) if solar_clean else None,
                    "max_wm2": round(float(np.max(solar_clean)), 2) if solar_clean else None,
                },
                "atmospheric": {
                    "temperature_2m": {k: round(v, 2) if v and v > -900 else None for k, v in params.get("T2M", {}).items()},
                    "wind_speed_2m": {k: round(v, 2) if v and v > -900 else None for k, v in params.get("WS2M", {}).items()},
                    "precipitation": {k: round(v, 2) if v and v > -900 else None for k, v in params.get("PRECTOTCORR", {}).items()},
                },
                "interpretation": self._interpret_solar_radiation(solar_clean, freq_mhz)
            }
        except requests.exceptions.Timeout:
            return {"error": "NASA POWER API timed out (20s). Servers may be overloaded."}
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot reach NASA POWER API. Check internet connection."}
        except Exception as e:
            return {"error": f"NASA POWER data fetch failed: {str(e)}"}

    def get_nasa_power(self, lat: float, lon: float, days_back: int = 30) -> dict:
        """
        Fetch solar radiation and environmental data from NASA POWER for specific coordinates.
        Real data — surface solar irradiance, temperature, wind, precipitation.
        """
        import requests

        end = datetime.now()
        start = end - timedelta(days=days_back)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        try:
            url = (
                f"https://power.larc.nasa.gov/api/temporal/daily/point?"
                f"parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_SFC_LW_DWN,"
                f"T2M,T2M_MAX,T2M_MIN,WS2M,PRECTOTCORR,RH2M,PS"
                f"&community=RE&longitude={lon}&latitude={lat}"
                f"&start={start_str}&end={end_str}&format=JSON"
            )
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                return {"error": f"NASA POWER API returned HTTP {resp.status_code}"}

            data = resp.json()
            params = data.get("properties", {}).get("parameter", {})

            solar = params.get("ALLSKY_SFC_SW_DWN", {})
            dates = sorted(solar.keys())

            result = {}
            for param_name, param_data in params.items():
                values = [param_data.get(d, None) for d in dates]
                clean = [v for v in values if v is not None and v > -900]
                result[param_name] = {
                    "dates": dates,
                    "values": [round(v, 2) if v and v > -900 else None for v in values],
                    "mean": round(float(np.mean(clean)), 2) if clean else None,
                    "min": round(float(np.min(clean)), 2) if clean else None,
                    "max": round(float(np.max(clean)), 2) if clean else None,
                }

            return {
                "source": "NASA POWER API (LARC)",
                "location": {"lat": lat, "lon": lon},
                "period": f"{start_str} to {end_str}",
                "data_points": len(dates),
                "parameters": result,
            }
        except requests.exceptions.Timeout:
            return {"error": "NASA POWER API timed out."}
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot reach NASA POWER API."}
        except Exception as e:
            return {"error": f"NASA POWER fetch failed: {str(e)}"}

    def get_historical_maps(self, lat: float, lon: float) -> dict:
        """
        Return real URLs to historical map services for a location.
        These are actual map servers with WMS/tile access.
        """
        # Calculate bounding box (roughly 50km radius)
        delta = 0.5
        return {
            "location": {"lat": lat, "lon": lon},
            "available_sources": [
                {
                    "name": "Old Maps Online",
                    "url": f"https://www.oldmapsonline.org/en/#bbox={lon-delta},{lat-delta},{lon+delta},{lat+delta}",
                    "type": "historical_maps",
                    "description": "Crowdsourced collection of historical maps worldwide",
                    "wms": "https://wms.oldmapsonline.org/cgi-bin/mapserv?map=/data/omo.map"
                },
                {
                    "name": "David Rumsey Map Collection",
                    "url": "https://www.davidrumsey.com/",
                    "type": "historical_maps",
                    "description": "150,000+ historical maps, focus on 18th-19th century"
                },
                {
                    "name": "USGS Historical Topos",
                    "url": "https://ngmdb.usgs.gov/topoview/",
                    "type": "topographic",
                    "description": "Historical topographic maps of the US (1880s-present)"
                },
                {
                    "name": "Sentinel Hub EO Browser",
                    "url": f"https://apps.sentinel-hub.com/eo-browser/?zoom=12&lat={lat}&lng={lon}",
                    "type": "satellite",
                    "description": "Free satellite imagery browser with temporal coverage"
                },
                {
                    "name": "Google Earth Timelapse",
                    "url": f"https://earthengine.google.com/timelapse/#lon={lon}&lat={lat}&zoom=12",
                    "type": "satellite_timelapse",
                    "description": "1984-present annual satellite imagery timelapse"
                },
                {
                    "name": "NASA Worldview",
                    "url": f"https://worldview.earthdata.nasa.gov/?v={lon-delta},{lat-delta},{lon+delta},{lat+delta}",
                    "type": "satellite",
                    "description": "NASA near-real-time satellite imagery (MODIS, VIIRS)"
                }
            ]
        }

    def get_elevation(self, lat: float, lon: float) -> dict:
        import requests
        try:
            resp = requests.post("https://api.open-elevation.com/api/v1/lookup",
                                 json={"locations": [{"latitude": lat, "longitude": lon}]}, timeout=15)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return {"source": "Open-Elevation API (SRTM 30m)",
                            "location": {"lat": lat, "lon": lon},
                            "elevation_m": results[0].get("elevation")}
        except Exception:
            pass
        try:
            resp = requests.get(f"https://api.opentopodata.org/v1/srtm90m?locations={lat},{lon}", timeout=15)
            if resp.status_code == 200:
                r = resp.json().get("results", [{}])[0]
                return {"source": "Open Topo Data API (SRTM 90m)",
                        "location": {"lat": lat, "lon": lon},
                        "elevation_m": r.get("elevation", 0)}
        except Exception as e:
            return {"error": f"Both elevation APIs failed: {e}"}

    def get_terrain_grid(self, lat: float, lon: float, grid_size: int = 50, span_deg: float = 0.02) -> dict:
        import requests

        lats = np.linspace(lat - span_deg / 2, lat + span_deg / 2, grid_size)
        lons = np.linspace(lon - span_deg / 2, lon + span_deg / 2, grid_size)

        locations = [{"latitude": float(la), "longitude": float(lo)} for la in lats for lo in lons]

        def _build(results):
            elev = np.zeros((grid_size, grid_size))
            for i in range(grid_size):
                for j in range(grid_size):
                    elev[i][j] = results[i * grid_size + j].get("elevation", 0)
            return elev

        def _analyze(elev):
            from scipy.ndimage import maximum_filter, minimum_filter
            lmax = maximum_filter(elev, size=10)
            lmin = minimum_filter(elev, size=10)
            return np.where(elev == lmax), np.where(elev == lmin)

        def _result(elev, src, ridges, valleys):
            return {
                "source": src,
                "location": {"lat": lat, "lon": lon},
                "grid_size": grid_size,
                "elevation": elev.tolist(),
                "min_elevation": round(float(np.min(elev)), 2),
                "max_elevation": round(float(np.max(elev)), 2),
                "ridge_points": len(ridges[0]),
                "valley_points": len(valleys[0]),
                "features": {
                    "ridges": [{"x": int(ridges[1][i]), "y": int(ridges[0][i]),
                                "elevation": round(float(elev[ridges[0][i], ridges[1][i]]), 2)}
                               for i in range(min(10, len(ridges[0])))],
                    "valleys": [{"x": int(valleys[1][i]), "y": int(valleys[0][i]),
                                 "elevation": round(float(elev[valleys[0][i], valleys[1][i]]), 2)}
                                for i in range(min(10, len(valleys[0])))]
                }
            }

        # Primary: Open-Elevation
        try:
            resp = requests.post("https://api.open-elevation.com/api/v1/lookup",
                                 json={"locations": locations}, timeout=30)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if len(results) == grid_size * grid_size:
                    elev = _build(results)
                    ridges, valleys = _analyze(elev)
                    return _result(elev, "Open-Elevation API (SRTM 30m)", ridges, valleys)
        except Exception:
            pass

        # Fallback: Open Topo Data (SRTM 90m, no key needed)
        try:
            import time
            all_results = []
            for start in range(0, len(locations), 100):
                batch = locations[start:start + 100]
                coords = "|".join(f"{l['latitude']},{l['longitude']}" for l in batch)
                resp = requests.get(f"https://api.opentopodata.org/v1/srtm90m?locations={coords}", timeout=30)
                if resp.status_code == 200:
                    for r in resp.json().get("results", []):
                        all_results.append({"elevation": r.get("elevation", 0) or 0})
                else:
                    return {"error": f"Open Topo Data HTTP {resp.status_code}"}
                if start + 100 < len(locations):
                    time.sleep(0.5)

            if len(all_results) == grid_size * grid_size:
                elev = _build(all_results)
                ridges, valleys = _analyze(elev)
                return _result(elev, "Open Topo Data API (SRTM 90m)", ridges, valleys)
        except Exception as e:
            return {"error": f"Both elevation APIs failed: {e}"}

    def _interpret_solar_wind(self, data: list) -> list:
        """Interpret solar wind data for EM implications."""
        interpretations = []
        if data:
            speeds = [d["speed"] for d in data if d["speed"] is not None]
            if speeds:
                avg_speed = np.mean(speeds)
                if avg_speed > 600:
                    interpretations.append("High solar wind speed — geomagnetic storm likely, EM readings will be elevated")
                elif avg_speed > 400:
                    interpretations.append("Moderate solar wind — normal EM conditions")
                else:
                    interpretations.append("Low solar wind — quiet conditions, good for baseline EM measurements")
        return interpretations if interpretations else ["Insufficient solar wind data for interpretation"]

    def _interpret_kp(self, data: list) -> list:
        """Interpret Kp index for geomagnetic activity."""
        interpretations = []
        if data:
            kps = [d["kp_index"] for d in data if d["kp_index"] is not None]
            if kps:
                current = kps[-1]
                if current >= 5:
                    interpretations.append("GEOMAGNETIC STORM — EM measurements will be heavily affected")
                elif current >= 3:
                    interpretations.append("Active geomagnetic conditions — some EM interference expected")
                else:
                    interpretations.append("Quiet geomagnetic conditions — ideal for EM measurements")
        return interpretations if interpretations else ["No Kp data available"]

    def _interpret_solar_radiation(self, values: list, freq_mhz: float) -> list:
        """Interpret solar radiation data for EM context."""
        interpretations = []
        if values:
            mean_val = np.mean(values)
            interpretations.append(f"Mean surface solar irradiance: {mean_val:.1f} W/m²")
            if mean_val > 300:
                interpretations.append("High solar activity — strong ionospheric effects on radio propagation")
            elif mean_val > 150:
                interpretations.append("Moderate solar activity — normal radio propagation conditions")
            else:
                interpretations.append("Low solar activity — quiet EM environment")
        interpretations.append(f"Requested radio frequency: {freq_mhz} MHz (hydrogen line at 1420.405 MHz)")
        return interpretations

    def get_elevation_profile(self, lat: float, lon: float, radius_m: int = 500, direction: str = "E-W", points: int = 30) -> dict:
        """
        Extract an elevation cross-section through the terrain grid.
        direction: 'E-W' (east-west), 'N-S' (north-south), 'NE-SW', 'NW-SE'
        Reveals buried ditches, walls, roads as subtle elevation anomalies.
        """
        import requests
        span_deg = (radius_m / 111320) * 2
        half = span_deg / 2

        dirs = {
            "E-W":  ((lat, lon - half), (lat, lon + half)),
            "N-S":  ((lat + half, lon), (lat - half, lon)),
            "NE-SW":((lat + half*0.7, lon + half*0.7), (lat - half*0.7, lon - half*0.7)),
            "NW-SE":((lat + half*0.7, lon - half*0.7), (lat - half*0.7, lon + half*0.7)),
        }
        start, end = dirs.get(direction, dirs["E-W"])

        lats = np.linspace(start[0], end[0], points)
        lons = np.linspace(start[1], end[1], points)
        locations = [{"latitude": float(la), "longitude": float(lo)} for la, lo in zip(lats, lons)]

        try:
            resp = self.session.post("https://api.open-elevation.com/api/v1/lookup",
                                 json={"locations": locations}, timeout=20)
            if resp.status_code != 200:
                return {"error": f"Open-Elevation HTTP {resp.status_code}"}
            results = resp.json().get("results", [])
            elevations = [r.get("elevation", 0) for r in results]

            # Compute distances along the transect
            distances = []
            for i in range(len(lats)):
                if i == 0:
                    distances.append(0)
                else:
                    dlat = (lats[i] - lats[i-1]) * 111320
                    dlon = (lons[i] - lons[i-1]) * 111320 * math.cos(math.radians(lats[i]))
                    distances.append(round(distances[-1] + math.sqrt(dlat**2 + dlon**2), 1))

            # Detect anomalies — spots where elevation deviates from local trend
            elev_arr = np.array(elevations)
            gradient = np.abs(np.diff(elev_arr))
            mean_grad = np.mean(gradient)
            std_grad = np.std(gradient)
            anomaly_indices = [i for i in range(len(gradient)) if gradient[i] > mean_grad + 1.5 * std_grad]

            interpretation = []
            elev_range = max(elevations) - min(elevations)
            if elev_range < 2:
                interpretation.append(f"Very flat terrain ({elev_range:.1f}m range) — subtle features possible, look for micro-relief")
            elif elev_range < 10:
                interpretation.append(f"Low relief ({elev_range:.1f}m range) — gentle terrain, good for surface archaeology")
            else:
                interpretation.append(f"Significant relief ({elev_range:.1f}m range) — elevated features may be natural")

            if anomaly_indices:
                interpretation.append(f"{len(anomaly_indices)} sharp elevation break(s) detected — possible buried edge or ditch")

            return {
                "source": "Open-Elevation (SRTM 30m)",
                "direction": direction,
                "points": points,
                "distances_m": distances,
                "elevations": [round(e, 1) for e in elevations],
                "anomaly_points": len(anomaly_indices),
                "anomaly_distances": [distances[i] for i in anomaly_indices],
                "elevation_range": round(elev_range, 1),
                "interpretation": interpretation,
            }
        except Exception as e:
            return {"error": f"Elevation profile failed: {str(e)}"}

    def get_water_proximity(self, lat: float, lon: float, radius_m: int = 2000) -> dict:
        """
        Find water sources near the location using OSM Overpass API.
        Distance to water = critical archaeological factor.
        """
        try:
            r = min(radius_m, 3000)
            query = f"""[out:json][timeout:15];
            (
              way["natural"="water"](around:{r},{lat},{lon});
              way["waterway"~"river|stream|canal"](around:{r},{lat},{lon});
            );
            out center 30;"""
            resp = self.session.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=25)
            if resp.status_code != 200:
                return {"error": f"Overpass API HTTP {resp.status_code}"}

            data = resp.json()
            features = []
            for el in data.get("elements", []):
                elat = el.get("lat") or el.get("center", {}).get("lat")
                elon = el.get("lon") or el.get("center", {}).get("lon")
                if elat is None or elon is None:
                    continue
                dlat = (elat - lat) * 111320
                dlon = (elon - lon) * 111320 * math.cos(math.radians(lat))
                dist = math.sqrt(dlat**2 + dlon**2)
                tags = el.get("tags", {})
                name = tags.get("name", "")
                ftype = tags.get("water", tags.get("waterway", tags.get("natural", "water")))
                features.append({"name": name or ftype, "type": ftype, "distance_m": round(dist, 0), "lat": elat, "lon": elon})

            features.sort(key=lambda x: x["distance_m"])
            nearest = features[0]["distance_m"] if features else None

            interpretation = []
            if nearest is not None:
                if nearest < 200:
                    interpretation.append(f"Very close to water ({nearest:.0f}m) — prime settlement location")
                elif nearest < 500:
                    interpretation.append(f"Near water ({nearest:.0f}m) — plausible settlement site")
                elif nearest < 1000:
                    interpretation.append(f"Moderate distance to water ({nearest:.0f}m) — settlement possible if other water sources exist")
                else:
                    interpretation.append(f"Far from surface water ({nearest:.0f}m) — check for ancient water courses or wells")
            else:
                interpretation.append("No surface water found in search radius — check for buried channels or seasonal water")

            return {
                "source": "OpenStreetMap Overpass API",
                "search_radius_m": radius_m,
                "features_found": len(features),
                "features": features[:20],
                "nearest_water_m": nearest,
                "interpretation": interpretation,
            }
        except Exception as e:
            return {"error": f"Water proximity failed: {str(e)}"}

    def get_geological_context(self, lat: float, lon: float) -> dict:
        """
        Get geological context from soil data (ISRIC SoilGrids) + Macrostrat (North America).
        Soil composition is a direct proxy for underlying geology.
        """
        interpretation = []
        units = []
        source = "ISRIC SoilGrids"

        # Try Macrostrat first (North America coverage)
        try:
            resp = self.session.get(f"https://macrostrat.org/api/v2/units?lat={lat}&lng={lon}&format=json", timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("success", {}).get("data", [])
                if data:
                    source = "Macrostrat + ISRIC SoilGrids"
                    for u in data[:3]:
                        name = u.get("unit_name", u.get("Fm", "Unknown"))
                        t_age = u.get("t_age", "")
                        b_age = u.get("b_age", "")
                        age_str = ""
                        if b_age and t_age:
                            age_str = f"{round(float(t_age),1)}-{round(float(b_age),1)} Ma"
                        units.append({"name": name, "age": age_str, "thickness_m": u.get("max_thick", "")})
        except Exception:
            pass

        # Get soil data as geological proxy (works globally)
        soil = {}
        try:
            props = ["clay", "sand", "silt", "soc", "phh2o", "bdod"]
            prop_str = "&".join(["property=" + p for p in props])
            # Try multiple depths — surface may be null in urban areas
            for depth in ["0-5cm", "5-15cm", "15-30cm"]:
                resp = self.session.get(
                    f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={lon}&lat={lat}&{prop_str}&depth={depth}&value=mean",
                    timeout=15
                )
                if resp.status_code == 200:
                    layers = resp.json().get("properties", {}).get("layers", [])
                    for layer in layers:
                        name = layer.get("name", "")
                        for d in layer.get("depths", []):
                            if d.get("label", "") == depth:
                                mv = d.get("values", {}).get("mean")
                                if mv is not None and mv > -9000 and name not in soil:
                                    soil[name] = mv
                if soil:
                    break  # Got data, no need to try deeper
        except Exception:
            pass

        if soil:
            clay = soil.get("clay", 0) or 0
            sand = soil.get("sand", 0) or 0
            silt = soil.get("silt", 0) or 0
            source = "Macrostrat + ISRIC SoilGrids" if units else "ISRIC SoilGrids"

            if clay > 400:
                interpretation.append(f"Clay-rich soil ({clay/10:.0f}%) — fine-grained sedimentary substrate (shale, mudstone). Excellent preservation.")
            elif sand > 600:
                interpretation.append(f"Sandy soil ({sand/10:.0f}%) — coarse sedimentary substrate (sandstone, alluvium). Poor organic preservation.")
            elif silt > 500:
                interpretation.append(f"Silt-rich soil ({silt/10:.0f}%) — loess or floodplain deposits. Good for buried features.")

            ph = (soil.get("phh2o", 0) or 0) / 10.0
            if ph > 0:
                if ph > 7.5:
                    interpretation.append(f"Alkaline pH {ph:.1f} — limestone/calcrete parent material. Good bone preservation.")
                elif ph < 5.5:
                    interpretation.append(f"Acidic pH {ph:.1f} — granite/sandstone substrate. Bone/metal degrade quickly.")
                else:
                    interpretation.append(f"Neutral pH {ph:.1f} — mixed geological substrate.")
        else:
            source = source if units else "No soil data available"
            interpretation.append("Soil data unavailable (urban area or data gap). Use elevation and geological maps for context.")

        # Add elevation as geological proxy
        try:
            elev_resp = self.get_elevation(lat, lon)
            if elev_resp.get("elevation_m"):
                elev = elev_resp["elevation_m"]
                if elev > 2000:
                    interpretation.append(f"High elevation ({elev}m) — mountain/hill terrain, likely hard rock substrate")
                elif elev < 50:
                    interpretation.append(f"Low elevation ({elev}m) — coastal/floodplain, alluvial deposits likely")
        except Exception:
            pass

        if not interpretation:
            interpretation.append("Geological context inferred from available data")

        return {
            "source": source,
            "location": {"lat": lat, "lon": lon},
            "units": units,
            "soil_properties": {k: round(v, 1) for k, v in soil.items()} if soil else None,
            "interpretation": interpretation,
        }

    def get_nearby_places(self, lat: float, lon: float, radius_km: int = 50) -> dict:
        """
        Find nearby populated places using OSM Overpass API.
        Place names often reveal ancient origins.
        """
        try:
            radius_m = min(radius_km * 1000, 50000)
            query = f"""[out:json][timeout:25];
            (
              node["place"~"city|town|village|hamlet"](around:{radius_m},{lat},{lon});
            );
            out body;"""
            resp = self.session.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=30)
            if resp.status_code != 200:
                return {"error": f"Overpass API HTTP {resp.status_code}"}

            data = resp.json()
            places = []
            for el in data.get("elements", []):
                elat = el.get("lat", 0)
                elon = el.get("lon", 0)
                dlat = (elat - lat) * 111320
                dlon = (elon - lon) * 111320 * math.cos(math.radians(lat))
                dist = math.sqrt(dlat**2 + dlon**2) / 1000
                tags = el.get("tags", {})
                pop = tags.get("population", "0")
                try:
                    pop = int(pop)
                except (ValueError, TypeError):
                    pop = 0
                places.append({
                    "name": tags.get("name", "Unnamed"),
                    "type": tags.get("place", ""),
                    "population": pop,
                    "distance_km": round(dist, 1),
                    "lat": elat,
                    "lon": elon,
                })

            places.sort(key=lambda x: x["distance_km"])

            interpretation = []
            if places:
                nearest = places[0]
                interpretation.append(f"Nearest settlement: {nearest['name']} ({nearest['distance_km']}km, {nearest['type']})")
                total_pop = sum(p["population"] for p in places)
                if total_pop > 0:
                    interpretation.append(f"Total population within {radius_km}km: {total_pop:,}")
                if total_pop > 100000:
                    interpretation.append("Densely settled area — modern activity may mask ancient features")
                elif total_pop < 1000 and total_pop > 0:
                    interpretation.append("Sparsely populated — good conditions for surface archaeology")
                elif total_pop == 0:
                    interpretation.append("Population data not available in OSM for this region")
            else:
                interpretation.append("No named settlements found — remote or uninhabited area")

            return {
                "source": "OpenStreetMap Overpass API",
                "location": {"lat": lat, "lon": lon},
                "radius_km": radius_km,
                "count": len(places),
                "places": places[:20],
                "interpretation": interpretation,
            }
        except Exception as e:
            return {"error": f"Nearby places failed: {str(e)}"}
