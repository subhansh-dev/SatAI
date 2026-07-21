"""CHRONOVISOR - Historical Web Data Layer"""
import requests
import concurrent.futures


class HistoricalWeb:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Chronovisor/0.2"})

    def wayback_search(self, lat, lon, place_name=""):
        try:
            results = []
            queries = []
            if place_name: queries.append(place_name)
            queries.append(str(round(lat,4))+","+str(round(lon,4)))
            for q in queries[:2]:
                try:
                    url = "https://web.archive.org/cdx/search/cdx?url="+q+"&output=json&limit=20&fl=urlkey,timestamp,original,statuscode&filter=statuscode:200"
                    resp = self.session.get(url, timeout=15)
                    if resp.status_code==200:
                        for row in resp.json()[1:]:
                            if len(row)>=4:
                                results.append({"url":row[2],"timestamp":row[1],"archived":"https://web.archive.org/web/"+row[1]+"/"+row[2]})
                except Exception: pass
            if place_name:
                for kw in ["archaeology","excavation","ancient","ruins","heritage"]:
                    try:
                        url = "https://web.archive.org/cdx/search/cdx?url=*"+place_name+"+"+kw+"*&output=json&limit=5&fl=urlkey,timestamp,original,statuscode&filter=statuscode:200"
                        resp = self.session.get(url, timeout=10)
                        if resp.status_code==200:
                            for row in resp.json()[1:]:
                                if len(row)>=4: results.append({"url":row[2],"timestamp":row[1],"archived":"https://web.archive.org/web/"+row[1]+"/"+row[2],"keyword":kw})
                    except Exception: pass
            seen = set()
            unique = [r for r in results if r["url"] not in seen and not seen.add(r["url"])]
            return {"source":"Internet Archive Wayback Machine","location":{"lat":lat,"lon":lon},"query":place_name,"count":len(unique),"archives":unique[:30],"interpretation":self._interp_wb(unique)}
        except Exception as e: return {"error":str(e)}

    def _interp_wb(self, archives):
        i = []
        if len(archives)>10: i.append("Rich web history. Check archived government and research pages.")
        elif archives: i.append("Some archived pages found.")
        else: i.append("No archived pages found.")
        kw = set(a.get("keyword","") for a in archives)
        if "archaeology" in kw: i.append("Archaeological content found - prior research exists.")
        return i

    def osm_history(self, lat, lon, radius_m=500):
        try:
            bbox = str(lat-0.005)+","+str(lon-0.005)+","+str(lat+0.005)+","+str(lon+0.005)
            q = "[out:json][timeout:25];(node("+bbox+");way("+bbox+"););out body;"
            resp = self.session.post("https://overpass-api.de/api/interpreter", data={"data":q}, timeout=25)
            if resp.status_code!=200: return {"error":"Overpass HTTP "+str(resp.status_code)}
            elements = resp.json().get("elements",[])
            features = []
            for el in elements:
                tags = el.get("tags",{})
                if tags:
                    features.append({"type":el.get("type"),"id":el.get("id"),"name":tags.get("name",""),"cat":tags.get("amenity",tags.get("historic",tags.get("landuse",tags.get("building","")))),"historic":tags.get("historic",""),"heritage":tags.get("heritage",""),"lat":el.get("lat"),"lon":el.get("lon")})
            hist = [f for f in features if f.get("historic") or f.get("heritage")]
            return {"source":"OpenStreetMap","location":{"lat":lat,"lon":lon},"total":len(features),"historic":hist,"all":features[:50],"interpretation":self._interp_osm(features,hist)}
        except Exception as e: return {"error":str(e)}

    def _interp_osm(self, features, historic):
        i = []
        if historic:
            i.append(str(len(historic))+" historically tagged features found.")
            for h in historic[:3]: i.append("  "+h.get("name","unnamed")+" ("+h.get("historic","")+")")
        else: i.append("No historic features tagged in OSM.")
        bldgs = [f for f in features if f.get("cat")=="building"]
        if len(bldgs)>20: i.append("Dense buildings - urban. Excavation needs permits.")
        elif len(bldgs)<5: i.append("Sparse - good for surface survey.")
        return i

    def full_web_scan(self, lat, lon, place_name="", radius_m=500):
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            wb = ex.submit(self.wayback_search, lat, lon, place_name)
            osm = ex.submit(self.osm_history, lat, lon, radius_m)
        return {"wayback":wb.result(),"osm":osm.result()}
