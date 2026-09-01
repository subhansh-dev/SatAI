"""
SatAI — Caption Tool
Generate detailed scene descriptions for satellite images.
"""
import time
from .base import BaseTool


class CaptionTool(BaseTool):
    tool_id = "caption"
    description = "Generate a detailed caption describing the satellite image"
    required_inputs = ["image"]

    def __init__(self, vlm_client):
        self.vlm = vlm_client

    async def execute(self, images: list = None, **kwargs) -> dict:
        start = time.time()
        images = images or []

        prompt = (
            "Provide a detailed caption for this remote sensing / satellite image. "
            "Include:\n"
            "- Land cover types (urban, agricultural, forest, water, barren, etc.)\n"
            "- Key objects (buildings, roads, vehicles, ships, aircraft, infrastructure)\n"
            "- Spatial layout and relationships\n"
            "- Notable features, patterns, or anomalies\n\n"
            "Be comprehensive but concise (3-5 sentences)."
        )

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            images=images[:1],
        )
        caption = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._wrap({"text": caption, "confidence": 0.85}, start)
