"""
SatAI — Area / Quantity Quantifier Tool

Answers "how much / how many hectares / % of the scene" questions with a
MEASURED number instead of a VLM guess:

- Algorithmic path (multispectral GeoTIFF/TIFF available): detect the class
  the query asks about (water / vegetation / built-up — or all three when no
  class is named), run the matching spectral-index band-math on the ORIGINAL
  raster, and convert the above-threshold pixel fraction into hectares / km²
  using the georeference's ground sample distance. Fully reproducible.
- VLM fallback (PNG/JPEG or band-math failure): scale-cue estimation through
  the counting specialist — honest, self-reported, and labelled as such in
  metadata (never presented as measured band-math).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..image_utils import spectral_index
from ..lang import LANG_HINT
from .base import BaseTool
from .numeric_tool import SYSTEM as COUNT_SYSTEM

_ANSWER_RE = re.compile(r"ANSWER\s*[:=]\s*(.+?)(?:\n|$)", re.IGNORECASE)

_CLASS_RES = [
    ("ndwi", re.compile(
        r"\b(water|flood|lake|river|reservoir|pond|inundat\w*|ndwi|"
        r"water[- ]body|open water|pa?ni|jal)\b", re.IGNORECASE)),
    ("ndvi", re.compile(
        r"\b(vegetation|forest|crop\w*|farmland|green\w*|tree\w*|ndvi|"
        r"photosynth\w*|hari|fasal)\b", re.IGNORECASE)),
    ("ndbi", re.compile(
        r"\b(built[- ]?up|urban|settlement\w*|city|cities|town\w*|concret\w*|"
        r"ndbi|roof\w*|house\w*|impervious|shahar|shehar)\b", re.IGNORECASE)),
]

_CLASS_LABEL = {
    "ndwi": "open water (NDWI above threshold)",
    "ndvi": "photosynthetically active vegetation (NDVI above threshold)",
    "ndbi": "built-up / impervious surfaces (NDBI above threshold)",
}


class QuantityTool(BaseTool):
    tool_id = "quantity"
    description = ("Area / quantity quantifier: hectares, km² and % of scene "
                   "for water / vegetation / built-up from band-math (falls "
                   "back to scale-cue VLM estimation without a GeoTIFF).")
    required_images = 1
    allowed_params = ["index"]
    ps_requirement = ("Extends single-image quantitative VQA with measured "
                      "area extents (ha / km²) from multispectral band-math")

    async def execute(self, query: str, images: list[str],
                      metadata: dict | None = None,
                      model: str | None = None, **params) -> Dict[str, Any]:
        md = metadata or {}
        rasters = md.get("_rasters") or []
        raw = rasters[0].get("raw") if rasters else None
        if raw:
            geo = rasters[0].get("geo") or {}
            alg = self._algorithmic(query, raw, geo, md)
            if alg["confidence_source"] != "algorithmic_degenerate":
                return alg
            # PNG/JPEG or unreadable bands — fall through to the scale-cue
            # VLM estimate, carrying the band-math reason as a caveat.
            fallback = await self._vlm_fallback(query, images, model)
            fallback["metadata"]["band_math_errors"] = \
                alg["metadata"].get("errors", [])
            return fallback
        return await self._vlm_fallback(query, images, model)

    # -------------------------------------------------------- algorithmic
    def _algorithmic(self, query: str, raw: bytes, geo: Dict[str, Any],
                     md: Dict[str, Any]) -> Dict[str, Any]:
        forced = md.get("index")
        if isinstance(forced, str) and forced.lower() in ("ndvi", "ndwi", "ndbi"):
            indices: List[str] = [forced.lower()]
        else:
            detected = self._detect_class(query)
            indices = [detected] if detected else ["ndwi", "ndvi", "ndbi"]

        results: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []
        for ix in indices:
            r = spectral_index(raw, index=ix, geo=geo)
            if "error" in r:
                errors.append(f"{ix}: {r['error']}")
            else:
                results[ix] = r

        if not results:
            return {
                "text": "Area quantification could not be computed from the "
                        "uploaded raster (" + "; ".join(errors or
                        ["no usable bands"]) + "). Re-send a multispectral "
                        "GeoTIFF/TIFF with 4+ bands, or ask a scale-cue "
                        "estimate explicitly.",
                "confidence": 0.3,
                "confidence_source": "algorithmic_degenerate",
                "model": self.vlm.active_model,
                "metadata": {"method": "band_math", "errors": errors},
            }

        primary_ix = (indices[0] if indices[0] in results
                      else max(results,
                               key=lambda k: results[k]["stats"]
                               ["threshold_fraction"]["fraction"]))
        lines: List[str] = []
        summary: Dict[str, Dict[str, Any]] = {}

        for ix, r in results.items():
            st = r["stats"]
            tf = st["threshold_fraction"]
            frac = float(tf["fraction"])
            pct = frac * 100.0
            ae = st.get("area_estimate")
            ha = km2 = None
            if ae:
                key_m2 = next(k for k in ae if k.startswith("area_above")
                              and k.endswith("_m2"))
                m2 = float(ae[key_m2])
                ha, km2 = m2 / 10_000.0, m2 / 1e6
            summary[ix] = {"fraction": round(frac, 4), "percent": round(pct, 2),
                           "area_ha": round(ha, 3) if ha is not None else None,
                           "area_km2": round(km2, 5) if km2 is not None else None,
                           "gsd_m": ae.get("ground_sample_dist_m") if ae else None}

        # ---- direct ANSWER line (the VQA-style headline) ------------------
        p = summary[primary_ix]
        label = _CLASS_LABEL[primary_ix]
        if p["area_ha"] is not None:
            headline = (f"ANSWER: **~{p['area_ha']:,.2f} hectares** "
                        f"({p['percent']:.1f}% of the scene) — {label}")
        else:
            headline = (f"ANSWER: **{p['percent']:.1f}% of the scene** — "
                        f"{label} (no georeference — absolute area "
                        f"unavailable)")
        lines.append(headline)
        lines.append("")

        if len(results) == 1:
            st = results[primary_ix]["stats"]
            lines.append(f"Measured by band-math on the original raster "
                         f"({st['definition']}, threshold "
                         f"{st['threshold_fraction']['threshold']}).")
            lines.append(f"- Fraction above threshold: "
                         f"**{p['percent']:.2f}%** of the scene")
            if p["area_ha"] is not None:
                lines.append(f"- Absolute extent: **{p['area_ha']:,.2f} ha** "
                             f"({p['area_km2']:,.5f} km²) at "
                             f"{p['gsd_m']:g} m/px GSD")
            else:
                lines.append("- Absolute extent: unavailable — the file has "
                             "no ground sample distance (add georeference / "
                             "upload the GeoTIFF)")
        else:
            lines.append("Class extents from simultaneous band-math "
                         "(water = NDWI, vegetation = NDVI, built-up = NDBI):")
            for ix, s in summary.items():
                unit = (f"~{s['area_ha']:,.2f} ha" if s["area_ha"] is not None
                        else "area n/a (no GSD)")
                lines.append(f"- {_CLASS_LABEL[ix].split(' (')[0]}: "
                             f"**{s['percent']:.2f}%** — {unit}")
        lines.append("")
        lines.append("These figures are algorithmic band-math — reproducible "
                     "from the uploaded file, independent of the vision model.")

        return {
            "text": "\n".join(lines),
            "confidence": 0.93,
            "confidence_source": "algorithmic_deterministic",
            "model": self.vlm.active_model,
            "bounding_boxes": None,
            "metadata": {
                "method": "band_math",
                "primary_index": primary_ix,
                "quantity": summary,
                "self_reported": False,
                "spectral": {
                    "index": results[primary_ix]["index"],
                    "stats": results[primary_ix]["stats"],
                    "preview_b64": results[primary_ix].get("index_preview_b64"),
                },
            },
        }

    # -------------------------------------------------------- VLM fallback
    async def _vlm_fallback(self, query: str, images: list[str],
                            model: str | None) -> Dict[str, Any]:
        """No usable raster (PNG/JPEG etc.) — scale-cue estimate via the
        counting specialist, clearly labelled as VLM, not measurement."""
        user = (
            f"Quantitative remote-sensing question: {query}\n\n"
            "No multispectral raster is attached, so estimate from scale "
            "cues in the image (if any) and state your assumptions. "
            f"{LANG_HINT}\n"
            "Reply with a 1-3 sentence justification, then `ANSWER: ...` "
            "and `CONFIDENCE: <0-100>`."
        )
        text, conf, meta = await self.ask(COUNT_SYSTEM, user, images[:1],
                                          max_tokens=384, model=model)
        parsed = _ANSWER_RE.search(text)
        return {
            "text": text or "no quantitative answer could be parsed",
            "confidence": conf,
            "confidence_source": ("parsed_answer+model_self_report"
                                  if parsed else "model_self_report"),
            "model": meta["model"],
            "metadata": {
                "method": "vlm_scale_estimate",
                "fallback": True,
                "parse_ok": bool(parsed),
                "self_reported": meta["self_reported_confidence"],
            },
        }

    # -------------------------------------------------------- class detect
    @staticmethod
    def _detect_class(query: str) -> Optional[str]:
        for ix, rx in _CLASS_RES:
            if rx.search(query or ""):
                return ix
        return None
