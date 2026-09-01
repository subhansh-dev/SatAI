"""
SatAI — CDVQA Evaluation
Change Detection VQA — evaluates bi-temporal change understanding.

Usage:
    python -m vlm.eval.eval_cdvqa --data_dir data/cdvqa
"""
import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("satai.eval.cdvqa")


class CDVQAEvaluator:
    def __init__(self, data_dir: str, controller):
        self.data_dir = Path(data_dir)
        self.controller = controller

    def load_samples(self, split: str = "test") -> list[dict]:
        fpath = self.data_dir / f"{split}.jsonl"
        if not fpath.exists():
            logger.warning(f"CDVQA split not found: {fpath}")
            return []
        samples = []
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
        return samples

    async def evaluate(self, samples: list[dict]) -> dict:
        correct = 0
        total = 0
        by_type = {}

        for i, sample in enumerate(samples):
            query = sample.get("question", "What changed between these two dates?")
            gt = sample.get("answer", "")
            images = sample.get("images", [])

            result = await self.controller.execute(
                query=query,
                images=images,
                mode="bitemporal",
            )

            pred = result.response.strip().lower()
            is_correct = pred == gt.strip().lower()
            if is_correct:
                correct += 1
            total += 1

            qtype = sample.get("question_type", "change")
            if qtype not in by_type:
                by_type[qtype] = {"correct": 0, "total": 0}
            by_type[qtype]["total"] += 1
            if is_correct:
                by_type[qtype]["correct"] += 1

            if (i + 1) % 25 == 0:
                logger.info(f"CDVQA progress: {i+1}/{len(samples)} | Running acc: {correct/total:.3f}")

        accuracy = correct / max(total, 1)
        type_acc = {t: v["correct"] / max(v["total"], 1) for t, v in by_type.items()}

        return {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "by_type": type_acc,
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", type=str, default="data/cdvqa")
    p.add_argument("--split", type=str, default="test")
    args = p.parse_args()

    logger.info("CDVQA Evaluation")
    from vlm.controller import Controller
    ctrl = Controller()

    evaluator = CDVQAEvaluator(args.data_dir, ctrl)
    samples = evaluator.load_samples(args.split)
    if not samples:
        logger.error("No samples found. Download CDVQA dataset first.")
        return

    import asyncio
    results = asyncio.run(evaluator.evaluate(samples))

    out_path = Path(args.data_dir) / f"eval_results_{args.split}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results: {out_path}")
    logger.info(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
