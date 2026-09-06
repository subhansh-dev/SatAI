"""
SatAI — CDVQA Evaluation (bi-temporal change VQA, PS-mandated task)

Same normalised-match protocol as RSVQA; runs every sample through the
agentic controller in bitemporal mode (change tool + spatial change map).

Usage (from repo root):
    python -m backend.vlm.eval.eval_cdvqa --data_dir data/cdvqa --limit 200
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

from vlm.eval.common import answers_match, to_image_inputs  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("satai.eval.cdvqa")


class CDVQAEvaluator:
    def __init__(self, data_dir: str, controller, limit: int = 0):
        self.data_dir = Path(data_dir)
        self.controller = controller
        self.limit = limit

    def load_samples(self, split: str = "test") -> list:
        from vlm.eval.common import read_jsonl
        rows = []
        for name in (f"{split}.jsonl", "test.jsonl", "train.jsonl"):
            rows = read_jsonl(self.data_dir / name)
            if rows:
                break
        if self.limit:
            rows = rows[:self.limit]
        return rows

    async def evaluate(self, samples: list) -> dict:
        correct = total = 0
        by_type: dict = {}
        misses = []
        for i, sample in enumerate(samples):
            imgs = to_image_inputs(sample.get("images", []), self.data_dir)
            if not imgs:
                continue
            query = sample.get("question", "What changed between these two dates?")
            gt = sample.get("answer", "")
            result = await self.controller.execute(
                query=query, images=imgs, mode="bitemporal")
            ok = answers_match(result.response, gt)
            correct += ok
            total += 1
            qtype = sample.get("question_type", "change")
            agg = by_type.setdefault(qtype, {"correct": 0, "total": 0})
            agg["total"] += 1
            agg["correct"] += int(ok)
            if not ok and len(misses) < 25:
                misses.append({"id": sample.get("id", str(i)),
                               "q": query, "gt": gt,
                               "pred": result.response[:200]})
            if (i + 1) % 25 == 0:
                logger.info("CDVQA progress %d/%d | acc %.3f",
                            i + 1, len(samples), correct / max(total, 1))
        return {
            "accuracy": round(correct / max(total, 1), 4),
            "correct": correct,
            "total": total,
            "by_type": {t: round(v["correct"] / max(v["total"], 1), 4)
                        for t, v in by_type.items()},
            "sample_misses": misses,
        }


async def run(args) -> dict:
    from vlm.eval.common import build_controller
    logger.info("CDVQA eval — split=%s", args.split)
    ctrl = build_controller()
    ev = CDVQAEvaluator(args.data_dir, ctrl, args.limit)
    samples = ev.load_samples(args.split)
    if not samples:
        logger.error("No samples. Download first: "
                     "python scripts/download_datasets.py --cdvqa")
        return {}
    logger.info("Loaded %d samples", len(samples))
    try:
        return await ev.evaluate(samples)
    finally:
        await ctrl.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", default="data/cdvqa")
    p.add_argument("--split", default="test")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    results = asyncio.run(run(args))
    if not results:
        return
    out_path = Path(args.data_dir) / f"eval_results_{args.split}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    summary = {k: v for k, v in results.items() if not isinstance(v, list)}
    logger.info("Results -> %s", out_path)
    logger.info(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
