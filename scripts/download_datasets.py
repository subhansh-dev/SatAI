"""
SatAI — Dataset Downloader
Downloads evaluation benchmarks: VRSBench, RSVQA, CDVQA.

Usage:
    python scripts/download_datasets.py --all
    python scripts/download_datasets.py --vrsbench
    python scripts/download_datasets.py --rsvqa
    python scripts/download_datasets.py --cdvqa
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("satai.download")

DATA_DIR = Path(__file__).parent.parent / "data"


def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)


def download_bigearthnet():
    """Download BigEarthNet dataset for LoRA fine-tuning."""
    logger.info("BigEarthNet — RS adaptation dataset")
    logger.info("=" * 60)
    logger.info("BigEarthNet is ~18GB and requires manual download.")
    logger.info("")
    logger.info("Steps:")
    logger.info("1. Go to: https://bigearth.net/")
    logger.info("2. Register and download Sentinel-2 tiles")
    logger.info("3. Extract to: data/bigearthnet/")
    logger.info("")
    logger.info("Alternative: Use HuggingFace Hub")
    logger.info("  pip install datasets")
    logger.info('  python -c "from datasets import load_dataset; ds = load_dataset(\"bigearthnet\", split=\"train[:1000]\"); ds.save_to_disk(\"data/bigearthnet\")"')
    logger.info("")

    out_dir = DATA_DIR / "bigearthnet"
    ensure_dir(out_dir)

    # Check if HuggingFace datasets is available
    try:
        import datasets
        logger.info("HuggingFace datasets found — attempting download...")
        ds = datasets.load_dataset("bigearthnet", split="train[:100]", trust_remote_code=True)
        ds.save_to_disk(str(out_dir / "hf"))
        logger.info(f"Saved to: {out_dir / 'hf'}")
        return True
    except ImportError:
        logger.info("HuggingFace datasets not installed. Install with: pip install datasets")
    except Exception as e:
        logger.warning(f"HuggingFace download failed: {e}")
        logger.info("Falling back to manual download instructions.")

    return False


def download_rsvqa():
    """Download RSVQA dataset."""
    logger.info("RSVQA — Remote Sensing Visual Question Answering")
    logger.info("=" * 60)

    out_dir = DATA_DIR / "rsvqa"
    ensure_dir(out_dir)

    # Try HuggingFace
    try:
        import datasets
        logger.info("Attempting HuggingFace download...")
        ds = datasets.load_dataset("arampacha/rsvqa", split="test[:200]", trust_remote_code=True)
        ds.save_to_disk(str(out_dir / "hf"))
        logger.info(f"Saved RSVQA to: {out_dir / 'hf'}")

        # Convert to JSONL format
        jsonl_path = out_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            for item in ds:
                sample = {
                    "id": item.get("id", ""),
                    "images": item.get("images", []),
                    "question": item.get("question", ""),
                    "answer": item.get("answer", ""),
                    "question_type": item.get("question_type", "unknown"),
                }
                f.write(json.dumps(sample) + "\n")
        logger.info(f"Converted to JSONL: {jsonl_path}")
        return True
    except ImportError:
        logger.info("pip install datasets")
    except Exception as e:
        logger.warning(f"HuggingFace download failed: {e}")

    logger.info("")
    logger.info("Manual download:")
    logger.info("  1. Go to: https://github.com/isaaccorley/RSVQA")
    logger.info("  2. Download dataset splits")
    logger.info("  3. Place as data/rsvqa/test.jsonl")
    return False


def download_cdvqa():
    """Download CDVQA dataset."""
    logger.info("CDVQA — Change Detection VQA")
    logger.info("=" * 60)

    out_dir = DATA_DIR / "cdvqa"
    ensure_dir(out_dir)

    logger.info("CDVQA is not yet on HuggingFace. Manual download required.")
    logger.info("")
    logger.info("Steps:")
    logger.info("1. Go to: https://github.com/SebastianJanisch/CDVQA")
    logger.info("2. Download the dataset")
    logger.info("3. Convert to JSONL format and place in data/cdvqa/")
    logger.info("")
    logger.info("Expected JSONL format per line:")
    logger.info('  {"id": "...", "images": ["before.jpg", "after.jpg"], "question": "...", "answer": "...", "question_type": "change"}')
    return False


def download_changechat():
    """Download ChangeChat dataset for change captioning training."""
    logger.info("ChangeChat — Change Captioning Training Data")
    logger.info("=" * 60)

    out_dir = DATA_DIR / "changechat"
    ensure_dir(out_dir)

    logger.info("ChangeChat contains 105k change captioning samples.")
    logger.info("")
    logger.info("Steps:")
    logger.info("1. Go to: https://github.com/linfanghe/ChangeChat")
    logger.info("2. Download the dataset")
    logger.info("3. Place as data/changechat/")
    return False


def create_placeholder_data():
    """Create minimal placeholder data for testing the pipeline."""
    logger.info("Creating placeholder test data...")
    ensure_dir(DATA_DIR / "vrsbench")
    ensure_dir(DATA_DIR / "rsvqa")
    ensure_dir(DATA_DIR / "cdvqa")

    # VRSBench placeholder
    vrsbench = DATA_DIR / "vrsbench" / "test.jsonl"
    with open(vrsbench, "w") as f:
        for i in range(10):
            sample = {
                "id": f"vrs_{i}",
                "images": [f"placeholder_{i}.jpg"],
                "caption": f"Satellite image showing mixed land cover with urban and agricultural areas.",
                "query": "Describe the land cover in this image.",
                "answer": "Mixed land cover",
                "boxes": [{"bbox": [100, 100, 500, 500], "label": "urban area"}],
            }
            f.write(json.dumps(sample) + "\n")
    logger.info(f"Created: {vrsbench} (10 samples)")

    # RSVQA placeholder
    rsvqa = DATA_DIR / "rsvqa" / "test.jsonl"
    with open(rsvqa, "w") as f:
        for i in range(10):
            sample = {
                "id": f"rsvqa_{i}",
                "images": [f"placeholder_{i}.jpg"],
                "question": "What is the dominant land cover type?",
                "answer": "Urban" if i % 2 == 0 else "Agricultural",
                "question_type": "category",
            }
            f.write(json.dumps(sample) + "\n")
    logger.info(f"Created: {rsvqa} (10 samples)")

    # CDVQA placeholder
    cdvqa = DATA_DIR / "cdvqa" / "test.jsonl"
    with open(cdvqa, "w") as f:
        for i in range(10):
            sample = {
                "id": f"cdvqa_{i}",
                "images": [f"before_{i}.jpg", f"after_{i}.jpg"],
                "question": "What changed between these two dates?",
                "answer": "New construction visible in the eastern area",
                "question_type": "change",
            }
            f.write(json.dumps(sample) + "\n")
    logger.info(f"Created: {cdvqa} (10 samples)")


def main():
    p = argparse.ArgumentParser(description="Download SatAI datasets")
    p.add_argument("--all", action="store_true", help="Download all datasets")
    p.add_argument("--bigearthnet", action="store_true", help="Download BigEarthNet")
    p.add_argument("--rsvqa", action="store_true", help="Download RSVQA")
    p.add_argument("--cdvqa", action="store_true", help="Download CDVQA")
    p.add_argument("--changechat", action="store_true", help="Download ChangeChat")
    p.add_argument("--placeholder", action="store_true", help="Create placeholder test data")
    args = p.parse_args()

    if not any([args.all, args.bigearthnet, args.rsvqa, args.cdvqa, args.changechat, args.placeholder]):
        args.placeholder = True
        logger.info("No dataset specified — creating placeholder data for testing")

    if args.placeholder:
        create_placeholder_data()
        return

    if args.all or args.bigearthnet:
        download_bigearthnet()
    if args.all or args.rsvqa:
        download_rsvqa()
    if args.all or args.cdvqa:
        download_cdvqa()
    if args.all or args.changechat:
        download_changechat()


if __name__ == "__main__":
    main()
