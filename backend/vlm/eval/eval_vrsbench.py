"""
SatAI — VRSBench Evaluation (captioning · grounding · VQA)

Metrics: BLEU-1..4 / METEOR / ROUGE-L / CIDEr (self-contained), Acc@0.5/0.7
grounding IoU against absolute-pixel GT boxes, normalised VQA accuracy.

Usage (from repo root):
    python -m backend.vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode caption
    python -m backend.vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode grounding
    python -m backend.vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode vqa

JSONL row format (see scripts/download_datasets.py --placeholder):
    {"id": "...", "images": ["img.jpg"], "caption": "...",
     "query": "...", "answer": "...",
     "boxes": [{"bbox": [x1,y1,x2,y2], "label": "..."}]}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from vlm.eval.common import (answers_match, box_iou, extract_pred_boxes,  # noqa: E402
                             gt_box_abs, to_image_inputs)
from vlm.eval.eval_metrics import caption_report  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("satai.eval.vrsbench")


class VRSEvaluator:
    def __init__(self, data_dir: str, controller, limit: int = 0):
        self.data_dir = Path(data_dir)
        self.controller = controller
        self.limit = limit

    def load_split(self, split: str = "test") -> list:
        from vlm.eval.common import read_jsonl
        rows = read_jsonl(self.data_dir / f"{split}.jsonl")
        if not rows:
            logger.warning("No samples in %s", self.data_dir / f"{split}.jsonl")
        if self.limit:
            rows = rows[:self.limit]
        return rows

    # ------------------------------------------------------------- caption
    async def eval_caption(self, samples: list) -> dict:
        preds, gts = [], []
        for i, sample in enumerate(samples):
            imgs = to_image_inputs(sample.get("images", []), self.data_dir)
            if not imgs:
                continue
            result = await self.controller.execute(
                query="Describe this satellite image in detail.",
                images=imgs, mode="single")
            preds.append(result.response)
            gt = sample.get("caption") or sample.get("answer") or ""
            gts.append([gt] if isinstance(gt, str) else list(gt))
            if (i + 1) % 25 == 0:
                logger.info("caption %d/%d", i + 1, len(samples))
        report = caption_report(preds, gts)
        report["predictions"] = [
            {"pred": p, "gt": g[0] if g else ""} for p, g in zip(preds, gts)]
        return report

    # ----------------------------------------------------------- grounding
    async def eval_grounding(self, samples: list) -> dict:
        ious, rows = [], []
        for i, sample in enumerate(samples):
            imgs = to_image_inputs(sample.get("images", []), self.data_dir)
            if not imgs:
                continue
            query = sample.get("query") or \
                "Locate the referred object with a bounding box."
            result = await self.controller.execute(
                query=query, images=imgs, mode="single",
                metadata={"force_task": "single_ground"})

            w = h = None
            if result.validation and result.validation.images:
                w, h = result.validation.images[0].width, \
                    result.validation.images[0].height
            pred_boxes = extract_pred_boxes(result)
            gt_boxes = [gt_box_abs(b.get("bbox", []), w, h)
                        for b in sample.get("boxes", [])
                        if b.get("bbox") and len(b["bbox"]) >= 4]

            best = max((box_iou(pb, gb) for pb in pred_boxes
                        for gb in gt_boxes), default=0.0) \
                if pred_boxes and gt_boxes else 0.0
            ious.append(best)
            rows.append({"id": sample.get("id", str(i)), "iou": round(best, 4),
                         "n_pred": len(pred_boxes), "n_gt": len(gt_boxes)})
            if (i + 1) % 25 == 0:
                logger.info("grounding %d/%d", i + 1, len(samples))

        n = max(len(ious), 1)
        return {
            "Acc@0.5": round(sum(v >= 0.5 for v in ious) / n, 4),
            "Acc@0.7": round(sum(v >= 0.7 for v in ious) / n, 4),
            "mean_IoU": round(sum(ious) / n, 4),
            "num_samples": len(ious),
            "detail": rows,
        }

    # ----------------------------------------------------------------- vqa
    async def eval_vqa(self, samples: list) -> dict:
        by_type: dict = {}
        correct = total = 0
        for i, sample in enumerate(samples):
            imgs = to_image_inputs(sample.get("images", []), self.data_dir)
            if not imgs:
                continue
            query = sample.get("query") or sample.get("question") or ""
            gt = sample.get("answer", "")
            result = await self.controller.execute(
                query=query, images=imgs, mode="single")
            ok = answers_match(result.response, gt)
            correct += ok
            total += 1
            qtype = sample.get("question_type", "unknown")
            agg = by_type.setdefault(qtype, {"correct": 0, "total": 0})
            agg["total"] += 1
            agg["correct"] += int(ok)
            if (i + 1) % 25 == 0:
                logger.info("vqa %d/%d (acc %.3f)", i + 1, len(samples),
                            correct / max(total, 1))
        return {
            "accuracy": round(correct / max(total, 1), 4),
            "correct": correct,
            "total": total,
            "by_type": {t: round(v["correct"] / max(v["total"], 1), 4)
                        for t, v in by_type.items()},
        }


async def run(args) -> dict:
    logger.info("VRSBench eval — mode=%s split=%s", args.mode, args.split)
    from vlm.eval.common import build_controller
    ctrl = build_controller()
    ev = VRSEvaluator(args.data_dir, ctrl, args.limit)
    samples = ev.load_split(args.split)
    if not samples:
        logger.error("No samples found in %s/%s.jsonl", args.data_dir, args.split)
        return {}
    logger.info("Loaded %d samples", len(samples))
    try:
        if args.mode == "caption":
            return await ev.eval_caption(samples)
        if args.mode == "grounding":
            return await ev.eval_grounding(samples)
        return await ev.eval_vqa(samples)
    finally:
        await ctrl.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", default="data/vrsbench")
    p.add_argument("--mode", choices=["caption", "grounding", "vqa"],
                   required=True)
    p.add_argument("--split", default="test")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    results = asyncio.run(run(args))
    if not results:
        return
    out_path = Path(args.data_dir) / f"eval_{args.mode}_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    summary = {k: v for k, v in results.items()
               if not isinstance(v, list)}
    logger.info("Results -> %s", out_path)
    logger.info(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
