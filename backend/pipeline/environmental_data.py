"""
CHRONOVISOR - Environmental & Geological Data Layer
Soil, geology, population, water table from free public APIs.
"""
import requests
import numpy as np
from datetime import datetime
import concurrent.futures


class EnvironmentalData:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Chronovisor/0.2"})

    def get_soil_data(self, lat, lon, depth="0-5cm"):
        try:
            props = ["clay","sand","silt","soc","phh2o","bdod"]
            prop_str = "&".join(["property="+p for p in props])
            url = "https://rest.isric.org/soilgrids/v2.0/properties/query?lon="+str(lon)+"&lat="+str(lat)+"&"+prop_str+"&depth="+depth+"&value=mean&value=uncertainty"
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200: return {"error": "SoilGrids HTTP "+str(resp.status_code)}
            data = resp.json()
            layers = data.get("properties",{}).get("layers",[])
            result = {"source":"ISRIC SoilGrids v2.0","location":{"lat":lat,"lon":lon},"depth":depth,"properties":{}}
            umap = {"clay":"g/kg","sand":"g/kg","silt":"g/kg","soc":"dg/kg","phh2o":"pH*10","bdod":"cg/cm3"}
            for layer in layers:
                name = layer.get("name","")
                for d in layer.get("depths",[]):
                    if d.get("label","")==depth:
                        v = d.get("values",{})
                        mv = v.get("mean")
                        if mv is not None and mv > -9000:
                            result["properties"][name]={"value":mv,"unit":umap.get(name,""),"uncertainty":v.get("uncertainty")}
            result["interpretation"]=self._interp_soil(result["properties"])
            return result
        except Exception as e: return {"error":str(e)}

    def _interp_soil(self, props):
        i = []
        clay = props.get("clay",{}).get("value",0)
        sand = props.get("sand",{}).get("value",0)
        if clay and clay>350: i.append("High clay - excellent preservation")
        elif sand and sand>600: i.append("Sandy soil - poor preservation")
        ph = props.get("phh2o",{}).get("value",0)
        if ph:
            r=ph/10.0
            if r<5.5: i.append("Acidic pH "+str(round(r,1))+" - bone/metal degrade")
            elif r>7.5: i.append("Alkaline pH "+str(round(r,1))+" - good bone preservation")
        return i if i else ["Soil conditions normal"]

    def get_fault_lines(self, lat, lon, radius_km=100):
        try:
            delta = radius_km / 111.0
            url = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude=2&starttime=2020-01-01&endtime="+datetime.now().strftime("%Y-%m-%d")+"&minlatitude="+str(lat-delta)+"&maxlatitude="+str(lat+delta)+"&minlongitude="+str(lon-delta)+"&maxlongitude="+str(lon+delta)+"&limit=200"
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200: return {"error":"USGS HTTP "+str(resp.status_code)}
            data = resp.json()
            features = data.get("features",[])
            quakes = []
            for f in features:
                p2 = f.get("properties",{})
                co = f.get("geometry",{}).get("coordinates",[])
                if len(co)>=2:
                    quakes.append({"mag":p2.get("mag"),"place":p2.get("place",""),"time":p2.get("time"),"depth_km":co[2] if len(co)>2 else None,"lon":co[0],"lat":co[1]})
            ad = np.mean([q["depth_km"] for q in quakes if q.get("depth_km")]) if quakes else 0
            return {"source":"USGS","location":{"lat":lat,"lon":lon},"radius_km":radius_km,"count":len(quakes),"quakes":sorted(quakes,key=lambda x:x.get("mag",0) or 0,reverse=True)[:20],"fault_activity":"active" if len(quakes)>5 else "low","avg_depth_km":round(float(ad),2),"interpretation":self._interp_faults(quakes)}
        except Exception as e: return {"error":str(e)}

    def _interp_faults(self, quakes):
        i = []
        if len(quakes)>20: i.extend(["High seismic activity - filter fault false positives","CAUTION: geological noise in satellite data"])
        elif len(quakes)>5: i.append("Moderate seismic zone")
        else: i.append("Low seismic - anomalies likely anthropogenic")
        return i if i else ["Minimal seismic activity"]

    def get_population_density(self, lat, lon):
        try:
            url = "https://api.worldpop.org/v1/services/wopr/query"
            resp = self.session.post(url, json={"dataset":"wpgp","lat":lat,"lon":lon,"year":2020}, timeout=15)
            if resp.status_code==200:
                data = resp.json()
                if "data" in data: return {"source":"WorldPop","location":{"lat":lat,"lon":lon},"population":data["data"],"interpretation":["Population data retrieved"]}
            return {"source":"WorldPop","location":{"lat":lat,"lon":lon},"error":"No data","interpretation":["Population data not available"]}
        except Exception as e: return {"error":str(e)}

    def get_water_table(self, lat, lon):
        try:
            resp = self.session.post("https://api.open-elevation.com/api/v1/lookup", json={"locations":[{"latitude":lat,"longitude":lon}]}, timeout=10)
            elev = 0
            if resp.status_code==200:
                r = resp.json().get("results",[])
                if r: elev = r[0].get("elevation",0)
            if elev<5: est,risk="very shallow (<2m)","high"
            elif elev<50: est,risk="shallow (2-5m)","moderate"
            elif elev<200: est,risk="moderate (5-15m)","low"
            elif elev<1000: est,risk="deep (15-50m)","very low"
            else: est,risk="very deep (>50m)","minimal"
            return {"source":"Elevation-based estimate","location":{"lat":lat,"lon":lon},"elevation_m":elev,"water_table":est,"risk":risk,"interpretation":self._interp_water(risk)}
        except Exception as e: return {"error":str(e)}

    def _interp_water(self, risk):
        if risk=="high": return ["Shallow water - structures waterlogged. Thermal dampened.","Organic remains may be preserved."]
        elif risk=="moderate": return ["Moderate water - seasonal flooding. Good stone preservation."]
        elif risk in ["low","very low"]: return ["Deep water - dry. Excellent thermal detection."]
        return ["Minimal water influence."]

    def full_environmental_scan(self, lat, lon, radius_km=100):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            sf = ex.submit(self.get_soil_data, lat, lon)
            ff = ex.submit(self.get_fault_lines, lat, lon, radius_km)
            pf = ex.submit(self.get_population_density, lat, lon)
            wf = ex.submit(self.get_water_table, lat, lon)
        return {"soil":sf.result(),"faults":ff.result(),"population":pf.result(),"water_table":wf.result()}
