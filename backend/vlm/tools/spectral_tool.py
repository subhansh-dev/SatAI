"""
SatAI — Spectral Index Tool
Algorithmic, reproducible band-math over multispectral GeoTIFFs:
NDVI (vegetation), NDWI (open water), NDBI (built-up).

This is the "measured, not guessed" differentiator: the numbers come from
the ORIGINAL spectral bands (Sentinel-2 / Cartosat-2S conventions), not
from the 8-bit VLM view, and are injected verbatim into the answer.
Real-world ISRO/NRSC workflows (crop monitoring, flood extent, LULC) run
on exactly these indices.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from ..image_utils import spectral_index
from .base import BaseTool

_INDEX_ASK_RE = re.compile(r"\b(ndvi|ndwi|ndbi|vegetation index|water index|"
                           r"built[- ]?up index|moisture)\b", re.IGNORECASE)


class SpectralIndexTool(BaseTool):
    tool_id = "spectral_index"
    description = ("Algorithmic spectral indices (NDVI vegetation, NDWI water, "
                   "NDBI built-up) computed from multispectral GeoTIFF bands, "
                   "with colour-coded map, class fractions and area estimates.")
    required_images = 1
    allowed_params = ["index"]
    ps_requirement = ("Extends single-image analysis with reproducible "
                      "band-math (Sentinel-2 / Cartosat-2S multispectral)")

    async def execute(self, query: str, images: list[str],
                      metadata: dict | None = None,
                      **params) -> Dict[str, Any]:
        md = metadata or {}
        rasters = md.get("_rasters") or []
        geo = (rasters[0].get("geo") if rasters else None) or {}

        index = self._detect_index(query, md)
        if not rasters or not rasters[0].get("raw"):
            return {
                "text": "Spectral indices need the original multispectral "
                        "raster — the prepared VLM view has no spectral "
                        "bands. Re-send the GeoTIFF/TIFF file.",
                "confidence": 0.2, "confidence_source": "error",
                "model": self.vlm.active_model,
            }

        result = spectral_index(rasters[0]["raw"], index=index, geo=geo)
        if "error" in result:
            return {
                "text": f"Spectral index could not be computed: {result['error']}",
                "confidence": 0.3,
                "confidence_source": "algorithmic_degenerate",
                "model": self.vlm.active_model,
                "metadata": {"index_request": index},
            }

        stats = result["stats"]
        lines = [
            f"**{result['title']} ({stats['index']})** — computed directly "
            f"from the uploaded multispectral raster "
            f"({stats['definition']}, bands {result['bands_used']}).",
            "",
            f"- Scene mean: **{stats['mean']:+.3f}** (median {stats['median']:+.3f}, "
            f"5–95% range {stats['p05']:+.3f} … {stats['p95']:+.3f})",
        ]
        tf = stats["threshold_fraction"]
        lines.append(f"- {tf['description'].split('(')[0].strip()}: "
                     f"**{tf['fraction'] * 100:.1f}%** of the scene")
        ae = stats.get("area_estimate")
        if ae:
            key = next(k for k in ae if k.startswith("area_above") and k.endswith("_km2"))
            lines.append(f"- Estimated area above threshold: "
                         f"**{ae[key]:,.2f} km²** "
                         f"(at {ae['ground_sample_dist_m']:g} m/px)")
        for w in result.get("warnings", []):
            lines.append(f"- Note: {w}")
        lines.append("")
        if result["index"] == "ndvi":
            lines.append("Interpretation: values > 0.4 mark photosynthetically "
                         "active vegetation; near-zero or negative values are "
                         "bare soil, water or built surfaces. Use the colour "
                         "map (brown = low, green = high) as visual evidence.")
        elif result["index"] == "ndwi":
            lines.append("Interpretation: positive values delineate open water "
                         "(flood extent, reservoirs); vegetation and built-up "
                         "are negative. Pairs naturally with SAR dark-water "
                         "confirmation in cross-modal checks.")
        else:
            lines.append("Interpretation: positive values highlight built-up / "
                         "bare-rock surfaces; vegetation and water are negative.")
        lines.append("These figures are algorithmic band-math — fully "
                     "reproducible from the uploaded file, independent of the "
                     "vision model.")

        return {
            "text": "\n".join(lines),
            "confidence": 0.93,
            "confidence_source": "algorithmic_deterministic",
            "model": self.vlm.active_model,
            "bounding_boxes": None,
            "metadata": {"bands_used": result["bands_used"],
                         "warnings": result.get("warnings", []),
                         "self_reported": False,
                         "spectral": {"index": result["index"],
                                      "stats": stats,
                                      "preview_b64": result.get("index_preview_b64")}},
        }

    @staticmethod
    def _detect_index(query: str, metadata: Dict[str, Any]) -> str:
        forced = (metadata or {}).get("index")
        if isinstance(forced, str) and forced.lower() in ("ndvi", "ndwi", "ndbi"):
            return forced.lower()
        m = _INDEX_ASK_RE.search(query or "")
        if not m:
            return "ndvi"
        token = m.group(0).lower()
        if "ndwi" in token or "water index" in token or "moisture" in token:
            return "ndwi"
        if "ndbi" in token or "built" in token:
            return "ndbi"
        return "ndvi"
