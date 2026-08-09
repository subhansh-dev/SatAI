import json
import os
import asyncio
import numpy as np
import httpx
from datetime import datetime, timezone


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


PROVIDERS = {
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "model": "gpt-oss-120b",
        "env_key": "CEREBRAS_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
        "env_key": "OPENROUTER_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "env_key": "GROQ_API_KEY",
    },
    "gemini": {
        "base_url": None,
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "env_key": "GEMINI_API_KEY",
    },
}


class GeminiAnalyzer:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini")
        self.model_name = None
        self.api_key = None
        self.base_url = None
        self.initialized = False
        self._http = None
        self._use_gemini_sdk = False

    def initialize(self):
        provider_cfg = PROVIDERS.get(self.provider, PROVIDERS["cerebras"])
        self.api_key = os.getenv(provider_cfg["env_key"], "")
        self.model_name = provider_cfg["model"]
        self.base_url = provider_cfg["base_url"]
        print(f"[GeminiAnalyzer] provider={self.provider}, env_key={provider_cfg['env_key']}, key_len={len(self.api_key)}")

        if not self.api_key or self.api_key.startswith("your-"):
            self.initialized = False
            print(f"[GeminiAnalyzer] init FAILED: no API key for {provider_cfg['env_key']}")
            return

        if self.provider == "gemini":
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.api_key)
                self._use_gemini_sdk = True
                self.initialized = True
            except ImportError:
                self.initialized = False
        else:
            self._http = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
            self._use_gemini_sdk = False
            self.initialized = True

    def _ok(self):
        return self.initialized

    async def _gen(self, system_prompt, user_prompt, temperature=0.7, max_tokens=4096):
        if self._use_gemini_sdk:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            resp = await asyncio.to_thread(
                self._gemini_client.models.generate_content,
                model=self.model_name,
                contents=full_prompt,
            )
            return resp.text

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        ) as client:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def analyze_scan_results(self, scan_data):
        if not self._ok():
            return {"error": f"LLM not initialized. Set {PROVIDERS[self.provider]['env_key']} in .env"}
        system = (
            "You are a senior satellite archaeologist with 20 years of experience in remote sensing. "
            "Analyze multi-source geospatial data with precision. Cite specific spectral indices, "
            "anomaly thresholds, and statistical confidence. Be direct — no hedging."
        )
        user = (
            f"Analyze this Chronovisor scan data:\n{_safe_json(scan_data, indent=2)[:12000]}\n\n"
            "Provide:\n"
            "1. OVERALL ASSESSMENT (2-3 sentences, decisive)\n"
            "2. KEY ANOMALIES (ranked by archaeological significance)\n"
            "3. MOST LIKELY EXPLANATIONS (ranked hypotheses with confidence)\n"
            "4. GROUND VERIFICATION METHODS (specific equipment/techniques)\n"
            "5. CONFIDENCE LEVEL: low/medium/high with reasoning"
        )
        try:
            text = await self._gen(system, user, temperature=0.5, max_tokens=3000)
            return {
                "analysis": text,
                "model": self.model_name,
                "provider": self.provider,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scan_target": scan_data.get("scan_target", {}),
            }
        except Exception as e:
            return {"error": str(e)}

    async def explain_anomaly(self, anomaly, context=None):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are a specialist in satellite archaeology and remote sensing anomalies. "
            "Provide ranked hypotheses with specific reasoning. Reference known archaeological "
            "phenomena (crop marks, soil marks, shadow marks, thermal inertia differences)."
        )
        ctx_str = ""
        if context:
            ctx_str = f"\nCONTEXT:\n{_safe_json(context, indent=2)[:2000]}\n"
        user = (
            f"Explain this anomaly in detail:\n{_safe_json(anomaly, indent=2)}\n{ctx_str}\n"
            "Provide:\n"
            "1. THREE RANKED HYPOTHESES (archaeological first, then natural explanations)\n"
            "2. GROUND-TRUTH METHOD for each hypothesis\n"
            "3. If archaeological: likely period, culture, structure type\n"
            "4. CONFIDENCE with reasoning\n"
            "5. ONE-SENTENCE RECOMMENDATION"
        )
        try:
            text = await self._gen(system, user, temperature=0.4, max_tokens=2000)
            return {"explanation": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def historical_context(self, lat, lon, location_name=""):
        if not self._ok():
            return {"error": "LLM not initialized"}
        loc = location_name or f"({lat}, {lon})"
        system = (
            "You are a historical geographer and archaeological surveyor. "
            "Build chronological profiles grounded in real archaeological records. "
            "Reference known excavation reports and satellite archaeology findings where possible."
        )
        user = (
            f"Chronological profile for: {loc}\nCoordinates: {lat}°N, {lon}°E\n\n"
            "Sections:\n"
            "1. GEOGRAPHIC SETTING (terrain, water, resources)\n"
            "2. PREHISTORIC (Stone Age – Bronze Age)\n"
            "3. ANCIENT (Iron Age – classical civilizations)\n"
            "4. MEDIEVAL\n"
            "5. MODERN\n"
            "6. EXISTING ARCHAEOLOGICAL RECORD (known sites, excavations)\n"
            "7. WHAT MIGHT BE BURIED HERE (based on geography + known settlement patterns)"
        )
        try:
            text = await self._gen(system, user, temperature=0.6, max_tokens=3000)
            return {
                "history": text,
                "location": {"lat": lat, "lon": lon, "name": location_name},
                "model": self.model_name,
                "provider": self.provider,
            }
        except Exception as e:
            return {"error": str(e)}

    async def compare_locations(self, scan_results):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are a regional archaeologist specializing in landscape-scale analysis. "
            "Identify connections between sites. Reference known settlement pattern theories "
            "(central place theory, sitecatchment analysis, peer polity interaction)."
        )
        user = (
            f"Compare {len(scan_results)} survey sites:\n"
            f"{_safe_json(scan_results, indent=2)[:12000]}\n\n"
            "Analyze:\n"
            "1. BEST SITE (highest archaeological potential, with reasoning)\n"
            "2. CONNECTING PATTERNS (trade routes, resource networks, cultural links)\n"
            "3. SAME-PERIOD ANOMALIES (sites that may be contemporaneous)\n"
            "4. INVESTIGATION ORDER (prioritized by significance + accessibility)\n"
            "5. REGIONAL NARRATIVE (what story do these sites tell together?)"
        )
        try:
            text = await self._gen(system, user, temperature=0.6, max_tokens=3000)
            return {"comparison": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def chat(self, message, scan_context=None, history=None):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are CHRONOVISOR AI — an archaeological analyst powered by satellite remote sensing. "
            "Be precise, cite real methods (NDVI thresholds, SAR backscatter physics, soil science). "
            "When uncertain, say so. Never fabricate archaeological sites."
        )
        parts = []
        if scan_context:
            sc = scan_context
            parts.append(
                f"ACTIVE SCAN CONTEXT:\n"
                f"Location: ({sc.get('scan_target', {}).get('lat', '?')}, "
                f"{sc.get('scan_target', {}).get('lon', '?')})\n"
                f"Satellite: {sc.get('satellite', {}).get('data_points', 0)} data points "
                f"from {sc.get('satellite', {}).get('source', 'unknown')}\n"
                f"Anomalies: {len(sc.get('anomalies', []))}\n"
                f"Structural probability: {sc.get('structural_analysis', {}).get('structural_probability', 0)}%\n"
                f"Fused score: {sc.get('fused_assessment', {}).get('fused_score', 'N/A')}%"
            )
        if history:
            for m in history[-10:]:
                role = m.get("role", "user")
                content = m.get("content", "")
                parts.append(f"{role}: {content}")
        parts.append(f"user: {message}")
        try:
            text = await self._gen(system, "\n\n".join(parts), temperature=0.7, max_tokens=2000)
            return {"reply": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def suggest_investigation(self, scan_data):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are a field archaeology project manager. Create actionable investigation plans "
            "with realistic budgets, timelines, and equipment lists. Reference standard "
            "archaeological survey methodologies (geophysics, remote sensing, test pits)."
        )
        user = (
            f"Create investigation plan from:\n{_safe_json(scan_data, indent=2)[:6000]}\n\n"
            "Format:\n"
            "1. PRIORITY TARGETS (ranked by potential)\n"
            "2. METHODS PER TARGET (GPR, magnetometry, resistivity, test pits)\n"
            "3. EQUIPMENT LIST (with approximate costs)\n"
            "4. TIMELINE (phases with durations)\n"
            "5. BUDGET ESTIMATE (breakdown by category)\n"
            "6. PERMITS REQUIRED"
        )
        try:
            text = await self._gen(system, user, temperature=0.5, max_tokens=3000)
            return {"plan": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def generate_report(self, scan_data, location_name=""):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are writing a professional archaeological survey report. "
            "Use formal academic tone. Structure with clear sections. "
            "Include methodology, findings, interpretation, and recommendations. "
            "Reference the data sources and statistical methods used."
        )
        user = (
            f"Write archaeological survey report for {location_name}.\n"
            f"Scan data:\n{_safe_json(scan_data, indent=2)[:10000]}\n\n"
            "Sections:\n"
            "1. ABSTRACT\n"
            "2. SITE DESCRIPTION\n"
            "3. METHODOLOGY (data sources, analytical methods)\n"
            "4. FINDINGS (satellite, environmental, archaeological data)\n"
            "5. INTERPRETATION (what the data suggests)\n"
            "6. RECOMMENDATIONS (next steps)\n"
            "7. REFERENCES (data sources)"
        )
        try:
            text = await self._gen(system, user, temperature=0.5, max_tokens=4000)
            return {"report": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def interpret_signal_patterns(self, signal_data, spectral_analysis):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are a geophysical signal analyst specializing in subsurface detection. "
            "Interpret FFT spectra, harmonic series, and EM field patterns. "
            "Distinguish natural geological signals from potential man-made signatures."
        )
        user = (
            f"Interpret these signal analysis results:\n"
            f"Spectral Data:\n{_safe_json(spectral_analysis, indent=2)[:4000]}\n"
            f"Signal Context:\n{_safe_json(signal_data, indent=2)[:2000]}\n\n"
            "Provide:\n"
            "1. SIGNAL CLASSIFICATION (natural/artificial/mixed)\n"
            "2. PATTERN INTERPRETATION (what the harmonics/peaks mean)\n"
            "3. SUBSURFACE IMPLICATIONS (depth, material, structure)\n"
            "4. CONFIDENCE and limitations"
        )
        try:
            text = await self._gen(system, user, temperature=0.4, max_tokens=2000)
            return {"interpretation": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def interpret_environmental(self, env_data):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are an environmental archaeologist. Interpret soil, seismic, hydrological, "
            "and population data in the context of archaeological site preservation and detection. "
            "Reference soil science, hydrogeology, and settlement ecology."
        )
        user = (
            f"Interpret this environmental data for archaeological potential:\n"
            f"{_safe_json(env_data, indent=2)[:6000]}\n\n"
            "Provide:\n"
            "1. PRESERVATION POTENTIAL (how well could artifacts survive here)\n"
            "2. DETECTION CONDITIONS (how favorable for satellite/remote sensing)\n"
            "3. SETTLEMENT SUITABILITY (why ancient people might have lived here)\n"
            "4. KEY ENVIRONMENTAL FACTORS (most important 2-3 findings)\n"
            "5. RISKS (what could create false positives/negatives)"
        )
        try:
            text = await self._gen(system, user, temperature=0.5, max_tokens=2000)
            return {"interpretation": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}

    async def synthesize_crossref(self, pleiades, wikidata, gbif, magnetic, other_db):
        if not self._ok():
            return {"error": "LLM not initialized"}
        system = (
            "You are an archaeological database specialist. Cross-reference multiple "
            "archaeological databases to identify confirmed sites, potential sites, "
            "and data gaps. Resolve conflicting entries."
        )
        user = (
            f"Cross-reference these archaeological database results:\n"
            f"Pleiades: {_safe_json(pleiades, indent=2)[:2000]}\n"
            f"Wikidata: {_safe_json(wikidata, indent=2)[:2000]}\n"
            f"GBIF: {_safe_json(gbif, indent=2)[:1000]}\n"
            f"Magnetic: {_safe_json(magnetic, indent=2)[:1000]}\n"
            f"Other: {_safe_json(other_db, indent=2)[:2000]}\n\n"
            "Provide:\n"
            "1. CONFIRMED SITES (entries that appear in multiple databases)\n"
            "2. CANDIDATE SITES (single-database entries needing verification)\n"
            "3. DATA GAPS (what's missing that should be checked)\n"
            "4. CONFLICTS (contradictory entries and resolution)\n"
            "5. PRIORITY LIST (most promising unverified locations)"
        )
        try:
            text = await self._gen(system, user, temperature=0.4, max_tokens=2500)
            return {"synthesis": text, "model": self.model_name, "provider": self.provider}
        except Exception as e:
            return {"error": str(e)}
