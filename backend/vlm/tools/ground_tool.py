"""
SatAI — Ground Tool
Visual grounding: locate objects with bounding boxes (HBB or OBB).
"""
import time
import json
import re
from .base import BaseTool


class GroundTool(BaseTool):
    tool_id = "ground"
    description = "Locate objects in the image with bounding boxes based on a text query"
    required_inputs = ["image", "query"]

    def __init__(self, vlm_client):
        self.vlm = vlm_client

    async def execute(self, query: str = "", images: list = None, **kwargs) -> dict:
        start = time.time()
        images = images or []
        output_format = kwargs.get("output_format", "hbb")

        prompt = (
            f"Locate all instances of the following in this satellite image:\n"
            f'"{query}"\n\n'
            f"For each instance, return a JSON array of objects with:\n"
            f'- "bbox": [x_min, y_min, x_max, y_max] normalized to 0-1000\n'
            f'- "confidence": float 0-1\n'
            f'- "label": short description\n\n'
            f"Return ONLY the JSON array. If nothing found, return []."
        )

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            images=images[:1],
        )
        raw = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        boxes = self._parse_boxes(raw)
        avg_conf = sum(b.get("confidence", 0) for b in boxes) / max(len(boxes), 1)

        return self._wrap({
            "text": f"Found {len(boxes)} instance(s) of '{query}'",
            "bounding_boxes": boxes,
            "confidence": avg_conf,
        }, start)

    def _parse_boxes(self, raw: str) -> list[dict]:
        """Robustly extract JSON bounding boxes from VLM output."""
        # Try direct parse
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass
        # Extract from code blocks
        for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"\[.*\]"]:
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1) if match.lastindex else match.group(0))
                except (json.JSONDecodeError, IndexError):
                    continue
        return []
