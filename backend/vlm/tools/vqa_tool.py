"""SatAI — Single-image VQA tool (PS mandatory baseline)."""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseTool

SYSTEM = (
    "You are SatAI, an expert remote-sensing analyst specialising in satellite "
    "and aerial imagery (optical, multispectral and SAR). You answer visual "
    "questions precisely, referencing what is actually visible. Consider "
    "typical RS characteristics: land-cover classes (built-up, cropland, "
    "forest, grassland, wetland, water, bare soil), object scale, resolution, "
    "sensor artefacts, shadows and seasonality. Be factual and concise. If "
    "something is not determinable from the image, say so explicitly.\n"
    "Formatting rules: answer the question directly in 1-4 short paragraphs. "
    "Quantities must be specific. End your reply with a final line "
    "`CONFIDENCE: <0-100>` estimating how confident you are in the answer."
)


class VQATool(BaseTool):
    tool_id = "vqa"
    description = ("Single-image visual question answering about satellite/"
                   "aerial imagery — the PS mandatory baseline task.")
    required_images = 1
    ps_requirement = "Mandatory: single-image VQA"

    async def execute(self, query: str, images: list[str],
                      **params) -> Dict[str, Any]:
        user = (
            f"Remote-sensing image analysis task.\n"
            f"User question: {query}\n\n"
            "Answer the question about the attached image. Use precise "
            "remote-sensing vocabulary. End with `CONFIDENCE: <0-100>`."
        )
        text, conf, meta = await self.ask(SYSTEM, user, images[:1],
                                          max_tokens=768)
        return {"text": text, "confidence": conf, "model": meta["model"],
                "metadata": {"self_reported": meta["self_reported_confidence"]}}
