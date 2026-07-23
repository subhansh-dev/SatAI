import json
import os
import asyncio
import numpy as np
from datetime import datetime


class _NumpyEncoder(json.JSONEncoder):
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
        if not GEMINI_AVAILABLE:
            self.initialized = False
            return
        if not self.api_key or self.api_key == "your-gemini-api-key-here":
            self.initialized = False
            return
        try:
            self.client = genai.Client(api_key=self.api_key)
            self.initialized = True
        except Exception:
            self.initialized = False

    def _ok(self):
        return self.initialized and self.client is not None

    async def _gen(self, prompt):
        resp = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=prompt)
        return resp.text

    async def analyze_scan_results(self, scan_data):
        if not self._ok():
            return {"error": "Gemini not initialized. Set GEMINI_API_KEY in .env"}
        prompt = (
            "Senior satellite archaeologist. Analyze this Chronovisor scan data:\n"
            + _safe_json(scan_data, indent=2)[:8000]
            + "\n\nProvide: 1. Overall assessment 2. Key anomalies ranked 3. Most likely explanations "
            + "4. Recommended ground verification methods 5. Confidence level (low/medium/high)."
        )
        try:
            return {"analysis": await self._gen(prompt), "model": self.model_name, "timestamp": datetime.utcnow().isoformat(), "scan_target": scan_data.get("scan_target", {})}
        except Exception as e:
            return {"error": str(e)}

    async def explain_anomaly(self, anomaly, context=None):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        prompt = (
            "Senior satellite archaeologist.\n\nANOMALY:\n"
            + _safe_json(anomaly, indent=2)
            + "\n\nProvide: 1. Three ranked hypotheses 2. Ground-truth method for each "
            + "3. If archaeological: period/culture/structure type 4. Confidence with reasoning "
            + "5. One-sentence recommendation."
        )
        try:
            return {"explanation": await self._gen(prompt), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def historical_context(self, lat, lon, location_name=""):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        loc = location_name or f"({lat}, {lon})"
        prompt = (
            f"Historical geographer. Chronological profile for: {loc}\n"
            f"Coords: {lat}, {lon}\n\nSections: 1. Geographic Setting "
            f"2. Prehistoric 3. Ancient 4. Medieval 5. Modern 6. Archaeological Record "
            f"7. What Might Be Buried Here."
        )
        try:
            return {"history": await self._gen(prompt), "location": {"lat": lat, "lon": lon, "name": location_name}, "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def compare_locations(self, scan_results):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        prompt = (
            f"Regional archaeologist. Compare {len(scan_results)} survey sites:\n"
            + _safe_json(scan_results, indent=2)[:8000]
            + "\n\nAnalyze: 1. Best site 2. Connecting patterns 3. Same-period anomalies "
            + "4. Investigation order 5. Regional narrative."
        )
        try:
            return {"comparison": await self._gen(prompt), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def chat(self, message, scan_context=None, history=None):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        parts = [
            "You are CHRONOVISOR, AI archaeological analyst. Precise, cite real methods.",
        ]
        if scan_context:
            sc = scan_context
            summary = f"Location: ({sc.get('scan_target', {}).get('lat', '?')}, {sc.get('scan_target', {}).get('lon', '?')})\n"
            sat = sc.get("satellite", {})
            if sat:
                summary += f"\nSatellite: {sat.get('data_points', 0)} data points from {sat.get('source', 'unknown')}"
            summary += f"\nAnomalies: {len(sc.get('anomalies', []))}"
            summary += f"\nStructural probability: {sc.get('structural_analysis', {}).get('structural_probability', 0)}%"
            parts.append(summary)
        if history:
            for m in history[-10:]:
                parts.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
        parts.append(f"user: {message}")
        try:
            return {"reply": await self._gen("\n\n".join(parts)), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def suggest_investigation(self, scan_data):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        prompt = (
            f"Field archaeology project manager. Create investigation plan from:\n"
            + _safe_json(scan_data, indent=2)[:4000]
            + "\n\nFormat: 1. Priority targets 2. Methods per target 3. Equipment 4. Timeline 5. Budget."
        )
        try:
            return {"plan": await self._gen(prompt), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}

    async def generate_report(self, scan_data, location_name=""):
        if not self._ok():
            return {"error": "Gemini not initialized"}
        prompt = (
            f"Write archaeological survey report for {location_name}.\n"
            f"Scan data:\n{_safe_json(scan_data, indent=2)[:6000]}\n\n"
            f"Sections: Summary, Methods, Findings, Interpretation, Recommendations."
        )
        try:
            return {"report": await self._gen(prompt), "model": self.model_name}
        except Exception as e:
            return {"error": str(e)}