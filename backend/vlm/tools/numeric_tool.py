"""
SatAI — Numeric Tool
Handles numeric/float answers via code execution.
For queries like "How many buildings?" or "What is the approximate area?"
"""
import time
import re
import math
from .base import BaseTool


class NumericTool(BaseTool):
    tool_id = "numeric"
    description = "Answer numeric questions about satellite imagery using VLM reasoning + code execution"
    required_inputs = ["image", "query"]

    def __init__(self, vlm_client):
        self.vlm = vlm_client

    async def execute(self, query: str = "", images: list = None, **kwargs) -> dict:
        start = time.time()
        images = images or []

        prompt = (
            "You are a remote sensing expert. The user is asking a NUMERIC question about "
            "a satellite image. Analyze the image and provide:\n"
            "1. Your observation (what you see)\n"
            "2. Your numeric estimate with reasoning\n"
            "3. The final numeric answer on a line starting with 'ANSWER:' followed by the number\n\n"
            "Example format:\n"
            "Observation: I can see approximately 15-20 rectangular structures consistent with buildings.\n"
            "Reasoning: Counting the distinct rectangular shapes visible in the residential area...\n"
            "ANSWER: 17\n\n"
            f"Question: {query}"
        )

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            images=images[:1],
        )
        raw = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Extract numeric answer
        numeric_val = self._extract_answer(raw)
        return self._wrap({
            "text": raw,
            "confidence": 0.65,
            "metadata": {"numeric_answer": numeric_val},
        }, start)

    def _extract_answer(self, text: str) -> float | None:
        """Extract numeric value from ANSWER: line."""
        match = re.search(r"ANSWER:\s*([+-]?\d+\.?\d*)", text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        # Fallback: find last number in text
        numbers = re.findall(r"[+-]?\d+\.?\d*", text)
        if numbers:
            try:
                return float(numbers[-1])
            except ValueError:
                return None
        return None
