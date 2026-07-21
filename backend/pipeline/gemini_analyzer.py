"""
CHRONOVISOR — Gemini AI Analyzer
Optional AI-powered analysis using Google Gemini.
Graceful degradation when API key not set.
"""
import json
import os
import asyncio
import numpy as np
from datetime import datetime


class _NumpyEncoder(json.JSONEncoder):
    """Handle NumPy types that the default JSON encoder can't serialize."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _safe_json(obj, **kwargs):
    """JSON dumps that handles NumPy types."""
    return json.dumps(obj, cls=_NumpyEncoder, **kwargs)

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class GeminiAnalyzer:
    def __init__(self):
        self.client = None
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.initialized = False

    def initialize(self):
        """Public init method called by run.py and main.py."""
        if not GEMINI_AVAILABLE:
            print("[GeminiAnalyzer] google-genai not installed. pip install google-genai")
            self.initialized = False
            return
        if not self.api_key or self.api_key == "your-gemini-api-key-here":
            print("[GeminiAnalyzer] No GEMINI_API_KEY set. AI features disabled.")
            self.initialized = False
            return
        try:
            self.client = genai.Client(api_key=self.api_key)
            self.initialized = True
            print(f"[GeminiAnalyzer] Ready: {self.model_name}")
        except Exception as e:
            print(f"[GeminiAnalyzer] Failed: {e}")
            self.initialized = False

    def _ok(self):
        return self.initialized and self.client is not None

    async def _gen(self, prompt):
        """Run generation in thread to avoid blocking the event loop."""
        resp = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=prompt)
        return resp.text

    async def analyze_scan_results(self, scan_data):
        """Main analysis entry point — called by main.py."""
        if not self._ok():
            return {"error": "Gemini not initialized. Set GEMINI_API_KEY in .env"}
        p = "Senior satellite archaeologist. Analyze this Chronovisor scan data:\\n" + _safe_json(scan_data, indent=2)[:8000] + "\\n\\nProvide: 1. Overall assessment 2. Key anomalies (rank by significance) 3. Most likely explanations 4. Recommended ground verification methods 5. Confidence level (low/medium/high with reasoning). Be specific, cite data values."
        try:
            return {"analysis": await self._gen(p), "model": self.model_name, "timestamp": datetime.utcnow().isoformat(), "scan_target": scan_data.get("scan_target", {})}
        except Exception as e:
            return {"error": str(e)}

    async def analyze_scan(self, scan_data):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        p = "Senior satellite archaeologist. Analyze this Chronovisor scan data:\n" + _safe_json(scan_data, indent=2)[:8000] + "\n\nProvide: 1. Overall assessment 2. Key anomalies (rank by significance) 3. Most likely explanations 4. Recommended ground verification methods 5. Confidence level (low/medium/high with reasoning). Be specific, cite data values."
        try:
            return {"analysis": await self._gen(p), "model": self.model_name, "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            return {"error": str(e)}

    async def explain_anomaly(self, anomaly, context=None):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        p = "Senior satellite archaeologist.\n\nANOMALY:\n" + _safe_json(anomaly, indent=2) + "\n\nCONTEXT:\n" + _safe_json(context or {}, indent=2) + "\n\nProvide: 1. Three ranked hypotheses 2. Ground-truth method for each 3. If archaeological: period/culture/structure type 4. Confidence with reasoning 5. One-sentence recommendation. Under 400 words."
        try:
            return {"explanation": await self._gen(p), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def historical_context(self, lat, lon, location_name=""):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        loc = location_name or "(" + str(lat) + ", " + str(lon) + ")"
        p = "Historical geographer and archaeologist. Chronological profile for: " + loc + " Coords: " + str(lat) + ", " + str(lon) + "\n\nSections: 1. Geographic Setting (terrain, hydrology, why settle here) 2. Prehistoric (before 3000BC) 3. Ancient (3000BC-500AD, name empires/cultures) 4. Medieval (500-1500AD) 5. Colonial/Modern (1500-present) 6. Archaeological Record (known sites within 50km) 7. What Might Be Buried Here (specific plausible structures). Be factual. Name real cultures and dates."
        try:
            return {"history": await self._gen(p), "location": {"lat": lat, "lon": lon, "name": location_name}, "model": self.model_name, "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            return {"error": str(e)}

    async def compare_locations(self, scan_results):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        p = "Regional archaeologist. Compare " + str(len(scan_results)) + " survey sites:\n" + _safe_json(scan_results, indent=2)[:8000] + "\n\nAnalyze: 1. Best site (cite data) 2. Connecting patterns (trade route, river, culture) 3. Same-period anomalies 4. Investigation order 5. Regional narrative. Be analytical."
        try:
            return {"comparison": await self._gen(p), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def chat(self, message, scan_context=None, history=None):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        sys_prompt = "You are CHRONOVISOR, AI archaeological analyst. You have satellite imagery, soil data, seismic data, EM readings, historical maps, web archives. Precise, authoritative. Cite real methods (NDVI, SAR, magnetometry, GPR). Never fabricate. When ambiguous, say so. Markdown. Concise."
        parts = [sys_prompt]
        if scan_context:
            sc = scan_context
            s = "LATEST SCAN DATA for (" + str(sc.get("scan_target", {}).get("lat", "?")) + ", " + str(sc.get("scan_target", {}).get("lon", "?")) + "):"
            # Satellite summary
            sat = sc.get("satellite", {})
            if sat:
                s += "\nSatellite: " + str(sat.get("data_points", 0)) + " data points from " + str(sat.get("source", "unknown"))
                ts = sat.get("timeseries", [])
                if ts:
                    ndvi_vals = [t.get("ndvi") for t in ts[-5:] if t.get("ndvi") is not None]
                    thermal_vals = [t.get("thermal") for t in ts[-5:] if t.get("thermal") is not None]
                    if ndvi_vals: s += "\nRecent NDVI: " + ", ".join(str(round(v,3)) for v in ndvi_vals)
                    if thermal_vals: s += "\nRecent Thermal: " + ", ".join(str(round(v,1)) for v in thermal_vals)
            # Anomalies
            anomalies = sc.get("anomalies", [])
            if anomalies:
                s += "\nANOMALIES (" + str(len(anomalies)) + "):"
                for a in anomalies[:5]:
                    s += "\n- " + str(a.get("type","")) + " on " + str(a.get("date","")) + " (deviation: " + str(a.get("deviation","")) + "σ): " + str(a.get("interpretation",""))
            # Structural analysis
            struct = sc.get("structural_analysis", {})
            if struct:
                s += "\nStructural probability: " + str(struct.get("structural_probability", 0)) + "%"
                for i in struct.get("interpretation", [])[:3]:
                    s += "\n- " + str(i)
            # Fused assessment
            if "fused_assessment" in sc:
                fa = sc["fused_assessment"]
                s += "\nFused score: " + str(fa.get("fused_score", "?")) + "%, Confidence: " + str(fa.get("confidence", "?"))
                for f in fa.get("findings", [])[:3]:
                    s += "\n- " + str(f)
            # Environmental data
            env = sc.get("environmental", {})
            if env:
                soil = env.get("soil", {})
                if soil.get("properties"):
                    soil_str = ", ".join(k + "=" + str(v.get("value","")) + str(v.get("unit","")) for k,v in list(soil["properties"].items())[:5])
                    s += "\nSoil: " + soil_str
                faults = env.get("faults", {})
                if "count" in faults:
                    s += "\nSeismic: " + str(faults["count"]) + " earthquakes, activity=" + str(faults.get("fault_activity","?"))
                water = env.get("water_table", {})
                if water.get("water_table"):
                    s += "\nWater table: " + str(water["water_table"])
            # Magnetic
            arch = sc.get("archaeological_db", {})
            if arch:
                mag = arch.get("magnetic", {})
                if mag.get("total_intensity_nt"):
                    s += "\nMagnetic field: " + str(mag["total_intensity_nt"]) + " nT"
            # Summary
            summary = sc.get("summary", {})
            if summary.get("recommendation"):
                s += "\nRecommendation: " + str(summary["recommendation"])
            parts.append(s)
        if history:
            for m in history[-10:]:
                parts.append(m.get("role", "user") + ": " + m.get("content", ""))
        parts.append("user: " + message)
        try:
            return {"reply": await self._gen("\n\n".join(parts)), "model": self.model_name, "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            return {"error": str(e)}

    async def suggest_investigation(self, scan_data):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        p = "Field archaeology project manager. Create investigation plan from:\n" + _safe_json(scan_data, indent=2)[:4000] + "\n\nPlan: 1. Priority Targets (top 3 areas, why) 2. Methods per target (GPR/magnetometry/resistivity/test pit, why, expected results) 3. Equipment (gear + USD costs) 4. Timeline (phases) 5. Permits 6. Budget 7. Risks + mitigation. Practical and actionable."
        try:
            return {"plan": await self._gen(p), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def generate_report(self, scan_data, location_name=""):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        p = "Write a professional archaeological survey report for:\nLocation: " + location_name + "\nScan data:\n" + _safe_json(scan_data, indent=2)[:6000] + "\n\nFormat: Executive Summary, Methodology, Findings (with data references), Interpretation, Recommendations, Appendix (raw data highlights). Professional tone, 800-1200 words."
        try:
            return {"report": await self._gen(p), "model": self.model_name, "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            return {"error": str(e)}
