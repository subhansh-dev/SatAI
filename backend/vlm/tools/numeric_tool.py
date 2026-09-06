"""
SatAI — Numeric / counting tool (PS example queries include counting).
Was registered but UNREACHABLE in the old build; the classifier now routes
count/quantity questions here explicitly.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from core import config

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


class NumericTool(BaseTool):
    tool_id = "numeric"
    description = ("Counting / quantitative VQA: 'How many ships...', area and "
                   "length estimates with scale cues.")
    required_images = 1
    ps_requirement = "Supports single-image VQA (quantitative queries)"

    async def execute(self, query: str, images: list[str],
                      metadata: dict | None = None,
                      **params) -> Dict[str, Any]:
        n_samples = max(1, int(getattr(config, "SELF_CONSISTENCY_SAMPLES", 3)))
        user = (
            f"Quantitative remote-sensing question: {query}\n\n"
            "Inspect the image carefully and count/measure methodically. "
            "Reply with a 1-3 sentence justification, then `ANSWER: ...` "
            "and `CONFIDENCE: <0-100>`."
        )
        # ---- self-consistency sampling (calibrated confidence) ------------
        # Counting is the noisiest VLM task; sampling n times at moderate
        # temperature and taking the modal answer + agreement bonus measures
        # how *stable* the answer is instead of trusting one greedy guess.
        temps = [0.0] + [0.6] * (n_samples - 1)
        results = []
        for t in temps[:n_samples]:
            text, conf, meta = await self.ask(SYSTEM, user, images[:1],
                                              max_tokens=384, temperature=t)
            results.append((self._extract_answer(text), text, conf, meta))
        answers = [r[0] for r in results if r[0] is not None]
        if not answers:
            # nothing parseable — report honestly with dinged confidence
            text = results[0][1] if results else ""
            conf = round(results[0][2] * 0.5, 3) if results else 0.0
            return {
                "text": text or "no quantitative answer could be parsed",
                "confidence": conf,
                "confidence_source": "unparsed",
                "model": results[0][3]["model"] if results else self.vlm.active_model,
                "metadata": {"parse_ok": False,
                             "samples": n_samples},
            }
        # modal answer (ties -> most common, then first seen)
        counts: Dict[str, int] = {}
        for a in answers:
            counts[a] = counts.get(a, 0) + 1
        answer = max(counts, key=lambda k: (counts[k], -answers.index(k)))
        agreement = counts[answer] / len(answers)
        base_conf = max(c for a, _tx, c, _m in results if a == answer)
        # agreement bonus: unanimous -> +0.1, majority -> less
        bonus = 0.1 * (agreement - 1.0 / max(len(counts), 2)) * (len(counts) / (n_samples - len(counts) + 1))
        confidence = round(min(0.99, base_conf + max(0.0, bonus)), 3)
        ref_meta = next((m for a, _tx, _c, m in results if a == answer), None)
        note = ("" if len(counts) == 1 else
                f" (self-consistency: {counts[answer]}/{len(answers)} samples agree)")
        return {
            "text": answer + note,
            "confidence": confidence,
            "confidence_source": "self_consistency+model_self_report",
            "model": (ref_meta or results[0][3])["model"],
            "metadata": {"parse_ok": True,
                         "samples": n_samples,
                         "answers": answers,
                         "agreement": round(agreement, 3),
                         "self_reported": (ref_meta or results[0][3]).get("self_reported_confidence")},
        }

    @staticmethod
    def _extract_answer(text: str) -> str | None:
        m = _ANSWER_RE.search(text or "")
        if m:
            return m.group(1).strip().rstrip(".") or None
        # NO free-number fallback: grabbing "the last number anywhere" turned
        # years and GSD values into fabricated counts. An unparseable answer
        # is reported as such (confidence dinged) instead of guessed.
        return None
