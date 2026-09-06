"""
SatAI — Evaluation harness shared helpers.

Bootstraps `backend/` onto sys.path so every eval script runs both ways:
    python -m backend.vlm.eval.eval_vrsbench     (from repo root)
    python backend/vlm/eval/eval_vrsbench.py     (anywhere)

and converts JSONL dataset rows (file paths) into controller-ready
ImageInput objects (base64) — the old harness passed raw path strings and
crashed in validation before a single VLM call.
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from vlm.schemas import ImageInput  # noqa: E402


# ---------------------------------------------------------------------------
# Controller construction
# ---------------------------------------------------------------------------
def build_controller():
    """Synchronous controller for eval scripts (single instance, reused)."""
    import asyncio
    from vlm.controller import Controller
    ctrl = Controller()
    return ctrl


# ---------------------------------------------------------------------------
# Sample IO
# ---------------------------------------------------------------------------
def read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.is_file():
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def resolve_image(base_dir: Path, ref: str) -> Optional[Path]:
    p = Path(ref)
    if not p.is_absolute():
        p = base_dir / p
    if p.is_file():
        return p
    # common fallbacks
    for cand in (base_dir / "images" / ref, base_dir.parent / "images" / ref):
        if cand.is_file():
            return cand
    return None


def to_image_inputs(imgs: List[str], base_dir: Path) -> List[ImageInput]:
    """JSONL image refs (paths) -> base64 ImageInput list (skips missing)."""
    out: List[ImageInput] = []
    for ref in imgs:
        p = resolve_image(base_dir, str(ref))
        if p is None:
            continue
        data = base64.b64encode(p.read_bytes()).decode()
        out.append(ImageInput(data=data, name=p.name))
    return out


# ---------------------------------------------------------------------------
# Answer normalisation (standard VQA protocol)
# ---------------------------------------------------------------------------
_ARTIFACTS = re.compile(r"\b(a|an|the)\b")
_PUNCT = re.compile(
    r"[%s]" % re.escape(".,;:!?'\"()[]{}<>-_/#$%&*+~`|^\\="))
_SPACES = re.compile(r"\s+")


def normalize_answer(ans: str) -> str:
    """Lowercase, strip punctuation/articles, collapse whitespace."""
    a = str(ans).lower().strip()
    a = _PUNCT.sub(" ", a)
    a = _ARTIFACTS.sub(" ", a)
    return _SPACES.sub(" ", a).strip()


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def answers_match(pred: str, gt: str) -> bool:
    """
    VLM answers are free-form sentences; GT is a short answer. Match rules:
      1. exact after normalisation,
      2. numeric equality ("2" == "2.0"),
      3. GT appears as a whole phrase inside the prediction (len <= 3 words),
      4. GT is a number and appears among the numbers in the prediction.
    """
    p, g = normalize_answer(pred), normalize_answer(gt)
    if p == g:
        return True
    for a, b in ((pred, gt), (p.replace(" ", ""), g.replace(" ", ""))):
        try:
            if abs(float(str(a).strip()) - float(str(b).strip())) < 1e-6:
                return True
        except (ValueError, TypeError):
            continue
    if g and len(g.split()) <= 3 and re.search(rf"\b{re.escape(g)}\b", p):
        return True
    try:
        g_num = float(str(gt).strip())
        for m in _NUM_RE.findall(pred):
            if abs(float(m) - g_num) < 1e-6:
                return True
    except (ValueError, TypeError):
        pass
    return False


# ---------------------------------------------------------------------------
# Box geometry
# ---------------------------------------------------------------------------
def box_iou(b1: List[float], b2: List[float]) -> float:
    try:
        x1, y1, x2, y2 = (float(v) for v in b1[:4])
        X1, Y1, X2, Y2 = (float(v) for v in b2[:4])
    except (TypeError, ValueError, IndexError):
        return 0.0
    ix1, iy1 = max(x1, X1), max(y1, Y1)
    ix2, iy2 = min(x2, X2), min(y2, Y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    a1 = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))
    a2 = max(0.0, (X2 - X1)) * max(0.0, (Y2 - Y1))
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def extract_pred_boxes(result) -> List[List[float]]:
    """
    Pull predicted boxes in ABSOLUTE PIXELS from a controller VLMResponse.
    Prefers trace.tool_outputs[].bounding_boxes (0-1000 normalised, scaled by
    validation image size); falls back to geojson pixel_bbox.
    """
    boxes: List[List[float]] = []
    w = h = None
    if result.validation and result.validation.images:
        w = result.validation.images[0].width or None
        h = result.validation.images[0].height or None

    trace = result.trace
    if trace:
        for out in trace.tool_outputs:
            for b in (out.bounding_boxes or []):
                bbox = b.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                try:
                    vals = [float(v) for v in bbox[:4]]
                except (TypeError, ValueError):
                    continue
                # registry tools emit 0-1000 normalised coords
                if all(v <= 1005 for v in vals) and w and h:
                    vals = [vals[0] / 1000 * w, vals[1] / 1000 * h,
                            vals[2] / 1000 * w, vals[3] / 1000 * h]
                boxes.append(vals)

    if not boxes and result.geojson:
        for feat in result.geojson.get("features", []):
            pb = feat.get("properties", {}).get("pixel_bbox")
            if pb and len(pb) >= 4:
                boxes.append([float(v) for v in pb[:4]])
    return boxes


def gt_box_abs(gt: List[float], w: Optional[int], h: Optional[int]
               ) -> List[float]:
    """GT boxes may be absolute px or 0-1 normalised — make absolute."""
    vals = [float(v) for v in gt[:4]]
    if all(0.0 <= v <= 1.001 for v in vals) and w and h:
        return [vals[0] * w, vals[1] * h, vals[2] * w, vals[3] * h]
    return vals
