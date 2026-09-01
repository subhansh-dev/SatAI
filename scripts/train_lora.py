"""
SatAI — LoRA Fine-Tuning Script
Fine-tunes Qwen2.5-VL-7B on remote sensing datasets using QLoRA.

Usage:
    python scripts/train_lora.py --dataset bigearthnet --epochs 3 --batch_size 4
    python scripts/train_lora.py --dataset rsvqa --epochs 5 --batch_size 2

Prerequisites:
    pip install transformers peft bitsandbytes accelerate datasets torch
"""
import argparse
import json
import logging
import os
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("satai.train")

# Default paths
BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
LORA_OUTPUT = Path(__file__).parent.parent / "backend" / "vlm" / "lora" / "checkpoints"
DATA_DIR = Path(__file__).parent.parent / "data"


def parse_args():
    p = argparse.ArgumentParser(description="Fine-tune Qwen2.5-VL with LoRA on RS data")
    p.add_argument("--dataset", type=str, default="bigearthnet",
                    choices=["bigearthnet", "rsvqa", "cdvqa", "changechat", "all"],
                    help="Dataset to train on")
    p.add_argument("--base_model", type=str, default=BASE_MODEL)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch_size", type=int, default=2)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--lora_r", type=int, default=16, help="LoRA rank")
    p.add_argument("--lora_alpha", type=int, default=32, help="LoRA alpha")
    p.add_argument("--max_length", type=int, default=2048)
    p.add_argument("--output_dir", type=str, default=str(LORA_OUTPUT))
    p.add_argument("--quantize", action="store_true", help="Use 4-bit QLoRA")
    p.add_argument("--dry_run", action="store_true", help="Print config and exit")
    return p.parse_args()


def load_dataset(name: str) -> list[dict]:
    """
    Load and format a dataset for VLM fine-tuning.
    Each sample should have: images, query, answer format.
    """
    dataset_dir = DATA_DIR / name
    if not dataset_dir.exists():
        logger.warning(f"Dataset dir not found: {dataset_dir}")
        logger.info(f"Creating placeholder for {name} — download real data first")
        return _create_placeholder(name)

    samples = []
    # Look for JSONL or JSON files
    for ext in ["*.jsonl", "*.json"]:
        for f in dataset_dir.glob(ext):
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        samples.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
    return samples


def _create_placeholder(name: str) -> list[dict]:
    """Create minimal placeholder data so training code can be tested."""
    if name == "bigearthnet":
        return [
            {
                "images": ["placeholder_sentinel2.jpg"],
                "messages": [
                    {"role": "user", "content": "Describe the land cover in this satellite image."},
                    {"role": "assistant", "content": "The image shows mixed land cover including urban areas with dense building clusters, agricultural fields with varying crop stages, forested areas in dark green, and a river running through the eastern portion."}
                ]
            }
        ] * 10
    elif name == "rsvqa":
        return [
            {
                "images": ["placeholder_sentinel2.jpg"],
                "messages": [
                    {"role": "user", "content": "What is the dominant land cover type?"},
                    {"role": "assistant", "content": "Urban"}
                ]
            }
        ] * 10
    elif name == "cdvqa":
        return [
            {
                "images": ["before.jpg", "after.jpg"],
                "messages": [
                    {"role": "user", "content": "What changed between these two dates?"},
                    {"role": "assistant", "content": "New buildings were constructed in the eastern area, and a previously forested patch has been cleared for agricultural use."}
                ]
            }
        ] * 10
    return []


def setup_lora(model_name: str, r: int, alpha: int, quantize: bool):
    """Configure LoRA adapter for Qwen2.5-VL."""
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    except ImportError as e:
        logger.error(f"Missing dependencies: {e}")
        logger.info("Install: pip install transformers peft bitsandbytes accelerate")
        return None, None

    logger.info(f"Loading base model: {model_name}")

    load_kwargs = {"trust_remote_code": True}
    if quantize:
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype="float16",
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

    try:
        model = AutoModelForCausalLM.from_pretrained(model_name, **load_kwargs)
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return None, None

    if quantize:
        model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=r,
        lora_alpha=alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model, tokenizer


def train(model, tokenizer, samples: list[dict], args):
    """Simple training loop. For production, use transformers Trainer."""
    import torch
    from torch.utils.data import Dataset, DataLoader

    class VLMDataset(Dataset):
        def __init__(self, samples, tokenizer, max_length):
            self.samples = samples
            self.tokenizer = tokenizer
            self.max_length = max_length

        def __len__(self):
            return len(self.samples)

        def __getitem__(self, idx):
            sample = self.samples[idx]
            text = ""
            for msg in sample["messages"]:
                text += f"<|{msg['role']}|>\n{msg['content']}\n"
            text += "<|end|>"

            encoded = self.tokenizer(
                text,
                max_length=self.max_length,
                truncation=True,
                padding="max_length",
                return_tensors="pt",
            )
            return {k: v.squeeze(0) for k, v in encoded.items()}

    dataset = VLMDataset(samples, tokenizer, args.max_length)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    model.train()

    total_steps = len(dataloader) * args.epochs
    step = 0
    for epoch in range(args.epochs):
        epoch_loss = 0
        for batch in dataloader:
            batch = {k: v.to(model.device) for k, v in batch.items()}
            outputs = model(**batch, labels=batch["input_ids"])
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            epoch_loss += loss.item()
            step += 1
            if step % 10 == 0:
                logger.info(f"Step {step}/{total_steps} | Loss: {loss.item():.4f}")

        avg_loss = epoch_loss / len(dataloader)
        logger.info(f"Epoch {epoch+1}/{args.epochs} | Avg Loss: {avg_loss:.4f}")

    return avg_loss


def save_lora(model, tokenizer, output_dir: str):
    """Save LoRA adapter weights."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out))
    tokenizer.save_pretrained(str(out))
    logger.info(f"LoRA adapter saved to: {out}")

    # Save metadata
    meta = {
        "base_model": BASE_MODEL,
        "timestamp": datetime.utcnow().isoformat(),
        "adapter_path": str(out),
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"Metadata saved to: {out / 'metadata.json'}")


def main():
    args = parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN — Configuration ===")
        logger.info(f"Base model: {args.base_model}")
        logger.info(f"Dataset: {args.dataset}")
        logger.info(f"LoRA rank: {args.lora_r}, alpha: {args.lora_alpha}")
        logger.info(f"Quantize: {args.quantize}")
        logger.info(f"Output: {args.output_dir}")
        return

    logger.info("Loading dataset...")
    if args.dataset == "all":
        samples = []
        for ds in ["bigearthnet", "rsvqa", "cdvqa", "changechat"]:
            samples.extend(load_dataset(ds))
    else:
        samples = load_dataset(args.dataset)

    if not samples:
        logger.error("No training samples found. Download datasets first.")
        return

    logger.info(f"Loaded {len(samples)} samples")

    model, tokenizer = setup_lora(args.base_model, args.lora_r, args.lora_alpha, args.quantize)
    if model is None:
        logger.error("Failed to setup LoRA. Check dependencies.")
        return

    logger.info("Starting training...")
    final_loss = train(model, tokenizer, samples, args)
    logger.info(f"Training complete. Final loss: {final_loss:.4f}")

    save_lora(model, tokenizer, args.output_dir)
    logger.info("Done!")


if __name__ == "__main__":
    main()
