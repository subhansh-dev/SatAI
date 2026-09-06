"""SatAI — Captioning / scene-description tool (PS single-image task option A)."""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseTool

SYSTEM = (
    "You are SatAI, an expert remote-sensing scene-description engine. You "
    "produce structured, evidence-grounded descriptions of satellite and "
    "aerial images (optical, multispectral, SAR). Follow the exact output "
    "skeleton you are given, be quantitative where possible, and never "
    "invent objects that are not visible.\n"
    "End your reply with a final line `CONFIDENCE: <0-100>`."
)


class CaptionTool(BaseTool):
    tool_id = "caption"
    description = ("Land-cover and scene description: dominant classes, major "
                   "objects, spatial layout — PS single-image task option A.")
    required_images = 1
    ps_requirement = "Single-image task: captioning / scene description"

    async def execute(self, query: str = "", images: list[str] = (),
                      model: str | None = None, **params) -> Dict[str, Any]:
        focus = query.strip() or "Describe this image."
        user = (
            f"Produce a remote-sensing scene description for the attached image.\n"
            f"User emphasis: {focus}\n\n"
            "Use exactly this skeleton:\n"
            "SCENE OVERVIEW: <1-2 sentences — environment type, apparent "
            "setting (urban/rural/coastal/etc.), approximate development level>\n"
            "LAND COVER: <dominant classes with rough percentages, e.g. "
            "built-up ~30%, vegetation ~45%, water ~10%, bare soil ~15%>\n"
            "MAJOR OBJECTS: <bullet list of identifiable features: roads, "
            "buildings, fields, rivers, ships, aircraft, clouds...>\n"
            "SPATIAL PATTERN: <how the classes are arranged, orientation, "
            "edges of scene>\n"
            "SENSOR NOTES: <apparent resolution, sensor type guess "
            "(optical/SAR/multispectral), artifacts, season if inferable>\n"
            "End with `CONFIDENCE: <0-100>`."
        )
        text, conf, meta = await self.ask(SYSTEM, user, images[:1],
                                          max_tokens=640, model=model)
        return {"text": text, "confidence": conf, "model": meta["model"],
                "metadata": {"self_reported": meta["self_reported_confidence"]}}
