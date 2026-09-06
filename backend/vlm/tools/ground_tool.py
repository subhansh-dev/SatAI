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


class GroundTool(BaseTool):
    tool_id = "ground"
    description = ("Text-guided region grounding: highlights referred regions "
                   "(water body, built-up area...) with bounding boxes — PS "
                   "single-image task option B.")
    required_images = 1
    allowed_params = ["output_format"]
    ps_requirement = "Single-image task: text-guided region grounding"

    async def execute(self, query: str, images: list[str],
                      output_format: str = "hbb", **params) -> Dict[str, Any]:
        obb = output_format == "obb"
        user = (
            f"Referring expression: \"{query}\"\n"
            "Localise every region in the attached image that matches the "
            "expression. " + ("Use oriented boxes described as the axis-aligned "
            "bounds of the rotated extent." if obb else "Use axis-aligned boxes.") +
            " Reply with the JSON array only."
        )
        text, model_conf, meta = await self.ask(SYSTEM, user, images[:1],
                                                max_tokens=512, temperature=0.0)
        boxes = parse_boxes(text)
        parse_ok = bool(boxes)
        self_reported = bool(meta.get("self_reported_confidence"))
        if not boxes and text:
            # model answered prose but found nothing concrete — keep honest
            boxes = []
        conf = (sum(b["confidence"] for b in boxes) / len(boxes)) if boxes else 0.0
        if not boxes:
            conf = 0.35 if parse_ok is False else 0.5
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
                         "raw_model_output": text[:500] if not boxes else None},
        }
