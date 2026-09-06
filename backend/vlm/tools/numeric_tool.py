"""
SatAI — Numeric / counting tool (PS example queries include counting).
Was registered but UNREACHABLE in the old build; the classifier now routes
count/quantity questions here explicitly.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from .base import BaseTool

SYSTEM = (
    "You are SatAI-Count, a precise counting and measurement engine for "
    "remote-sensing imagery. You count objects (buildings, vehicles, ships, "
    "fields, storage tanks...), estimate areas/lengths when scale cues exist, "
    "and answer quantitative questions about the image. Count systematically "
    "(e.g. row by row). If an exact count is impossible due to resolution, "
    "give your best range and say why.\n"
    "Final line MUST be exactly `ANSWER: <number or short phrase>` followed "
    "by `CONFIDENCE: <0-100>`."
)

_ANSWER_RE = re.compile(r"ANSWER\s*[:=]\s*(.+?)(?:\n|$)", re.IGNORECASE)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


class NumericTool(BaseTool):
    tool_id = "numeric"
    description = ("Counting / quantitative VQA: 'How many ships...', area and "
                   "length estimates with scale cues.")
    required_images = 1
    ps_requirement = "Supports single-image VQA (quantitative queries)"

    async def execute(self, query: str, images: list[str],
                      **params) -> Dict[str, Any]:
        user = (
            f"Quantitative remote-sensing question: {query}\n\n"
            "Inspect the image carefully and count/measure methodically. "
            "Reply with a 1-3 sentence justification, then `ANSWER: ...` "
            "and `CONFIDENCE: <0-100>`."
        )
        text, conf, meta = await self.ask(SYSTEM, user, images[:1],
                                          max_tokens=384, temperature=0.0)
        answer = self._extract_answer(text)
        confidence = conf if answer else round(conf * 0.5, 3)
        return {
            "text": answer or text,
            "confidence": confidence,
            "confidence_source": "parsed_answer+model_self_report" if answer
                                 else "unparsed",
            "model": meta["model"],
            "metadata": {"self_reported": meta["self_reported_confidence"],
                         "parse_ok": bool(answer)},
        }

    @staticmethod
    def _extract_answer(text: str) -> str | None:
        m = _ANSWER_RE.search(text)
        if m:
            return m.group(1).strip().rstrip(".") or None
        # fallback: last number in the text
        nums = _NUM_RE.findall(text)
        return nums[-1] if nums else None
