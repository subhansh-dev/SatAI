"""
SatAI — VRSBench Evaluation
Evaluates on VRSBench: captioning, visual grounding, VQA.

Usage:
    python -m vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode caption
    python -m vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode grounding
    python -m vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode vqa
"""
import argparse
import json
import logging
import time
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("satai.eval")


class VRSEvaluator:
    def __init__(self, data_dir: str, controller):
        self.data_dir = Path(data_dir)
        self.controller = controller
        self.results = []

    def load_split(self, split: str = "test") -> list[dict]:
        """Load VRSBench split."""
        fpath = self.data_dir / f"{split}.jsonl"
        if not fpath.exists():
            logger.warning(f"Split not found: {fpath}")
            return []
        samples = []
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
        return samples

    async def eval_caption(self, samples: list[dict]) -> dict:
        """Evaluate captioning: BLEU-1/2/3/4, METEOR, ROUGE-L, CIDEr."""
        predictions = []
        for i, sample in enumerate(samples):
            result = await self.controller.execute(
                query="Describe this satellite image in detail.",
                images=sample.get("images", []),
                mode="single",
            )
            predictions.append({
                "id": sample.get("id", str(i)),
                "pred": result.response,
                "gt": sample.get("caption", ""),
            })
            if (i + 1) % 50 == 0:
                logger.info(f"Caption eval: {i+1}/{len(samples)}")

        return self._compute_caption_metrics(predictions)

    async def eval_grounding(self, samples: list[dict]) -> dict:
        """Evaluate visual grounding: Acc@0.5, Acc@0.7 (IoU thresholds)."""
        predictions = []
        for i, sample in enumerate(samples):
            query = sample.get("query", "What objects are in this image?")
            result = await self.controller.execute(
                query=query,
                images=sample.get("images", []),
                mode="single",
            )
            pred_boxes = result.visual_evidence.get("features", []) if result.visual_evidence else []
            gt_boxes = sample.get("boxes", [])
            iou = self._compute_iou(pred_boxes, gt_boxes)
            predictions.append({
                "id": sample.get("id", str(i)),
                "iou": iou,
            })

        acc_5 = sum(1 for p in predictions if p["iou"] >= 0.5) / max(len(predictions), 1)
        acc_7 = sum(1 for p in predictions if p["iou"] >= 0.7) / max(len(predictions), 1)
        return {"Acc@0.5": acc_5, "Acc@0.7": acc_7, "num_samples": len(predictions)}

    async def eval_vqa(self, samples: list[dict]) -> dict:
        """Evaluate VQA: accuracy per question type."""
        correct = 0
        total = 0
        by_type = {}
        for i, sample in enumerate(samples):
            query = sample.get("query", "")
            gt = sample.get("answer", "")
            result = await self.controller.execute(
                query=query,
                images=sample.get("images", []),
                mode="single",
            )
            pred = result.response.strip().lower()
            is_correct = pred == gt.strip().lower()
            if is_correct:
                correct += 1
            total += 1

            qtype = sample.get("question_type", "unknown")
            if qtype not in by_type:
                by_type[qtype] = {"correct": 0, "total": 0}
            by_type[qtype]["total"] += 1
            if is_correct:
                by_type[qtype]["correct"] += 1

            if (i + 1) % 50 == 0:
                logger.info(f"VQA eval: {i+1}/{len(samples)}")

        accuracy = correct / max(total, 1)
        type_acc = {t: v["correct"] / max(v["total"], 1) for t, v in by_type.items()}
        return {"accuracy": accuracy, "by_type": type_acc, "num_samples": total}

    def _compute_iou(self, pred_boxes: list, gt_boxes: list) -> float:
        """Compute IoU between predicted and ground truth boxes."""
        if not pred_boxes or not gt_boxes:
            return 0.0
        # Simple: use best matching box
        best_iou = 0.0
        for pb in pred_boxes:
            for gb in gt_boxes:
                iou = self._iou(pb, gb)
                best_iou = max(best_iou, iou)
        return best_iou

    def _iou(self, box1: list, box2: list) -> float:
        """IoU between two [x1,y1,x2,y2] boxes."""
        if len(box1) < 4 or len(box2) < 4:
            return 0.0
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        return inter / max(union, 1e-6)

    def _compute_caption_metrics(self, predictions: list[dict]) -> dict:
        """Compute caption metrics (placeholder — use pycocoevalcap for real metrics)."""
        logger.info("Computing caption metrics...")
        # In production, use: from pycocoevalcap.bleu.bleu import Bleu
        # For now, return basic stats
        avg_len = sum(len(p["pred"].split()) for p in predictions) / max(len(predictions), 1)
        return {
            "num_samples": len(predictions),
            "avg_pred_length": avg_len,
            "note": "Install pycocoevalcap for BLEU/METEOR/CIDEr metrics",
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", type=str, default="data/vrsbench")
    p.add_argument("--mode", type=str, choices=["caption", "grounding", "vqa"], required=True)
    p.add_argument("--split", type=str, default="test")
    args = p.parse_args()

    logger.info(f"VRSBench eval — mode: {args.mode}, split: {args.split}")
    logger.info("Import controller...")
    from vlm.controller import Controller
    ctrl = Controller()

    evaluator = VRSEvaluator(args.data_dir, ctrl)
    samples = evaluator.load_split(args.split)
    if not samples:
        logger.error(f"No samples found in {args.data_dir}/{args.split}.jsonl")
        return

    logger.info(f"Loaded {len(samples)} samples")

    import asyncio
    if args.mode == "caption":
        results = asyncio.run(evaluator.eval_caption(samples))
    elif args.mode == "grounding":
        results = asyncio.run(evaluator.eval_grounding(samples))
    elif args.mode == "vqa":
        results = asyncio.run(evaluator.eval_vqa(samples))

    out_path = Path(args.data_dir) / f"eval_{args.mode}_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to: {out_path}")
    logger.info(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
