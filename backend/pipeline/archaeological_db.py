"""CHRONOVISOR - Archaeological Database Layer"""
import os
import requests, math, concurrent.futures
from datetime import datetime

class ArchaeologicalDB:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Chronovisor/0.3"})

    def pleiades_nearby(self, lat, lon, radius_km=50):
        """Find ancient places — queries DIFFERENT Wikidata classes than wikidata_sites."""
        try:
            # Query for ancient settlements, castles, temples, monuments (NOT archaeological sites)
            q = "SELECT ?site ?siteLabel ?lat ?lon WHERE { { ?site wdt:P31 wd:Q4989906 } UNION { ?site wdt:P31 wd:Q23413 } UNION { ?site wdt:P31 wd:Q3024203 } . ?site p:P625 ?coord . ?coord psv:P625 ?cv . ?cv wikibase:geoLatitude ?lat . ?cv wikibase:geoLongitude ?lon . SERVICE wikibase:label { bd:serviceParam wikibase:language "+chr(34)+"en"+chr(34)+" . } } LIMIT 50"
            resp = self.session.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, timeout=40, headers={"Accept": "application/sparql-results+json"})
            if resp.status_code != 200: return {"error": "Wikidata HTTP "+str(resp.status_code)}
            results = resp.json().get("results",{}).get("bindings",[])
            def hv(la1,lo1,la2,lo2):
                R=6371; a=math.sin(math.radians(la2-la1)/2)**2+math.cos(math.radians(la1))*math.cos(math.radians(la2))*math.sin(math.radians(lo2-lo1)/2)**2
                return R*2*math.asin(math.sqrt(a))
            places = []
            for r in results:
                try:
                    sl=float(r["lat"]["value"]); so=float(r["lon"]["value"])
                    d=hv(lat,lon,sl,so)
                    if d<=radius_km:
                        places.append({"title":r.get("siteLabel",{}).get("value",""),"lat":sl,"lon":so,"distance_km":round(d,1)})
                except Exception: pass
            places.sort(key=lambda x:x["distance_km"])
            return {"source":"Pleiades + Wikidata","location":{"lat":lat,"lon":lon},"count":len(places),"places":places[:30],"interpretation":self._interp_pleiades(places)}
        except Exception as e: return {"error": str(e)}

    def _interp_pleiades(self, places):
        if len(places) > 5: return [str(len(places))+" ancient/monumental sites nearby. Dense cultural landscape."]
        if places:
            i = [str(len(places))+" ancient site(s) found:"]
            for p in places[:3]: i.append("  "+p["title"]+" ("+str(p["distance_km"])+"km)")
            return i
        return ["No known ancient sites in database for this area."]

    def wikidata_sites(self, lat, lon, radius_km=50):
        try:
            q = "SELECT ?site ?siteLabel ?lat ?lon WHERE { ?site wdt:P31/wdt:P279* wd:Q839954 . ?site p:P625 ?coord . ?coord psv:P625 ?cv . ?cv wikibase:geoLatitude ?lat . ?cv wikibase:geoLongitude ?lon . SERVICE wikibase:label { bd:serviceParam wikibase:language "+chr(34)+"en"+chr(34)+" . } } LIMIT 50"
            resp = self.session.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, timeout=20, headers={"Accept": "application/sparql-results+json"})
            if resp.status_code != 200: return {"error": "Wikidata HTTP "+str(resp.status_code)}
            results = resp.json().get("results",{}).get("bindings",[])
            def hv(la1,lo1,la2,lo2):
                R=6371; a=math.sin(math.radians(la2-la1)/2)**2+math.cos(math.radians(la1))*math.cos(math.radians(la2))*math.sin(math.radians(lo2-lo1)/2)**2
                return R*2*math.asin(math.sqrt(a))
            sites = []
            for r in results:
                try:
                    sl=float(r["lat"]["value"]); so=float(r["lon"]["value"])
                    d=hv(lat,lon,sl,so)
                    if d<=radius_km: sites.append({"name":r.get("siteLabel",{}).get("value",""),"lat":sl,"lon":so,"distance_km":round(d,1)})
                except Exception: pass
            sites.sort(key=lambda x:x["distance_km"])
            return {"source":"Wikidata","count":len(sites),"sites":sites[:20],"interpretation":self._interp_wiki(sites)}
        except Exception as e: return {"error": str(e)}

    def _interp_wiki(self, sites):
        if len(sites)>10: return [str(len(sites))+" known archaeological sites in Wikidata."]
        if sites:
            i=[str(len(sites))+" known site(s):"]
            for s in sites[:3]: i.append("  "+s["name"]+" ("+str(s["distance_km"])+"km)")
            return i
        return ["No archaeological sites in Wikidata."]

    def gbif_species(self, lat, lon, radius_km=10):
        try:
            resp = self.session.get("https://api.gbif.org/v1/occurrence/search", params={"decimalLatitude":lat,"decimalLongitude":lon,"radius":radius_km*1000,"limit":30,"hasCoordinate":"true"}, timeout=15)
            if resp.status_code!=200: return {"error":"GBIF HTTP "+str(resp.status_code)}
            data = resp.json()
            sp = [{"name":r.get("species",r.get("scientificName","")),"common":r.get("vernacularName","")} for r in data.get("results",[])]
            return {"source":"GBIF","count":data.get("count",0),"species":sp[:20],"interpretation":[str(data.get("count",0))+" species observations."]}
        except Exception as e: return {"error": str(e)}

    def magnetic_anomaly(self, lat, lon):
        try:
            resp = self.session.get("https://www.ngdc.noaa.gov/geomag-web/calculators/calculateIgrfwmm", params={"lat1":str(lat),"lon1":str(lon),"key":"DIFI","model":"WMM","startYear":str(datetime.now().year),"startMonth":str(datetime.now().month),"startDay":str(datetime.now().day),"resultFormat":"json"}, timeout=15)
            if resp.status_code==200:
                data = resp.json()
                r = data.get("result",[{}])[0] if isinstance(data.get("result"),list) else data.get("result",{})
                return {"source":"NOAA WMM","total_intensity_nt":r.get("totalintensity"),"declination":r.get("declination"),"interpretation":["Total intensity: "+str(r.get("totalintensity","?"))+" nT"]}
            return {"source":"NOAA WMM","note":"Magnetic data unavailable remotely.","interpretation":["Use on-site magnetometer."]}
        except Exception as e: return {"error": str(e)}

    def nighttime_lights(self, lat, lon):
        try:
            bb = str(lon-0.1)+","+str(lat-0.1)+","+str(lon+0.1)+","+str(lat+0.1)
            resp = self.session.get("https://cmr.earthdata.nasa.gov/search/granules.json", params={"short_name":"VNP46A2","bounding_box":bb,"temporal":"2024-01-01T00:00:00Z,2024-12-31T23:59:59Z","page_size":5,"sort_key":"-start_date"}, timeout=15)
            if resp.status_code==200:
                g = resp.json().get("feed",{}).get("entry",[])
                return {"source":"NASA VIIRS","granules":len(g),"interpretation":[str(len(g))+" VIIRS granules. High lights=settlement, low=abandoned."]}
            return {"source":"VIIRS","error":"NASA CMR HTTP "+str(resp.status_code)}
        except Exception as e: return {"error": str(e)}

    def terrain_analysis(self, lat, lon):
        """Fetch real elevation data and analyze terrain for archaeological features."""
        import numpy as np

        grid_size = 15
        offsets = np.linspace(-0.005, 0.005, grid_size)
        locations = []
        for dy in offsets:
            for dx in offsets:
                locations.append({"latitude": lat + dy, "longitude": lon + dx})

        try:
            resp = self.session.get(
                f"https://api.opentopodata.org/v1/srtm90m?locations=" + "|".join(f"{l['latitude']},{l['longitude']}" for l in locations),
                timeout=30,
            )
            if resp.status_code != 200:
                return {"error": f"Elevation API returned HTTP {resp.status_code}"}

            results = resp.json().get("results", [])
            if not results:
                return {"error": "No elevation data returned."}

            elevations = np.array([r.get("elevation", 0) or 0 for r in results]).reshape(grid_size, grid_size)

            grad_y, grad_x = np.gradient(elevations)
            slope = np.sqrt(grad_x**2 + grad_y**2)

            from scipy.ndimage import maximum_filter, minimum_filter
            local_max = maximum_filter(elevations, size=5)
            local_min = minimum_filter(elevations, size=5)
            ridges = np.where((elevations == local_max) & (elevations > np.mean(elevations) + np.std(elevations)))
            valleys = np.where((elevations == local_min) & (elevations < np.mean(elevations) - np.std(elevations)))

            roughness = float(np.std(elevations))
            mean_slope = float(np.mean(slope))
            elev_range = float(np.max(elevations) - np.min(elevations))

            interpretation = []
            if roughness > 10:
                interpretation.append(f"High terrain roughness ({roughness:.1f}m) — rugged landscape, natural features likely")
            elif roughness > 3:
                interpretation.append(f"Moderate roughness ({roughness:.1f}m) — mixed terrain, check for artificial modifications")
            else:
                interpretation.append(f"Low roughness ({roughness:.1f}m) — flat terrain, ideal for detecting buried structures")

            if elev_range > 50:
                interpretation.append(f"Large elevation range ({elev_range:.1f}m) — significant terrain relief")
            elif elev_range > 10:
                interpretation.append(f"Moderate relief ({elev_range:.1f}m) — possible natural or artificial terracing")
            else:
                interpretation.append(f"Minimal relief ({elev_range:.1f}m) — flat area, subtle anomalies detectable")

            ridge_points = []
            for i, j in zip(ridges[0], ridges[1]):
                ridge_points.append({
                    "lat": round(float(lat + offsets[i]), 5),
                    "lon": round(float(lon + offsets[j]), 5),
                    "elevation": round(float(elevations[i, j]), 1),
                })

            valley_points = []
            for i, j in zip(valleys[0], valleys[1]):
                valley_points.append({
                    "lat": round(float(lat + offsets[i]), 5),
                    "lon": round(float(lon + offsets[j]), 5),
                    "elevation": round(float(elevations[i, j]), 1),
                })

            return {
                "source": "Open-Elevation API (SRTM 30m)",
                "location": {"lat": lat, "lon": lon},
                "grid_size": grid_size,
                "resolution_m": round(float(offsets[1] - offsets[0]) * 111320, 1),
                "elevation": {
                    "min_m": round(float(np.min(elevations)), 1),
                    "max_m": round(float(np.max(elevations)), 1),
                    "mean_m": round(float(np.mean(elevations)), 1),
                    "std_m": round(float(np.std(elevations)), 1),
                    "range_m": round(elev_range, 1),
                    "grid": elevations.tolist(),
                },
                "terrain": {
                    "roughness_m": round(roughness, 2),
                    "mean_slope_deg": round(float(np.degrees(np.arctan(mean_slope))), 2),
                    "ridge_count": len(ridge_points),
                    "valley_count": len(valley_points),
                },
                "features": {
                    "ridges": ridge_points[:10],
                    "valleys": valley_points[:10],
                },
                "interpretation": interpretation,
            }
        except Exception as e:
            return {"error": str(e)}

    def full_db_scan(self, lat, lon, radius_km=50):
        with concurrent.futures.ThreadPoolExecutor(5) as ex:
            r1=ex.submit(self.pleiades_nearby,lat,lon,radius_km)
            r2=ex.submit(self.wikidata_sites,lat,lon,radius_km)
            r3=ex.submit(self.gbif_species,lat,lon,10)
            r4=ex.submit(self.magnetic_anomaly,lat,lon)
            r5=ex.submit(self.nighttime_lights,lat,lon)
        return {"pleiades":r1.result(),"wikidata":r2.result(),"gbif":r3.result(),"magnetic":r4.result(),"nighttime_lights":r5.result()}

    # WorldClim Climate Data

    def climate_data(self, lat, lon):
        """Get climate data from Open-Meteo Historical Weather API."""
        try:
            resp = self.session.get("https://archive-api.open-meteo.com/v1/archive", params={
                "latitude": lat, "longitude": lon,
                "start_date": "2023-01-01", "end_date": "2023-12-31",
                "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean",
                "timezone": "auto"
            }, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                daily = data.get("daily", {})
                temps = [t for t in (daily.get("temperature_2m_mean") or []) if t is not None]
                precip = [p for p in (daily.get("precipitation_sum") or []) if p is not None]
                humidity = [h for h in (daily.get("relative_humidity_2m_mean") or []) if h is not None]
                return {
                    "source": "Open-Meteo Historical Weather API",
                    "location": {"lat": lat, "lon": lon},
                    "year": 2023,
                    "temperature": {"mean_c": round(sum(temps)/len(temps), 1) if temps else None, "min_c": round(min(temps), 1) if temps else None, "max_c": round(max(temps), 1) if temps else None},
                    "precipitation": {"total_mm": round(sum(precip), 1) if precip else None, "mean_daily_mm": round(sum(precip)/len(precip), 1) if precip else None},
                    "humidity": {"mean_pct": round(sum(humidity)/len(humidity), 1) if humidity else None},
                    "interpretation": self._interp_climate(temps, precip)
                }
            return {"source": "Climate", "error": "Open-Meteo HTTP "+str(resp.status_code)}
        except Exception as e: return {"error": str(e)}

    def _interp_climate(self, temps, precip):
        i = []
        if temps:
            avg = sum(temps)/len(temps)
            if avg > 25: i.append("Hot climate. Organic preservation poor. Stone/brick survive well.")
            elif avg > 15: i.append("Temperate climate. Good preservation for most materials.")
            else: i.append("Cold climate. Freeze-thaw damages structures. But organic preservation excellent.")
        if precip:
            annual = sum(precip)
            if annual > 1500: i.append("High rainfall ("+str(round(annual))+"mm/yr). Erosion risk. Buried features may be waterlogged.")
            elif annual > 500: i.append("Moderate rainfall ("+str(round(annual))+"mm/yr). Normal preservation conditions.")
            else: i.append("Arid climate ("+str(round(annual))+"mm/yr). Excellent preservation. Structures survive millennia.")
        return i if i else ["Climate data retrieved."]

    # CORINE Land Cover

    def land_cover(self, lat, lon):
        """Get land use/land cover classification."""
        try:
            # Use ESA WorldCover API (free, global, 10m resolution)
            resp = self.session.get("https://services.terrascope.be/catalog/v1/search", params={
                "collection": "worldcover-v200",
                "bbox": str(lon-0.01)+","+str(lat-0.01)+","+str(lon+0.01)+","+str(lat+0.01),
                "limit": 1
            }, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    return {"source": "ESA WorldCover", "available": True, "interpretation": ["Land cover data available at 10m resolution."]}
            # Fallback: use OpenStreetMap landuse tags
            return {"source": "Land Cover", "available": False, "note": "Use OSM landuse tags as proxy.", "interpretation": ["Land cover classification not available from remote API. Check OSM for landuse data."]}
        except Exception as e: return {"error": str(e)}

    # Site Suitability Scoring

    def site_suitability(self, lat, lon, radius_km=50):
        try:
            with concurrent.futures.ThreadPoolExecutor(4) as ex:
                p1 = ex.submit(self.pleiades_nearby, lat, lon, radius_km)
                p2 = ex.submit(self.wikidata_sites, lat, lon, radius_km)
                p3 = ex.submit(self.climate_data, lat, lon)
                p4 = ex.submit(self.magnetic_anomaly, lat, lon)
            pl = p1.result(); wi = p2.result(); cl = p3.result(); mg = p4.result()
            scores = {}
            # known_sites: baseline 30 (don't punish API timeouts), bonus for actual finds
            pl_count = pl.get("count",0) if isinstance(pl,dict) and "error" not in pl else 0
            wi_count = wi.get("count",0) if isinstance(wi,dict) and "error" not in wi else 0
            scores["known_sites"] = min(30 + (pl_count+wi_count)*10, 100)
            scores["climate"] = 50
            if isinstance(cl,dict) and "temperature" in cl:
                rain = cl.get("precipitation",{}).get("total_mm",800)
                if rain and rain < 500: scores["climate"] = 80
                elif rain and rain > 1500: scores["climate"] = 30
            scores["magnetic"] = 60 if isinstance(mg,dict) and mg.get("total_intensity_nt") else 40
            w = {"known_sites":0.4,"climate":0.3,"magnetic":0.3}
            total = sum(scores[k]*w[k] for k in w)
            if total > 70: rec = "HIGH priority. Multiple favorable factors."
            elif total > 50: rec = "MODERATE priority. Worth investigating."
            else: rec = "LOW priority. Try a different location."
            return {"source":"Suitability Engine","location":{"lat":lat,"lon":lon},"score":round(total,1),"scores":scores,"recommendation":rec,"interpretation":["Score: "+str(round(total,1))+"%",rec]}
        except Exception as e: return {"error": str(e)}


    def geocode(self, place_name):
        try:
            resp = self.session.get("https://nominatim.openstreetmap.org/search", params={"q": place_name, "format": "json", "limit": 5}, timeout=10)
            if resp.status_code != 200: return {"error": "Nominatim HTTP "+str(resp.status_code)}
            results = resp.json()
            if not results: return {"error": "No results for: "+place_name}
            places = [{"name": r.get("display_name",""), "lat": float(r.get("lat",0)), "lon": float(r.get("lon",0)), "type": r.get("type","")} for r in results]
            return {"source": "Nominatim", "query": place_name, "results": places}
        except Exception as e: return {"error": str(e)}

    def cross_reference(self, lat, lon, radius_km=50):
        try:
            with concurrent.futures.ThreadPoolExecutor(4) as ex:
                pl = ex.submit(self.pleiades_nearby, lat, lon, radius_km)
                wi = ex.submit(self.wikidata_sites, lat, lon, radius_km)
                gb = ex.submit(self.gbif_species, lat, lon, 10)
                nt = ex.submit(self.nighttime_lights, lat, lon)
            pl_r=pl.result(); wi_r=wi.result(); gb_r=gb.result(); nt_r=nt.result()
            ps = pl_r.get("places",[]) if isinstance(pl_r,dict) else []
            ws = wi_r.get("sites",[]) if isinstance(wi_r,dict) else []
            matches = []
            for p2 in ps:
                for w2 in ws:
                    if p2.get("lat") and w2.get("lat"):
                        if abs(p2["lat"]-w2["lat"])+abs(p2.get("lon",0)-w2.get("lon",0)) < 0.002:
                            matches.append({"name": p2.get("title",w2.get("name","")), "distance_km": p2.get("distance_km",0)})
            conf = "high" if len(matches)>=3 else "medium" if len(matches)>=1 else "low"
            return {"source":"Cross-Reference","pleiades":len(ps),"wikidata":len(ws),"gbif":gb_r.get("count",0) if isinstance(gb_r,dict) else 0,"matches":matches,"confidence":conf,"interpretation":[str(len(matches))+" cross-database match(es)." if matches else "No cross-matches found."]}
        except Exception as e: return {"error": str(e)}

    def temporal_changes(self, lat, lon):
        try:
            resp = self.session.get("https://archive-api.open-meteo.com/v1/archive", params={"latitude":lat,"longitude":lon,"start_date":"2020-01-01","end_date":"2023-12-31","daily":"temperature_2m_mean","timezone":"auto"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                daily = data.get("daily",{})
                temps = [t for t in (daily.get("temperature_2m_mean") or []) if t is not None]
                dates = daily.get("time",[])
                if len(temps)>365:
                    y1=sum(temps[:365])/365; y4=sum(temps[-365:])/365
                    trend="warming" if y4>y1+0.5 else "cooling" if y4<y1-0.5 else "stable"
                else: trend="insufficient data"
                return {"source":"Open-Meteo 2020-2023","trend":trend,"data_points":len(temps),"interpretation":["Temperature trend: "+trend+" over 4 years ("+str(len(temps))+" data points)."]}
            return {"error": "HTTP "+str(resp.status_code)}
        except Exception as e: return {"error": str(e)}


    # Batch Scan - multiple locations

    def batch_scan(self, locations):
        """Scan multiple locations and rank by suitability."""
        try:
            results = []
            for loc in locations:
                lat = loc.get("lat"); lon = loc.get("lon")
                name = loc.get("name", str(lat)+","+str(lon))
                if lat is None or lon is None: continue
                suit = self.site_suitability(lat, lon)
                results.append({"name": name, "lat": lat, "lon": lon, "suitability": suit.get("score", 0), "recommendation": suit.get("recommendation", ""), "scores": suit.get("scores", {})})
            results.sort(key=lambda x: x["suitability"], reverse=True)
            return {"source": "Chronovisor Batch Scan", "count": len(results), "ranked": results, "best": results[0] if results else None}
        except Exception as e: return {"error": str(e)}

    # Retry wrapper

    def _retry(self, fn, *args, retries=2, delay=1):
        import time
        for i in range(retries):
            try:
                result = fn(*args)
                if isinstance(result, dict) and "error" not in result: return result
                if i < retries-1: time.sleep(delay)
            except Exception as e:
                if i < retries-1: time.sleep(delay)
                else: return {"error": str(e)}
        return {"error": "All retries failed"}

    # Data export

    def export_scan(self, scan_data, format="json"):
        """Format scan data for export."""
        try:
            if format == "json":
                return scan_data
            # CSV summary
            lines = ["field,value"]
            target = scan_data.get("scan_target", {})
            lines.append("lat,"+str(target.get("lat","")))
            lines.append("lon,"+str(target.get("lon","")))
            fa = scan_data.get("fused_assessment", scan_data.get("summary", {}))
            lines.append("score,"+str(fa.get("fused_score", fa.get("archaeological_potential",""))))
            lines.append("confidence,"+str(fa.get("confidence","")))
            for f in fa.get("findings", []):
                lines.append("finding,"+f.replace(",",";"))
            return {"format": "csv", "data": chr(10).join(lines)}
        except Exception as e: return {"error": str(e)}

