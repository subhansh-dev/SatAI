"""
SatAI — SAR-Optical Fusion Tool
Cross-modal analysis combining optical and SAR imagery.
"""
import time
from .base import BaseTool


class SARFusionTool(BaseTool):
    tool_id = "sar_fusion"
    description = "Analyze co-registered optical + SAR pair for complementary information extraction"
    required_inputs = ["optical_image", "sar_image"]

    def __init__(self, vlm_client):
        self.vlm = vlm_client

    async def execute(self, query: str = "", images: list = None, **kwargs) -> dict:
        start = time.time()
        images = images or []

        prompt = (
            "You are analyzing a PAIR of co-registered satellite images of the same area:\n"
            "- Image 1: OPTICAL (visible/near-infrared)\n"
            "- Image 2: SAR (synthetic aperture radar)\n\n"
            "Use BOTH modalities together to provide a comprehensive analysis:\n"
            "- Built-up areas (visible in optical, bright in SAR)\n"
            "- Water bodies (dark in optical with spectral signature, very dark in SAR)\n"
            "- Vegetation (green in optical, textured in SAR)\n"
            "- Bare soil/rock (visible in optical, smooth in SAR)\n"
            "- Flooded areas (darker in SAR than usual)\n\n"
            "The SAR image reveals what optical cannot: surface roughness, moisture content, "
            "structure beneath vegetation, and anything hidden by clouds.\n\n"
            "Provide a unified analysis that fuses information from both sensors."
        )
        if query:
            prompt += f"\n\nSpecific query: {query}"

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            images=images[:2],
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._wrap({
            "text": text,
            "confidence": 0.8,
            "metadata": {"mode": "crossmodal", "sensors": ["optical", "sar"]},
        }, start)
