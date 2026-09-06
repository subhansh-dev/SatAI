"""
SatAI — Text-guided region grounding tool (PS single-image task option B).
Returns normalised [0-1000] pixel boxes + robust parsing (direct JSON,
fenced JSON, then bracket regex). Confidence = model boxes x parse success.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .base import BaseTool

SYSTEM = (
    "You are SatAI-Ground, a remote-sensing visual grounding model. Given an "
    "image and a referring expression, you localise the referred regions "
    "strictly in JSON. Normalise all coordinates to a 0-1000 grid over the "
    "full image extent, origin top-left, axis x right, axis y down.\n"
    "Output ONLY a JSON array, then on the FINAL line the confidence:\n"
    '[{"label":"<short name>","bbox":[x1,y1,x2,y2],"confidence":0.0}]\n'
    "`CONFIDENCE: <0-100>`\n"
    "Rules: (x1,y1) is top-left, (x2,y2) bottom-right, x2>x1, y2>y1, all in "
    "[0,1000]. If the object is absent, output [] with CONFIDENCE still set. "
    "No other commentary."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)
_ARRAY_RE = re.compile(r"\[\s*\{.*?\}\s*\]", re.DOTALL)


def parse_boxes(raw: str) -> List[Dict[str, Any]]:
    """Robustly extract box dicts from model output."""
    candidates: List[str] = [raw.strip()]
    fence = _FENCE_RE.search(raw)
    if fence:
        candidates.insert(0, fence.group(1))
    arr = _ARRAY_RE.search(raw)
    if arr:
        candidates.insert(0, arr.group(0))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("boxes") or data.get("regions") or []
        if isinstance(data, list):
            return _sanitize(data)
    return []


def _sanitize(items: List[Any]) -> List[Dict[str, Any]]:
    boxes: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        bbox = it.get("bbox") or it.get("box") or it.get("bounding_box")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            continue
        x1, x2 = sorted((max(0.0, min(x1, 1000.0)), max(0.0, min(x2, 1000.0))))
        y1, y2 = sorted((max(0.0, min(y1, 1000.0)), max(0.0, min(y2, 1000.0))))
        if x2 - x1 < 2 or y2 - y1 < 2:      # degenerate
            continue
        conf = it.get("confidence", it.get("score", 0.7))
        try:
            conf = float(conf)
            if conf > 1.0:      # model used 0-100
                conf /= 100.0
        except (TypeError, ValueError):
            conf = 0.7
        boxes.append({
            "label": str(it.get("label", it.get("name", "object")))[:60],
            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "confidence": round(max(0.0, min(conf, 1.0)), 3),
        })
    return boxes[:12]        # sanity cap


def _parsed_cleanly(raw: str) -> bool:
    """
    True when the model emitted a parseable JSON array — possibly empty.
    Distinguishes an honest "object absent" result (parsed, 0 boxes) from a
    parse failure (prose / malformed output): the two must not receive the
    same dinged confidence.
    """
    candidates: List[str] = [raw.strip()]
    fence = _FENCE_RE.search(raw)
    if fence:
        candidates.insert(0, fence.group(1))
    arr = _ARRAY_RE.search(raw)
    if arr:
        candidates.insert(0, arr.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("boxes") or data.get("regions") or []
        if isinstance(data, list):
            return True
    return False


class GroundTool(BaseTool):
    tool_id = "ground"
    description = ("Text-guided region grounding: highlights referred regions "
                   "(water body, built-up area...) with bounding boxes — PS "
                   "single-image task option B.")
    required_images = 1
    allowed_params = ["output_format"]
    ps_requirement = "Single-image task: text-guided region grounding"

    async def execute(self, query: str, images: list[str],
                      metadata: dict | None = None,
                      output_format: str = "hbb",
                      model: str | None = None, **params) -> Dict[str, Any]:
        obb = output_format == "obb"
        user = (
            f"Referring expression: \"{query}\"\n"
            "Localise every region in the attached image that matches the "
            "expression. " + ("Use oriented boxes described as the axis-aligned "
            "bounds of the rotated extent." if obb else "Use axis-aligned boxes.") +
            " Reply with the JSON array only."
        )
        text, model_conf, meta = await self.ask(SYSTEM, user, images[:1],
                                                max_tokens=512, temperature=0.0,
                                                model=model)
        boxes = parse_boxes(text)
        parsed_cleanly = _parsed_cleanly(text)
        self_reported = bool(meta.get("self_reported_confidence"))
        conf = (sum(b["confidence"] for b in boxes) / len(boxes)) if boxes else 0.0
        if not boxes:
            # honest-empty (model answered with a valid empty array) is more
            # trustworthy than output we could not parse at all — the old code
            # collapsed both into the same 0.35 (the 0.5 arm was dead)
            conf = 0.5 if parsed_cleanly else 0.35
        # grounding trust = box confidences, dinged when the model never used
        # the confidence protocol (the old code multiplied by 0.6 on every
        # answer because the prompt banned the CONFIDENCE line entirely)
        confidence = round(min(1.0, conf * (0.95 if self_reported else 0.8)), 3)
        return {
            "text": (f"Located {len(boxes)} region(s) matching "
                     f"\"{query}\"." if boxes else
                     f"No region matching \"{query}\" could be located."),
            "bounding_boxes": boxes,
            "confidence": confidence,
            "confidence_source": "box_scores+parse",
            "model": meta["model"],
            "metadata": {"output_format": output_format,
                         "self_reported": self_reported,
                         "parsed_cleanly": parsed_cleanly,
                         "raw_model_output": text[:500] if not boxes else None},
        }
