"""
SatAI — VQA Tool
Single-image visual question answering.
"""
import time
from .base import BaseTool


class VQATool(BaseTool):
    tool_id = "vqa"
    description = "Answer natural-language questions about a single satellite image"
    required_inputs = ["image", "query"]

    def __init__(self, vlm_client):
        self.vlm = vlm_client

    async def execute(self, query: str = "", images: list = None, **kwargs) -> dict:
        start = time.time()
        images = images or []

        prompt = (
            "You are a remote sensing expert analyzing satellite imagery. "
            "Answer the following question precisely and concisely based on what you see. "
            "If uncertain, state your uncertainty.\n\n"
            f"Question: {query}"
        )

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            images=images[:1],
        )
        answer = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._wrap({"text": answer, "confidence": 0.8}, start)
