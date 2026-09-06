"""
SatAI — Bi-temporal change analysis tool (PS mandatory multi-image task).
Change description + change-based VQA in one structured pass, so a question
like "What changed between these two dates and where?" is answered directly.
A heuristic spatial change map (visual_evidence.render_change_map) is added
by the controller as visual evidence.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseTool

SYSTEM = (
    "You are SatAI-Change, a bi-temporal remote-sensing change analyst. You "
    "compare two co-registered images of the same area captured on different "
    "dates (optical, SAR, or mixed) and report precisely what changed, where, "
    "in which direction, and how strongly — or state confidently that no "
    "significant change is visible. Beware: seasonal/illumination differences "
    "are NOT land-cover change; sensor differences between optical and SAR "
    "are NOT change either. End your reply with `CONFIDENCE: <0-100>`."
)


class ChangeDescTool(BaseTool):
    tool_id = "change_desc"
    description = ("Bi-temporal change description and change-based VQA from "
                   "two images of the same area (PS mandatory multi-image task).")
    required_images = 2
    ps_requirement = "Mandatory: multitemporal change understanding + change-VQA"

    async def execute(self, query: str, images: list[str],
                      metadata: Dict[str, Any] | None = None,
                      model: str | None = None, **params) -> Dict[str, Any]:
        metadata = metadata or {}
        dates = metadata.get("dates") or []
        date_a, date_b = (dates + ["Image 1", "Image 2"])[:2]
        specific = bool(query and query.strip() and
                        query.strip().lower() not in
                        ("what changed between these two dates?", "what changed?"))

        user = (
            "You receive two remote-sensing images of the SAME area.\n"
            f"- BEFORE: {date_a}\n- AFTER: {date_b}\n\n"
            f"User question: {query.strip() or 'What changed between these two dates, and where?'}\n\n"
            "Reply using exactly this skeleton:\n"
            "CHANGE SUMMARY: <2-3 sentence verdict: what changed overall, or "
            "'no significant change' if that is the case>\n"
            "CHANGED AREAS: <bullet list; for each: location in scene (e.g. "
            "upper-left, centre-east), class transition (e.g. vegetation -> "
            "built-up, water -> dry land), and approximate extent>\n"
            "DIRECTION: <increase / decrease / appeared / disappeared per class>\n"
            "MAGNITUDE: <minor / moderate / major + rough % of scene affected>\n"
            "CONFUSERS: <seasonal, illumination, sensor or registration effects "
            "that could mimic change here>\n"
            + ("Directly answer the user's specific question in the summary.\n"
               if specific else "")
            + "End with `CONFIDENCE: <0-100>`."
        )
        text, conf, meta = await self.ask(SYSTEM, user, images[:2],
                                          max_tokens=768, model=model)
        return {"text": text, "confidence": conf, "model": meta["model"],
                "metadata": {"dates": [str(date_a), str(date_b)],
                             "self_reported": meta["self_reported_confidence"]}}
