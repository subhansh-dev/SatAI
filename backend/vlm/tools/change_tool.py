"""
SatAI — Change Description Tool
Bi-temporal change detection: describe what changed between two dates.
"""
import time
from .base import BaseTool


class ChangeDescTool(BaseTool):
    tool_id = "change_desc"
    description = "Describe changes between two satellite images of the same area"
    required_inputs = ["before_image", "after_image"]

    def __init__(self, vlm_client):
        self.vlm = vlm_client

    async def execute(self, query: str = "", images: list = None, **kwargs) -> dict:
        start = time.time()
        images = images or []

        prompt = (
            "You are analyzing two satellite images of the SAME geographic area taken at "
            "different times. Image 1 is the BEFORE image; Image 2 is the AFTER image.\n\n"
            "Describe ALL observable changes between the two dates:\n"
            "- New construction or demolition\n"
            "- Vegetation changes (deforestation, new growth, crop changes)\n"
            "- Water body changes (expansion, drying, flooding)\n"
            "- Road/infrastructure changes\n"
            "- Land cover transitions\n"
            "- Any other notable differences\n\n"
            "For each change, state: WHAT changed, WHERE (relative location), and HOW MUCH "
            "(estimate area if possible).\n\n"
            "Be precise and systematic."
        )
        if query:
            prompt += f"\n\nAdditional focus: {query}"

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            images=images[:2],
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._wrap({
            "text": text,
            "confidence": 0.75,
            "metadata": {"mode": "bitemporal", "num_images": len(images[:2])},
        }, start)
