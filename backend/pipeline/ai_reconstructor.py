"""
CHRONOVISOR — AI Reconstruction Module
Uses ML models for: image super-resolution, anomaly detection,
pattern recognition, and signal reconstruction.
Colab-ready for GPU acceleration.
"""
import numpy as np
from typing import Optional
import json
import os
import httpx


class AIReconstructor:
    """AI-powered reconstruction and analysis engine."""

    def __init__(self):
        self.models_loaded = False
        self._llm_client = None
        self._llm_key = os.getenv("CEREBRAS_API_KEY", "")
        self._llm_model = "gpt-oss-120b"
        self._llm_url = "https://api.cerebras.ai/v1"
        # Fallback: Gemini
        self._fallback_client = None
        self._fallback_model = None
        self._fallback_use_sdk = False

    def load_models(self):
        """Load ML models (lightweight versions for local, full on Colab)."""
        self.models_loaded = True
        if self._llm_key:
            try:
                self._llm_client = httpx.Client(
                    base_url=self._llm_url,
                    headers={"Authorization": f"Bearer {self._llm_key}", "Content-Type": "application/json"},
                    timeout=60.0,
                )
                print("[AIReconstructor] Models loaded + Cerebras LLM connected")
            except Exception:
                print("[AIReconstructor] Models loaded (LLM unavailable)")
        else:
            print("[AIReconstructor] Models loaded (lightweight mode)")

        # Init Gemini fallback
        self._init_fallback()

    def _init_fallback(self):
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not gemini_key or gemini_key.startswith("your-"):
            return
        try:
            from google import genai
            self._fallback_client = genai.Client(api_key=gemini_key)
            self._fallback_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            self._fallback_use_sdk = True
            print("[AIReconstructor] Gemini fallback ready")
        except ImportError:
            pass

    def _llm_generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate text via Cerebras, fallback to Gemini."""
        # Try Cerebras first
        if self._llm_client:
            try:
                resp = self._llm_client.post("/chat/completions", json={
                    "model": self._llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    print(f"[AIReconstructor] Cerebras returned {resp.status_code}")
            except Exception as e:
                print(f"[AIReconstructor] Cerebras failed: {e}")

        # Fallback to Gemini
        if self._fallback_client:
            try:
                print("[AIReconstructor] Falling back to Gemini...")
                resp = self._fallback_client.models.generate_content(
                    model=self._fallback_model,
                    contents=prompt,
                )
                return resp.text.strip()
            except Exception as e:
                print(f"[AIReconstructor] Gemini fallback also failed: {e}")

        return ""

    def ai_interpret_fusion(self, fusion_result: dict) -> str:
        """Use Cerebras LLM to generate a human-readable expert interpretation of fused results."""
        score = fusion_result.get("fused_score", 0)
        findings = fusion_result.get("findings", [])
        warnings = fusion_result.get("warnings", [])
        modifiers = fusion_result.get("modifiers", [])

        prompt = f"""You are an archaeological remote sensing expert analyzing satellite and environmental data.

Analysis Results:
- Fused archaeological potential score: {score}/100
- Confidence: {fusion_result.get('confidence', 'unknown')}
- Key findings: {'; '.join(findings[:5])}
- Warnings: {'; '.join(warnings[:3]) if warnings else 'None'}
- Data modifiers: {json.dumps(modifiers[:3]) if modifiers else 'None'}

Provide a 2-3 sentence expert assessment. Be specific about what the data means for archaeological potential. Do not be generic."""

        return self._llm_generate(prompt, max_tokens=200)

    def ai_interpret_terrain(self, terrain_result: dict) -> str:
        """Use Cerebras LLM to interpret 3D terrain analysis."""
        ridges = terrain_result.get("features", {}).get("ridges", [])
        valleys = terrain_result.get("features", {}).get("valleys", [])
        anomalies = terrain_result.get("features", {}).get("anomalies", [])
        elev_range = terrain_result.get("max_elevation", 0) - terrain_result.get("min_elevation", 0)

        prompt = f"""You are a terrain analysis expert for archaeological survey.
