"""
SatAI — Cross-modal optical + SAR fusion tool (PS mandatory pair analysis).
Extracts complementary information: optical gives colour/texture/context,
SAR gives structure/roughness/moisture and is cloud- and night-independent.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseTool

SYSTEM = (
    "You are SatAI-Fusion, a specialist in joint analysis of co-registered "
    "optical and SAR imagery. Image 1 is the OPTICAL source (true/multi "
    "colour), Image 2 is the SAR source (radar backscatter, speckled gray or "
    "false-colour polarisation composite). Reason about what each sensor "
    "contributes and what only their combination reveals: built-up areas "
    "(bright radar doubles + optical roofs), water (dark SAR + optical tone), "
    "vegetation, flooded vegetation, roughness, moisture, ships vs containers, "
    "shadow vs smooth surfaces. End with `CONFIDENCE: <0-100>`."
)


class SARFusionTool(BaseTool):
    tool_id = "sar_fusion"
    description = ("Optical + SAR co-registered pair analysis: complementary "
                   "extraction of built-up, water, vegetation, flood and "
                   "surface-roughness information.")
    required_images = 2
    ps_requirement = "Mandatory: cross-modal (optical + SAR) paired-image analysis"

    async def execute(self, query: str, images: list[str],
                      metadata: dict | None = None,
                      **params) -> Dict[str, Any]:
        md = metadata or {}
        stats = md.get("sar_stats") or {}
        stat_block = ""
        if stats:
            stat_block = (
                "\nPRE-COMPUTED SAR STATISTICS (algorithmic, measured on the raw "
                "backscatter raster — cite these numbers, do not re-estimate):\n"
                + "\n".join(f"- {k}: {v}" for k, v in stats.items())
                + "\n"
            )
        user = (
            "Joint optical (image 1) + SAR (image 2) analysis task.\n"
            f"User query: {query}\n"
            f"{stat_block}\n"
            "Reply using exactly this skeleton:\n"
            "OPTICAL OBSERVATIONS: <colour, texture, visible land cover>\n"
            "SAR OBSERVATIONS: <backscatter patterns, bright/dark signatures, "
            "speckle, artificial doubles>\n"
            "JOINT FINDINGS: <bullet list combining both: e.g. built-up regions "
            "confirmed by radar doubles, calm water dark in both, flooded "
            "vegetation (dark optical + bright SAR)>\n"
            "BUILT-UP AREAS: <where and how confident>\n"
            "WATER-COVERED AREAS: <where and how confident>\n"
            "CAVEATS: <registration, resolution mismatch, speckle, layover>\n"
            "End with `CONFIDENCE: <0-100>`."
        )
        text, conf, meta = await self.ask(SYSTEM, user, images[:2],
                                          max_tokens=768)
        return {"text": text, "confidence": conf, "model": meta["model"],
                "metadata": {"self_reported": meta["self_reported_confidence"],
                             "sar_stats": stats or None}}
