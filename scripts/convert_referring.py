"""
SatAI — Convert RSBench referring data into SatAI grounding JSONL.

The grounding evaluator (backend/vlm/eval/eval_vrsbench.py) needs, per row:

    {"id": ..., "images": ["img.png"], "query": "<referring expression>",
     "boxes": [{"bbox": [x1, y1, x2, y2], "label": "..."}]}   # 0-1 normalised

RSBench referring splits instead carry:
    ground_truth : "{<25><40><33><60>}"   — box on a 0-100 grid (x1,y1,x2,y2)
    obj_corner   : [x,y, x,y, x,y, x,y]   — object polygon corners, 0-1
    obj_cls      : class label, question: the referring expression

Without conversion the eval slice has no GT boxes (n_gt = 0) and every IoU is
forced to 0.0 — a data artifact, not a model score. This script fixes that.

Box-source policy: prefer the official `ground_truth` string (scaled /100);
if it is absent/unparseable, use the axis-aligned bounding box of `obj_corner`.
If both exist and disagree by more than --tolerance (default 0.05, i.e. the
quantisation error of the 0-100 grid plus slack), the precise polygon AABB is
used instead and the row is counted as a warning.

Usage (from repo root):
    python scripts/convert_referring.py --src data/vrsgnd/referring.jsonl \
        --out-dir data/vrsgnd --split test
    # then, with images resolvable under data/vrsgnd (or data/vrsgnd/images/):
    python -m backend.vlm.eval.eval_vrsbench --data_dir data/vrsgnd \
        --mode grounding --limit 100
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

_NUM = re.compile(r"<\s*([\d.]+)\s*>")
_GROUP = re.compile(r"\{[^{}]*\}")


def parse_gt_boxes(gt: str) -> List[Tuple[float, float, float, float]]:
    """'{<25><40><33><60>}' (0-100 grid) -> [(0.25, 0.40, 0.33, 0.60), ...].

    Supports multiple {...} groups; each group must hold >= 4 numbers
    (extra numbers, e.g. class id suffixes, are ignored)."""
    boxes: List[Tuple[float, float, float, float]] = []
    for group in _GROUP.findall(str(gt)):
        nums = [float(v) for v in _NUM.findall(group)]
        if len(nums) < 4:
            continue
        x1, y1, x2, y2 = nums[0], nums[1], nums[2], nums[3]
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        boxes.append((x1 / 100.0, y1 / 100.0, x2 / 100.0, y2 / 100.0))
    return boxes


def corners_aabb(obj_corner) -> Optional[Tuple[float, float, float, float]]:
    """Axis-aligned bounding box of 0-1 corner pairs [x,y, x,y, ...]."""
    try:
        vals = [float(v) for v in (obj_corner or [])]
    except (TypeError, ValueError):
        return None
    if len(vals) < 4 or len(vals) % 2:
        return None
    xs, ys = vals[0::2], vals[1::2]
    if any(not (0.0 <= v <= 1.001) for v in vals):
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _max_diff(a, b) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def convert_row(row: dict, tolerance: float = 0.05) -> Tuple[Optional[dict], str]:
    """RSBench referring row -> SatAI grounding row (or None, with status)."""
    query = str(row.get("question") or "").strip()
    image = str(row.get("image_id") or "").strip()
    if not query or not image:
        return None, "skipped (missing question/image_id)"

    gt_str = parse_gt_boxes(row.get("ground_truth", ""))
    aabb = corners_aabb(row.get("obj_corner"))

    if gt_str:
        box = gt_str[0]
        if aabb and _max_diff(box, aabb) > tolerance:
            box, status = aabb, "ok (gt/corner mismatch — used corner AABB)"
        else:
            status = "ok"
    elif aabb:
        box, status = aabb, "ok (no gt string — used corner AABB)"
    else:
        return None, "skipped (no usable ground-truth box)"

    out = {
        "id": str(row.get("question_id", image)),
        "images": [image],
        "query": f"{query} Return the bounding box of the described object.",
        "boxes": [{"bbox": [round(v, 6) for v in box],
                   "label": str(row.get("obj_cls") or "object")}],
    }
    return out, status


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--src", required=True,
                   help="RSBench referring file (.jsonl or a .json list)")
    p.add_argument("--out-dir", default="data/vrsgnd",
                   help="directory for the converted <split>.jsonl")
    p.add_argument("--split", default="test",
                   help="output split name (default: test)")
    p.add_argument("--limit", type=int, default=0,
                   help="convert only the first N rows (0 = all)")
    p.add_argument("--tolerance", type=float, default=0.05,
                   help="max gt-string vs corner-AABB coord diff before the "
                        "polygon box wins (default 0.05)")
    args = p.parse_args()

    src = Path(args.src)
    rows: List[dict] = []
    if src.suffix == ".jsonl":
        with open(src, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    else:
        data = json.loads(src.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("data", [])
    if args.limit:
        rows = rows[: args.limit]

    out_rows, skipped, warned = [], 0, 0
    for row in rows:
        out, status = convert_row(row, args.tolerance)
        if out is None:
            skipped += 1
            if "mismatch" in status:
                warned += 1
            continue
        if "mismatch" in status:
            warned += 1
        out_rows.append(out)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.split}.jsonl"
    with open(out_path, "w", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"converted {len(out_rows)}/{len(rows)} rows -> {out_path} "
          f"(skipped {skipped}, gt/corner mismatches {warned})")
    if out_rows:
        print("images must resolve under", out_dir,
              "(or", out_dir / "images", ") — e.g. copy/symlink the "
              "RSBench image folder there before running the grounding eval.")


if __name__ == "__main__":
    main()