Terrain data: grid={terrain_result.get('grid_size')}, elev_range={elev_range:.1f}m
Ridge points: {len(ridges)}, Valley points: {len(valleys)}, Anomaly points: {len(anomalies)}
Ridges: {json.dumps(ridges[:3])}
Valleys: {json.dumps(valleys[:3])}

What does this terrain tell us about possible buried structures or artificial modifications? Be specific."""

        return self._llm_generate(prompt, max_tokens=200)

    def detect_buried_structures(
        self,
        ndvi_series: list,
        thermal_series: list,
        dates: list
    ) -> dict:
        """
        Analyze vegetation and thermal patterns to detect buried structures.
        Buried structures cause:
        - Vegetation stress (roots can't penetrate stone/foundation)
        - Thermal anomalies (stone retains/releases heat differently)
        - Moisture differences (water pools around buried walls)
        """
        if len(ndvi_series) < 6:
            return {"error": "Need at least 6 data points for analysis"}

        ndvi = np.array(ndvi_series, dtype=float)
        thermal = np.array(thermal_series, dtype=float) if thermal_series else np.zeros_like(ndvi)

        # Remove seasonal trend (detrend)
        from scipy.signal import detrend
        ndvi_detrended = detrend(ndvi)
        thermal_detrended = detrend(thermal)

        # Compute anomaly scores
        ndvi_anomaly = np.abs(ndvi_detrended) / max(np.std(ndvi_detrended), 0.001)
        thermal_anomaly = np.abs(thermal_detrended) / max(np.std(thermal_detrended), 0.001)

        # Combined anomaly score
        combined = 0.6 * ndvi_anomaly + 0.4 * thermal_anomaly

        # Find anomalous periods
        threshold = 2.0
        anomalous_indices = np.where(combined > threshold)[0]

        # Correlation between NDVI and thermal (inverse = structural)
        if len(ndvi) > 3 and len(thermal) > 3:
            correlation = float(np.corrcoef(ndvi[:min(len(ndvi), len(thermal))],
                                           thermal[:min(len(ndvi), len(thermal))])[0, 1])
        else:
            correlation = 0.0

        # Structural probability
        structural_score = 0.0
        if correlation < -0.3:
            structural_score += 30  # inverse correlation = structure likely
        if len(anomalous_indices) > 0:
            structural_score += min(len(anomalous_indices) / len(ndvi) * 100, 40)
        if np.std(ndvi_detrended) > 0.05:
            structural_score += 20
        structural_score = min(structural_score, 100)

        anomalies = []
        for idx in anomalous_indices:
            date = dates[idx] if idx < len(dates) else f"point_{idx}"
            anomalies.append({
                "index": int(idx),
                "date": date,
                "ndvi_anomaly_score": round(float(ndvi_anomaly[idx]), 2),
                "thermal_anomaly_score": round(float(thermal_anomaly[idx]), 2),
                "combined_score": round(float(combined[idx]), 2),
            })

        return {
            "structural_probability": round(structural_score, 1),
            "ndvi_thermal_correlation": round(correlation, 4),
            "anomalous_points": len(anomalous_indices),
            "total_points": len(ndvi),
            "anomalies": anomalies[:10],
            "interpretation": self._interpret_structure(structural_score, correlation),
            "confidence": self._confidence_level(structural_score, len(ndvi))
        }

    def reconstruct_3d_terrain(self, elevation_data: np.ndarray, lat: float = None, lon: float = None) -> dict:
        """
        Analyze real elevation data for 3D terrain rendering.
        Identifies ridges, valleys, and anomalies in the terrain.
        Requires real elevation data from Open-Elevation or SRTM.
        """
        if elevation_data is None or elevation_data.size == 0:
            return {"error": "No elevation data provided. Fetch real terrain data from Open-Elevation API."}

        grid_size = elevation_data.shape[0]

        # Find features
        from scipy.ndimage import maximum_filter, minimum_filter
        local_max = maximum_filter(elevation_data, size=10)
        local_min = minimum_filter(elevation_data, size=10)
        ridges = np.where(elevation_data == local_max)
        valleys = np.where(elevation_data == local_min)

        # Detect anomalies — spots where elevation changes sharply
        grad_y, grad_x = np.gradient(elevation_data)
        gradient_mag = np.sqrt(grad_x**2 + grad_y**2)
        anomaly_threshold = np.mean(gradient_mag) + 2 * np.std(gradient_mag)
        anomaly_points = np.where(gradient_mag > anomaly_threshold)

        return {
            "source": "Open-Elevation API (SRTM 30m)",
            "grid_size": grid_size,
            "elevation": elevation_data.tolist(),
            "min_elevation": round(float(np.min(elevation_data)), 2),
            "max_elevation": round(float(np.max(elevation_data)), 2),
            "ridge_points": len(ridges[0]),
            "valley_points": len(valleys[0]),
            "anomaly_points": len(anomaly_points[0]),
            "features": {
                "ridges": [{"x": int(ridges[1][i]), "y": int(ridges[0][i]),
                            "elevation": round(float(elevation_data[ridges[0][i], ridges[1][i]]), 2)}
                           for i in range(min(10, len(ridges[0])))],
                "valleys": [{"x": int(valleys[1][i]), "y": int(valleys[0][i]),
                             "elevation": round(float(elevation_data[valleys[0][i], valleys[1][i]]), 2)}
                            for i in range(min(10, len(valleys[0])))],
                "anomalies": [{"x": int(anomaly_points[1][i]), "y": int(anomaly_points[0][i]),
                               "gradient": round(float(gradient_mag[anomaly_points[0][i], anomaly_points[1][i]]), 2)}
                              for i in range(min(10, len(anomaly_points[0])))]
            }
        }

    def analyze_temporal_change(
        self,
        time_series: list,
        dates: list,
        window_size: int = 5
    ) -> dict:
        """
        Detect significant temporal changes in any time series.
        Uses change point detection to find moments when the
        environment shifted (construction, demolition, burial, etc.)
        """
        if len(time_series) < window_size * 2:
            return {"error": f"Need at least {window_size * 2} data points"}

        data = np.array(time_series, dtype=float)

        # Simple change point detection (CUSUM)
        mean_data = np.mean(data)
        cusum = np.cumsum(data - mean_data)

        # Find change points (where CUSUM slope changes dramatically)
        cusum_diff = np.diff(cusum)
        threshold = np.std(cusum_diff) * 2

        change_points = []
        for i in range(1, len(cusum_diff) - 1):
            if abs(cusum_diff[i] - cusum_diff[i-1]) > threshold:
                change_points.append({
                    "index": i,
                    "date": dates[i] if i < len(dates) else f"point_{i}",
                    "magnitude": round(float(abs(cusum_diff[i] - cusum_diff[i-1])), 4),
                    "direction": "increase" if cusum_diff[i] > cusum_diff[i-1] else "decrease"
                })

        # Trend analysis
        from scipy.stats import linregress
        x = np.arange(len(data))
        slope, intercept, r_value, p_value, std_err = linregress(x, data)

        return {
            "data_points": len(data),
            "change_points": change_points[:10],
            "trend": {
                "slope": round(float(slope), 6),
                "r_squared": round(float(r_value**2), 4),
                "p_value": round(float(p_value), 6),
                "direction": "increasing" if slope > 0 else "decreasing",
                "significant": p_value < 0.05
            },
            "interpretation": self._interpret_temporal(change_points, slope, p_value)
        }

    def _interpret_structure(self, score: float, correlation: float) -> list:
        """Interpret buried structure detection results."""
        interpretations = []
        if score > 70:
            interpretations.append("HIGH probability of buried structure — strong anomaly pattern detected")
        elif score > 40:
            interpretations.append("MODERATE probability of buried features — some anomaly signatures present")
        else:
            interpretations.append("LOW probability — no significant structural signatures")

        if correlation < -0.3:
            interpretations.append("Inverse NDVI-thermal correlation — vegetation stress aligned with thermal anomalies (classic buried structure signature)")
        elif correlation > 0.3:
            interpretations.append("Positive correlation — anomalies are likely seasonal, not structural")

        return interpretations

    def _confidence_level(self, score: float, n_points: int) -> str:
        """Determine confidence level based on score and data quantity."""
        if n_points < 10:
            return "low (insufficient data)"
        if score > 70 and n_points > 20:
            return "high"
        elif score > 40 and n_points > 12:
            return "medium"
        return "low"

    def _interpret_temporal(self, change_points: list, slope: float, p_value: float) -> list:
        """Interpret temporal change results."""
        interpretations = []
        if change_points:
            interpretations.append(f"Detected {len(change_points)} significant change event(s)")
            for cp in change_points[:3]:
                interpretations.append(
                    f"  Change at {cp['date']}: {cp['direction']} (magnitude: {cp['magnitude']})"
                )
        if p_value < 0.05:
            direction = "increasing" if slope > 0 else "decreasing"
            interpretations.append(f"Statistically significant {direction} trend (p={p_value:.4f})")
        else:
            interpretations.append("No statistically significant trend detected")
        return interpretations

    # ─── ENVIRONMENTAL FUSION ENGINE ───
    # This is the core intelligence: combines satellite anomalies with
    # soil preservation, seismic filtering, water table, and OSM context
    # into a single unified archaeological assessment.

    def fuse_all_data(
        self,
        structural: dict,
        anomalies: list,
        temporal: dict,
        spectral: dict,
        soil: dict = None,
        faults: dict = None,
        water_table: dict = None,
        population: dict = None,
        osm: dict = None,
        wayback: dict = None
    ) -> dict:
        """
        FUSE all data sources into a unified archaeological assessment.
        This replaces the naive generate_summary() with a proper weighted
        scoring system that accounts for environmental context.

        Scoring weights:
        - Satellite anomalies: 35% (base signal)
        - Soil preservation potential: 20% (multiplier on satellite signal)
        - Seismic false-positive filter: 10% (penalty for geological noise)
        - Water table effect: 10% (adjusts thermal interpretation)
        - OSM historical features: 10% (confirmation signal)
        - Temporal consistency: 10% (persistent anomalies = more likely real)
        - Web archive evidence: 5% (prior research confirmation)
        """
        scores = {}
        findings = []
        warnings = []
        modifiers = []

        # 1. BASE SCORE from satellite anomalies (35% weight)
        base_score = structural.get("structural_probability", 0)
        n_points = structural.get("total_points", 0)
        correlation = structural.get("ndvi_thermal_correlation", 0)

        # Penalize low data quantity
        data_quality_mult = min(n_points / 20.0, 1.0)  # Need 20+ points for full confidence
        adjusted_base = base_score * data_quality_mult
        scores["satellite_anomalies"] = round(adjusted_base, 1)

        if base_score > 70:
            findings.append("Strong satellite anomaly pattern (score: " + str(round(base_score, 0)) + "%)")
        elif base_score > 40:
            findings.append("Moderate satellite anomalies detected")

        if correlation < -0.3:
            findings.append("Inverse NDVI-thermal correlation — classic buried structure signature")
            scores["satellite_anomalies"] = min(scores["satellite_anomalies"] + 5, 100)

        if n_points < 10:
            warnings.append("Low data quantity (" + str(n_points) + " points). Results less reliable.")

        # 2. SOIL PRESERVATION (20% weight)
        soil_score = 50  # neutral default
        if soil and "properties" in soil:
            props = soil["properties"]
            clay = props.get("clay", {}).get("value", 0) or 0
            sand = props.get("sand", {}).get("value", 0) or 0
            ph = props.get("phh2o", {}).get("value", 0) or 0
            soc = props.get("soc", {}).get("value", 0) or 0

            if clay > 350:
                soil_score = 85
                findings.append("High clay soil — excellent structure preservation potential")
                modifiers.append({"factor": "soil_clay", "effect": "+35%", "reason": "Clay preserves stone foundations for millennia"})
            elif clay > 200:
                soil_score = 65
                findings.append("Moderate clay — decent preservation")
            elif sand > 600:
                soil_score = 25
                warnings.append("Sandy soil — poor preservation. Anomalies may be geological, not archaeological.")
                modifiers.append({"factor": "soil_sand", "effect": "-25%", "reason": "Sandy soil degrades buried structures"})

            if ph:
                ph_real = ph / 10.0
                if ph_real > 7.5:
                    soil_score = min(soil_score + 10, 100)
                    findings.append("Alkaline soil (pH " + str(round(ph_real, 1)) + ") — good bone preservation")
                elif ph_real < 5.5:
                    soil_score = max(soil_score - 15, 0)
                    warnings.append("Acidic soil (pH " + str(round(ph_real, 1)) + ") — degrades bone and metal")

            if soc and soc > 200:
                findings.append("High organic carbon — long habitation or natural accumulation")

            for interp in soil.get("interpretation", []):
                if interp not in findings and interp not in warnings:
                    findings.append(interp)

        scores["soil_preservation"] = round(soil_score, 1)

        # 3. SEISMIC FALSE-POSITIVE FILTER (10% weight)
        seismic_penalty = 0
        if faults:
            quake_count = faults.get("count", faults.get("earthquake_count", 0))
            activity = faults.get("fault_activity", "low")

            if activity == "active" and quake_count > 20:
                seismic_penalty = 25
                warnings.append("High seismic activity — geological noise may create false positives")
                modifiers.append({"factor": "seismic_active", "effect": "-25%", "reason": "Active fault zone creates subsurface anomalies resembling structures"})
            elif activity == "active" and quake_count > 5:
                seismic_penalty = 10
                warnings.append("Moderate seismic activity — some geological noise expected")
            else:
                findings.append("Low seismic activity — anomalies more likely anthropogenic")

            for interp in faults.get("interpretation", []):
                if interp not in findings and interp not in warnings:
                    findings.append(interp)

        scores["seismic_filter"] = round(50 - seismic_penalty, 1)  # 50 is neutral

        # 4. WATER TABLE EFFECT (10% weight)
        water_score = 50  # neutral
        if water_table:
            risk = water_table.get("risk", water_table.get("preservation_risk", "unknown"))
            elev = water_table.get("elevation_m", 0)

            if risk == "high":
                water_score = 30
                warnings.append("Shallow water table — thermal signatures dampened, organic preservation possible")
                modifiers.append({"factor": "water_high", "effect": "-20%", "reason": "Waterlogged soil distorts thermal anomaly signals"})
            elif risk == "moderate":
                water_score = 45
                findings.append("Moderate water table — seasonal effects on surface readings")
            elif risk in ["low", "very low"]:
                water_score = 70
                findings.append("Deep water table — dry conditions, excellent for thermal detection")
            elif risk == "minimal":
                water_score = 80
                findings.append("Minimal water influence — pure signal conditions")

            for interp in water_table.get("interpretation", []):
                if interp not in findings and interp not in warnings:
                    findings.append(interp)

        scores["water_table"] = round(water_score, 1)

        # 5. OSM HISTORICAL FEATURES (10% weight)
        osm_score = 30  # low default (no data = neutral-negative)
        if osm:
            historic = osm.get("historic", [])
            total = osm.get("total", 0)

            if historic:
                osm_score = 80
                findings.append(str(len(historic)) + " historically tagged features in OSM — prior cultural activity confirmed")
                for h in historic[:3]:
                    name = h.get("name", "Unnamed")
                    tag = h.get("historic", h.get("heritage", "historic site"))
                    findings.append("  OSM: " + name + " (" + tag + ")")
                modifiers.append({"factor": "osm_historic", "effect": "+30%", "reason": "Existing historical features confirm cultural activity"})
            elif total > 20:
                osm_score = 45
                findings.append("Dense OSM coverage — active area, check for development threats")
            else:
                osm_score = 40
                findings.append("Sparse OSM data — area may be undeveloped (good for survey)")

            for interp in osm.get("interpretation", []):
                if interp not in findings and interp not in warnings:
                    findings.append(interp)

        scores["osm_context"] = round(osm_score, 1)

        # 6. TEMPORAL CONSISTENCY (10% weight)
        temporal_score = 40
        if temporal and "trend" in temporal:
            trend = temporal["trend"]
            change_points = temporal.get("change_points", [])

            if trend.get("significant") and trend.get("r_squared", 0) > 0.3:
                temporal_score = 70
                findings.append("Statistically significant trend in satellite data (R²=" + str(round(trend.get("r_squared", 0), 2)) + ")")

            if change_points:
                temporal_score = min(temporal_score + len(change_points) * 5, 90)
                findings.append(str(len(change_points)) + " temporal change events — environment shifted at specific dates")

            for interp in temporal.get("interpretation", []):
                if interp not in findings:
                    findings.append(interp)

        scores["temporal_consistency"] = round(temporal_score, 1)

        # 7. WEB ARCHIVE EVIDENCE (5% weight)
        web_score = 30  # low default
        if wayback:
            archives = wayback.get("archives", [])
            has_archaeological = any(a.get("keyword") in ["archaeology", "excavation", "ancient", "ruins"] for a in archives)

            if has_archaeological:
                web_score = 85
                findings.append("Archaeological content found in web archives — prior research at this location")
                modifiers.append({"factor": "wayback_archaeology", "effect": "+20%", "reason": "Prior research confirms archaeological interest"})
            elif len(archives) > 5:
                web_score = 55
                findings.append(str(len(archives)) + " archived web pages mention this area")
            else:
                web_score = 30

        scores["web_evidence"] = round(web_score, 1)

        # ─── WEIGHTED FUSION ───
        weights = {
            "satellite_anomalies": 0.35,
            "soil_preservation": 0.20,
            "seismic_filter": 0.10,
            "water_table": 0.10,
            "osm_context": 0.10,
            "temporal_consistency": 0.10,
            "web_evidence": 0.05,
        }

        fused_score = sum(scores[k] * weights[k] for k in weights)
        fused_score = round(min(max(fused_score, 0), 100), 1)

        # Apply modifiers (stacking bonuses/penalties)
        total_modifier = 0
        for mod in modifiers:
            pct = mod["effect"].replace("%", "").replace("+", "")
            try:
                total_modifier += float(pct)
            except ValueError:
                pass

        final_score = round(min(max(fused_score + total_modifier, 0), 100), 1)

        # Determine confidence and recommendation
        if final_score > 70 and n_points > 15 and not warnings:
            confidence = "high"
            recommendation = "Strong candidate. Deploy ground-penetrating radar or magnetometer survey."
        elif final_score > 50:
            confidence = "medium"
            recommendation = "Promising. Conduct targeted field survey with magnetometer."
        elif final_score > 30:
            confidence = "low"
            recommendation = "Weak signal. Collect more satellite data or try different season."
        else:
            confidence = "very low"
            recommendation = "No significant archaeological signatures. Try a different location."

        if warnings:
            confidence += " (warnings apply)"

        return {
            "fused_score": final_score,
            "component_scores": scores,
            "weights": weights,
            "modifiers": modifiers,
            "confidence": confidence,
            "recommendation": recommendation,
            "findings": findings,
            "warnings": warnings,
            "data_sources_used": {
                "satellite": n_points > 0,
                "soil": soil is not None and "properties" in (soil or {}),
                "seismic": faults is not None,
                "water_table": water_table is not None,
                "osm": osm is not None,
                "wayback": wayback is not None,
                "temporal": temporal is not None and "trend" in (temporal or {}),
            },
            "interpretation": self._interpret_fused(final_score, confidence, findings, warnings)
        }

    def _interpret_fused(self, score: float, confidence: str, findings: list, warnings: list) -> list:
        """Generate human-readable interpretation of fused results."""
        interp = []

        if score > 70:
            interp.append("COMBINED ASSESSMENT: Strong archaeological potential. Multiple independent data sources corroborate.")
        elif score > 50:
            interp.append("COMBINED ASSESSMENT: Moderate potential. Some signals present but not all sources confirm.")
        elif score > 30:
            interp.append("COMBINED ASSESSMENT: Weak signal. Environmental factors may be masking or mimicking features.")
        else:
            interp.append("COMBINED ASSESSMENT: No significant archaeological signatures across any data source.")

        if warnings:
            interp.append("CAVEATS: " + "; ".join(warnings[:3]))

        signal_count = sum(1 for f in findings if "strong" in f.lower() or "excellent" in f.lower() or "confirmed" in f.lower())
        if signal_count >= 3:
            interp.append("STRONG CONVERGENCE: " + str(signal_count) + " independent strong signals. High reliability.")
        elif signal_count >= 2:
            interp.append("MODERATE CONVERGENCE: " + str(signal_count) + " strong signals. Worth investigating.")

        return interp
