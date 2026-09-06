"""
SatAI — Multimodal LoRA Fine-Tuning (PS requirement: "at least one VLM
component fine-tuned on remote-sensing data").

Fine-tunes Qwen2.5-VL on remote-sensing datasets (BigEarthNet primary,
RSVQA / CDVQA / ChangeChat optional) with QLoRA or full-precision LoRA.

This is a REAL multimodal pipeline:
  * images are loaded from disk and turned into vision tokens by the
    Qwen2.5-VL processor (chat template with <|image_pad|> placeholders),
  * the assistant reply is the only supervised target (prompt tokens are
    masked with -100),
  * the saved adapter is served by vLLM via --lora-modules (see
    vllm_config.yaml) so the whole stack runs on RS-adapted weights.

Usage:
    python scripts/train_lora.py --dataset bigearthnet --epochs 3 --dry_run
    python scripts/train_lora.py --dataset bigearthnet --epochs 3 --batch_size 2 --quantize
    python scripts/train_lora.py --dataset mix --epochs 2

Prerequisites:
    pip install "transformers>=4.49" peft bitsandbytes accelerate datasets \
                torch Pillow qwen-vl-utils
    python scripts/download_datasets.py --bigearthnet   # first
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("satai.train")

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
LORA_OUTPUT = REPO / "backend" / "vlm" / "lora" / "checkpoints"

BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

# BigEarthNet 19-class nomenclature (official 2019 release)
BEN_19_CLASSES = [
    "Urban fabric",
    "Industrial or commercial units",
    "Arable land",
    "Permanent crops",
    "Pastures",
    "Complex cultivation patterns",
    "Land principally occupied by agriculture, with significant areas of "
    "natural vegetation",
    "Agro-forestry areas",
    "Broad-leaved forest",
    "Coniferous forest",
    "Mixed forest",
    "Natural grassland and sparsely vegetated areas",
    "Moors, heathland and sclerophyllous vegetation",
    "Transitional woodland, shrub",
    "Beaches, dunes, sands",
    "Inland wetlands",
    "Coastal wetlands",
    "Inland waters",
    "Marine waters",
]

# OFFICIAL 43-class (v1) -> 19-class (v2/reBEN) index map.
# Source: RSIM label_indices.json
# (git.tu-berlin.de/rsim/BigEarthNet-S2_19-classes_models) — the same table
# the bigearthnet_common package ships. v1 index order is the ORIGINAL
# BigEarthNet ordering (see label_indices.json 'original_labels'); -1 marks
# classes dropped by the 19-class nomenclature.
BEN43_TO_BEN19 = [
    0,   # 0  Continuous urban fabric        -> Urban fabric
    0,   # 1  Discontinuous urban fabric     -> Urban fabric
    1,   # 2  Industrial or commercial units
    -1,  # 3  Road and rail networks         (dropped)
    -1,  # 4  Port areas                     (dropped)
    -1,  # 5  Airports                       (dropped)
    -1,  # 6  Mineral extraction sites       (dropped)
    -1,  # 7  Dump sites                     (dropped)
    -1,  # 8  Construction sites             (dropped)
    -1,  # 9  Green urban areas              (dropped)
    -1,  # 10 Sport and leisure facilities   (dropped)
    2, 2, 2,      # 11-13 arable land (non-irrigated / irrigated / rice)
    3, 3, 3,     # 14-16 permanent crops (vineyards / fruit / olive)
    4,           # 17 Pastures
    3,           # 18 Annual crops assoc. w/ permanent crops -> Permanent crops
    5,           # 19 Complex cultivation patterns
    6,           # 20 Land principally occupied by agriculture...
    7,           # 21 Agro-forestry areas
    8, 9, 10,    # 22-24 broad-leaved / coniferous / mixed forest
    11,          # 25 Natural grassland -> Nat. grassland & sparsely veg.
    12, 12,      # 26-27 Moors+heathland / Sclerophyllous -> Moors,heath,scler.
    13,          # 28 Transitional woodland/shrub
    14,          # 29 Beaches, dunes, sands
    -1,          # 30 Bare rock                    (dropped)
    11,          # 31 Sparsely vegetated areas     -> Nat. grassland & sparse
    -1,          # 32 Burnt areas                  (dropped)
    15, 15,      # 33-34 Inland marshes / Peatbogs -> Inland wetlands
    16, 16,      # 35-36 Salt marshes / Salines    -> Coastal wetlands
    -1,          # 37 Intertidal flats             (dropped)
    17, 17,      # 38-39 Water courses / bodies    -> Inland waters
    18, 18, 18,  # 40-42 Coastal lagoons / Estuaries / Sea -> Marine waters
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fine-tune Qwen2.5-VL with LoRA on remote-sensing data")
    p.add_argument("--dataset", default="bigearthnet",
                   choices=["bigearthnet", "rsvqa", "cdvqa", "changechat",
                            "mix", "all"],
                   help="Training dataset ('mix'/'all' = every folder found)")
    p.add_argument("--base_model", default=BASE_MODEL)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch_size", type=int, default=2)
    p.add_argument("--grad_accum", type=int, default=4)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--warmup_ratio", type=float, default=0.03)
    p.add_argument("--lora_r", type=int, default=16)
    p.add_argument("--lora_alpha", type=int, default=32)
    p.add_argument("--lora_dropout", type=float, default=0.05)
    p.add_argument("--max_length", type=int, default=2048)
    p.add_argument("--max_samples", type=int, default=0,
                   help="Cap dataset size (0 = all)")
    p.add_argument("--val_fraction", type=float, default=0.02)
    p.add_argument("--output_dir", default=str(LORA_OUTPUT))
    p.add_argument("--quantize", action="store_true",
                   help="4-bit QLoRA (fits a 24 GB GPU)")
    p.add_argument("--train_vision", action="store_true",
                   help="Also attach LoRA to the vision tower (slower, "
                        "stronger RS adaptation)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dry_run", action="store_true",
                   help="Print the resolved plan (datasets, sample counts, "
                        "trainable params estimate) and exit — no GPU needed")
    p.add_argument("--tune_image_size", type=int, default=448,
                   help="Max side the processor resizes images to during "
                        "training (keeps tokens + memory bounded)")
    return p.parse_args()


# ===========================================================================
# Unified sample format used everywhere:
#   {"images": [<abs path>, ...], "messages": [{"role": ..., "content": str}]}
# The collator converts `content` strings to multimodal parts, inserting one
# {"type": "image"} placeholder per listed image in the FIRST user turn.
# ===========================================================================
Sample = Dict[str, Any]


def _img(path: Path) -> Optional[str]:
    return str(path) if path.is_file() else None


# ---------------------------------------------------------------- BigEarthNet
def load_bigearthnet(limit: int = 0) -> List[Sample]:
    """
    Two supported layouts (see scripts/download_datasets.py):

    1. HF snapshot  data/bigearthnet/hf/  (datasets.load_from_disk)
       -> bands arrive as PIL images, 'labels' = list of 19-class indices.
    2. Raw tiles   data/bigearthnet/raw/**/<patch>/...json
       -> BigEarthNet v1/v2 per-patch label JSONs next to band GeoTIFFs.
    """
    samples: List[Sample] = []
    import PIL.Image as PILImage

    img_dir = DATA_DIR / "bigearthnet" / "images"
    jsonl = DATA_DIR / "bigearthnet" / "train.jsonl"
    hf_dir = DATA_DIR / "bigearthnet" / "hf"

    if jsonl.is_file():                                   # pre-materialised
        samples = _read_jsonl(jsonl)
    elif hf_dir.is_dir():                                 # materialise now
        try:
            from datasets import load_from_disk
        except ImportError:
            logger.error("pip install datasets  (needed to read data/bigearthnet/hf)")
            return []
        ds = load_from_disk(str(hf_dir))
        img_dir.mkdir(parents=True, exist_ok=True)
        band_keys = [k for k in ds.features if k.startswith("B")]
        # RGB proxy: B04 (red), B03 (green), B02 (blue) when available
        rgb = [b for b in ("B04", "B03", "B02") if b in band_keys] or band_keys[:3]
        for i, row in enumerate(ds):
            labels = row.get("labels") or []
            names = [BEN_19_CLASSES[c] for c in labels
                     if isinstance(c, int) and 0 <= c < len(BEN_19_CLASSES)]
            if not names:
                continue
            out = img_dir / f"ben_{i:06d}.jpg"
            if not out.is_file():
                try:
                    bands = [row[k] for k in rgb]
                    if not all(isinstance(b, PILImage.Image) for b in bands):
                        continue
                    arr = [b.resize((384, 384)) for b in bands]
                    PILImage.merge("RGB", tuple(arr)).save(out, quality=92)
                except Exception:
                    continue
            q = ("Which land-cover classes are present in this Sentinel-2 "
                 "image?")
            samples.append({
                "images": [str(out)],
                "messages": [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": _ben_answer(names)},
                ],
            })
            if limit and len(samples) >= limit:
                break
        _write_jsonl(jsonl, samples)
    else:                                                 # raw tiles
        raw = DATA_DIR / "bigearthnet" / "raw"
        if not raw.is_dir():
            logger.warning("BigEarthNet not found under %s "
                           "(run scripts/download_datasets.py --bigearthnet)",
                           DATA_DIR / "bigearthnet")
            return []
        import json as _json
        for meta in sorted(raw.rglob("*.json")):
            try:
                payload = _json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            idx19 = payload.get("labels_19") or payload.get("labels")
            if idx19 and idx19 and max(idx19) >= len(BEN_19_CLASSES):
                idx19 = sorted({BEN43_TO_BEN19[c] for c in idx19
                                if c < len(BEN43_TO_BEN19)})
            names = [BEN_19_CLASSES[c] for c in (idx19 or [])
                     if c < len(BEN_19_CLASSES)]
            if not names:
                continue
            tif = _img(meta.parent / "B04.tif") or \
                _img(meta.parent / "B02.tif")
            if not tif:
                continue
            samples.append({
                "images": [tif],
                "messages": [
                    {"role": "user", "content":
                        "Describe the land cover in this Sentinel-2 image."},
                    {"role": "assistant", "content": _ben_answer(names)},
                ],
            })
            if limit and len(samples) >= limit:
                break
    return samples


def _ben_answer(names: List[str]) -> str:
    land = [n for n in names if "waters" not in n and "wetlands" not in n]
    water = [n for n in names if "waters" in n or "wetlands" in n]
    parts = []
    if land:
        parts.append("The image shows " + ", ".join(n.lower() for n in
                                                    land[:4]) + ".")
    if water:
        parts.append("Water bodies detected: " +
                     ", ".join(n.lower() for n in water[:2]) + ".")
    parts.append("Sentinel-2 multispectral scene, 10 m ground sampling "
                 "distance.")
    return " ".join(parts)


# --------------------------------------------------------------------- JSONL
def load_jsonl_dataset(name: str, limit: int = 0) -> List[Sample]:
    """RSVQA / CDVQA / ChangeChat — {images, question, answer} JSONL."""
    ddir = DATA_DIR / name
    samples: List[Sample] = []
    for split in ("train", "train.jsonl", "all", "data"):
        f = ddir / (split if split.endswith(".jsonl") else f"{split}.jsonl")
        if f.is_file():
            for row in _read_jsonl(f):
                imgs = [str((ddir / p).resolve()) if not os.path.isabs(p)
                        else p for p in row.get("images", [])]
                if not imgs or not all(os.path.isfile(p) for p in imgs):
                    continue
                q = row.get("question") or row.get("query") or ""
                a = row.get("answer") or row.get("caption") or ""
                if not q or not a:
                    continue
                samples.append({
                    "images": imgs,
                    "messages": [{"role": "user", "content": q},
                                 {"role": "assistant", "content": a}],
                })
                if limit and len(samples) >= limit:
                    return samples
            break
    if not samples:
        logger.warning("Dataset '%s' has no usable JSONL samples under %s",
                       name, ddir)
    return samples


# ------------------------------------------------------------------- mix/all
def load_dataset(name: str, limit: int = 0) -> List[Sample]:
    if name == "bigearthnet":
        return load_bigearthnet(limit)
    if name in ("rsvqa", "cdvqa", "changechat"):
        return load_jsonl_dataset(name, limit)
    if name in ("mix", "all"):
        out: List[Sample] = []
        # BigEarthNet first (PS: RS adaptation on BigEarthNet), then the rest
        for ds in ("bigearthnet", "rsvqa", "cdvqa", "changechat"):
            part = load_dataset(ds, limit)
            logger.info("  %s: %d samples", ds, len(part))
            out.extend(part)
        return out
    raise ValueError(f"unknown dataset {name}")


def _read_jsonl(f: Path) -> List[dict]:
    rows = []
    with open(f, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_jsonl(f: Path, rows: List[dict]) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ===========================================================================
# Collator — text + images -> tensors, assistant-only supervision
# ===========================================================================
class VLMCollator:
    """
    Builds Qwen2.5-VL chat-format inputs:
      text  = chat template with <|image_pad|> placeholders
      pixel_values / image_grid_thw = processor-encoded images
    Labels are -100 over the prompt prefix (everything before and including
    the '<|im_start|>assistant\\n' header) so the model is trained to answer,
    not to re-read the question.
    """

    def __init__(self, processor, max_length: int, image_size: int):
        self.processor = processor
        self.max_length = max_length
        self.image_size = image_size

    def _encode(self, msgs: List[dict], images: List[Any],
                add_gen_prompt: bool):
        text = self.processor.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=add_gen_prompt)
        return self.processor(
            text=[text], images=images if images else None,
            padding=False, truncation=True, max_length=self.max_length,
            return_tensors="pt")

    def __call__(self, batch: List[Sample]) -> Dict[str, Any]:
        import torch
        from PIL import Image

        full_ids, full_pix, full_grid, labels = [], [], [], []
        for sample in batch:
            imgs = []
            for p in sample["images"]:
                im = Image.open(p).convert("RGB")
                im.thumbnail((self.image_size, self.image_size))
                imgs.append(im)
            msgs = []
            for i, m in enumerate(sample["messages"]):
                if i == 0 and imgs and m["role"] == "user":
                    content = [{"type": "image"} for _ in imgs]
                    content.append({"type": "text", "text": m["content"]})
                    msgs.append({"role": "user", "content": content})
                else:
                    msgs.append({"role": m["role"], "content": m["content"]})

            enc_full = self._encode(msgs, imgs, add_gen_prompt=False)
            enc_prompt = self._encode(msgs[:-1], imgs, add_gen_prompt=True)

            ids = enc_full["input_ids"][0]
            n_prompt = enc_prompt["input_ids"].shape[1]
            if n_prompt >= ids.shape[1]:      # degenerate — supervise all
                n_prompt = 0
            lab = ids.clone()
            lab[:n_prompt] = -100

            full_ids.append(ids)
            labels.append(lab)
            full_pix.append(enc_full.get("pixel_values"))
            full_grid.append(enc_full.get("image_grid_thw"))

        max_len = max(t.shape[0] for t in full_ids)
        pad_id = self.processor.tokenizer.pad_token_id or 0
        input_ids, attn, lab_out = [], [], []
        for ids, lab in zip(full_ids, labels):
            n_pad = max_len - ids.shape[0]
            input_ids.append(torch.cat([ids,
                torch.full((n_pad,), pad_id, dtype=ids.dtype)]))
            attn.append(torch.cat([torch.ones_like(ids),
                torch.zeros((n_pad,), dtype=ids.dtype)]))
            lab_out.append(torch.cat([lab,
                torch.full((n_pad,), -100, dtype=lab.dtype)]))

        out: Dict[str, Any] = {
            "input_ids": torch.stack(input_ids),
            "attention_mask": torch.stack(attn),
            "labels": torch.stack(lab_out),
        }
        if full_pix and full_pix[0] is not None:
            out["pixel_values"] = torch.cat(full_pix)
            out["image_grid_thw"] = torch.cat(full_grid)
        return out


# ===========================================================================
# Model setup
# ===========================================================================
def setup_model_and_processor(model_name: str, args):
    try:
        import torch
        from transformers import AutoProcessor
        from peft import LoraConfig
    except ImportError as e:
        logger.error("Missing dependencies: %s", e)
        logger.error("Install: pip install transformers peft bitsandbytes "
                     "accelerate datasets torch Pillow qwen-vl-utils")
        return None, None, None

    try:
        from transformers import Qwen2_5_VLForConditionalGeneration
    except ImportError:
        try:
            from transformers import (Qwen2VLForConditionalGeneration
                                      as Qwen2_5_VLForConditionalGeneration)
            logger.warning("transformers < 4.49 — using Qwen2VL class; "
                           "upgrade for native Qwen2.5-VL support")
        except ImportError:
            logger.error("transformers too old for Qwen2-VL — "
                         "pip install 'transformers>=4.49'")
            return None, None, None

    is_vl = "vl" in model_name.lower()
    load_kwargs: Dict[str, Any] = {"trust_remote_code": True}
    if args.quantize:
        try:
            from transformers import BitsAndBytesConfig
            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
            load_kwargs["device_map"] = "auto"
        except ImportError:
            logger.warning("bitsandbytes missing — training full precision")
            args.quantize = False

    logger.info("Loading base model: %s", model_name)
    if is_vl:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_name, torch_dtype=torch.bfloat16, **load_kwargs)
    else:
        from transformers import AutoModelForCausalLM
        model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.bfloat16, **load_kwargs)
    processor = AutoProcessor.from_pretrained(
        model_name, trust_remote_code=True, min_pixels=256 * 28 * 28,
        max_pixels=args.tune_image_size * args.tune_image_size * 28 * 28)

    if not args.quantize:
        model = model.to("cuda" if torch.cuda.is_available() else "cpu")
    if torch.cuda.is_available():
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    targets = ["q_proj", "k_proj", "v_proj", "o_proj",
               "gate_proj", "up_proj", "down_proj"]
    if args.train_vision and is_vl:
        # vision-tower modules (suffix match; distinct from the LLM names)
        targets += ["attn.qkv", "merger.mlp.0", "merger.mlp.2"]

    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout, bias="none",
        target_modules=targets, task_type="CAUSAL_LM")
    from peft import get_peft_model, prepare_model_for_kbit_training
    if args.quantize:
        model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    return model, processor, lora


# ===========================================================================
# Training loop
# ===========================================================================
def train(model, processor, collator, train_samples: List[Sample],
          val_samples: List[Sample], args) -> float:
    import torch
    from torch.utils.data import Dataset, DataLoader

    class _DS(Dataset):
        def __init__(self, rows):
            self.rows = rows

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            return self.rows[i]

    loader = DataLoader(_DS(train_samples), batch_size=args.batch_size,
                        shuffle=True, collate_fn=collator, num_workers=2,
                        drop_last=True)
    steps_per_epoch = max(1, len(loader) // args.grad_accum)
    total_steps = max(1, steps_per_epoch * args.epochs)
    warmup = max(1, int(total_steps * args.warmup_ratio))

    optim = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=args.lr,
        weight_decay=0.01)
    sched = torch.optim.lr_scheduler.LambdaLR(
        optim, lambda s: s / warmup if s < warmup
        else 0.5 * (1 + math.cos(math.pi * (s - warmup)
                                 / max(1, total_steps - warmup))))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scaler_dtype = torch.bfloat16
    use_amp = torch.cuda.is_available()

    model.train()
    step = 0
    final_loss = float("nan")
    for epoch in range(args.epochs):
        running, seen = 0.0, 0
        for i, batch in enumerate(loader):
            batch = {k: v.to(model.device) for k, v in batch.items()}
            with torch.autocast("cuda", dtype=scaler_dtype,
                                enabled=use_amp):
                out = model(**batch)
            (out.loss / args.grad_accum).backward()
            running += out.loss.item()
            seen += 1

            if (i + 1) % args.grad_accum == 0 or (i + 1) == len(loader):
                torch.nn.utils.clip_grad_norm_(
                    (p for p in model.parameters() if p.requires_grad), 1.0)
                optim.step()
                sched.step()
                optim.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0:
                    logger.info("epoch %d | step %d/%d | loss %.4f",
                                epoch + 1, step, total_steps,
                                running / max(seen, 1))

            if (i + 1) % 200 == 0:
                model.save_pretrained(str(out_dir))   # crash-safe checkpoint

        final_loss = running / max(seen, 1)
        logger.info("epoch %d/%d done | avg loss %.4f",
                    epoch + 1, args.epochs, final_loss)
        if val_samples:
            model.eval()
            val_loss, n = 0.0, 0
            with torch.no_grad():
                for j in range(0, len(val_samples), args.batch_size):
                    batch = collator(val_samples[j:j + args.batch_size])
                    batch = {k: v.to(model.device) for k, v in batch.items()}
                    with torch.autocast("cuda", dtype=scaler_dtype,
                                        enabled=use_amp):
                        out = model(**batch)
                    val_loss += out.loss.item()
                    n += 1
            logger.info("val loss %.4f", val_loss / max(n, 1))
            model.train()

    return final_loss


def save_adapter(model, processor, args, dataset_name: str,
                 n_samples: int) -> Path:
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out))
    processor.save_pretrained(str(out))
    meta = {
        "base_model": args.base_model,
        "adapter_path": str(out),
        "dataset": dataset_name,
        "n_samples": n_samples,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "quantized": args.quantize,
        "trained_vision_tower": args.train_vision,
        "epochs": args.epochs,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "serve": ("vllm serve --lora-modules satai-rs=" + str(out)),
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    logger.info("Adapter saved to %s", out)
    return out


# ===========================================================================
def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    ds_name = args.dataset
    samples = load_dataset(ds_name, args.max_samples)
    if not samples:
        logger.error("No training samples. Run: "
                     "python scripts/download_datasets.py --bigearthnet")
        sys.exit(1)
    random.shuffle(samples)
    n_val = max(1, int(len(samples) * args.val_fraction)) \
        if args.val_fraction > 0 and len(samples) >= 10 else 0
    val, train_s = samples[:n_val], samples[n_val:] or samples[:1]
    logger.info("Dataset %s — %d train / %d val samples",
                ds_name, len(train_s), len(val))

    if args.dry_run:
        n_img = sum(len(s["images"]) for s in train_s)
        logger.info("=== DRY RUN — plan ===")
        logger.info("base model        : %s", args.base_model)
        logger.info("train / val       : %d / %d", len(train_s), len(val))
        logger.info("images processed  : %d", n_img)
        logger.info("QLoRA             : %s", args.quantize)
        logger.info("vision-tower LoRA : %s", args.train_vision)
        logger.info("rank/alpha        : %d / %d", args.lora_r, args.lora_alpha)
        logger.info("effective batch   : %d (bs %d x accum %d)",
                    args.batch_size * args.grad_accum, args.batch_size,
                    args.grad_accum)
        logger.info("optimizer steps   : ~%d",
                    max(1, (len(train_s) // (args.batch_size * args.grad_accum))
                        * args.epochs))
        logger.info("output            : %s", args.output_dir)
        logger.info("supervision       : assistant tokens only (prompt masked)")
        return

    model, processor, _ = setup_model_and_processor(args.base_model, args)
    if model is None:
        sys.exit(1)
    collator = VLMCollator(processor, args.max_length, args.tune_image_size)
    final_loss = train(model, processor, collator, train_s, val, args)
    logger.info("Training complete — final loss %.4f", final_loss)
    save_adapter(model, processor, args, ds_name, len(train_s))


if __name__ == "__main__":
    main()
