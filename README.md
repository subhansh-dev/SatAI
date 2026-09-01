<p align="center">
  <br>
  <img src="https://img.shields.io/badge/SIH-2026-blue?style=for-the-badge" alt="sih">
  <img src="https://img.shields.io/badge/PS-SIH26167--ISRO-red?style=for-the-badge" alt="ps">
  <img src="https://img.shields.io/badge/version-1.0.0-green?style=for-the-badge" alt="version">
  <img src="https://img.shields.io/badge/VLM-Qwen2.5--VL--7B-purple?style=for-the-badge" alt="vlm">
  <img src="https://img.shields.io/badge/tools-8-specialist-orange?style=for-the-badge" alt="tools">
  <img src="https://img.shields.io/badge/APIs-24--free-yellow?style=for-the-badge" alt="apis">
  <br><br>
</p>

```
SatAI v1.0.0
SatQuery AI — Agentic Vision-Language Assistant
for Multimodal Remote Sensing Image Analysis
```

<p align="center">
  <b>Problem Statement: An Interactive Vision-Language Assistant for Multimodal Remote Sensing Image Analysis through Text Queries</b><br>
  Organization: ISRO (Indian Space Research Organisation, Department of Space) &nbsp;|&nbsp; PS ID: SIH26167 &nbsp;|&nbsp; Category: Software &nbsp;|&nbsp; Theme: Space Technology
</p>

---

## What is SatAI?

SatAI is an **agentic vision-language assistant** that analyzes satellite imagery through natural-language queries. It automatically routes queries to the right specialist tools and returns evidence-grounded answers with full execution traces.

### Three Mandatory Input Modes

| Mode | Input | Output |
|---|---|---|
| **Single Image** | One optical/multispectral OR SAR image | VQA + captioning OR grounding |
| **Cross-Modal Pair** | Co-registered optical + SAR | Joint information extraction |
| **Bi-Temporal Pair** | Two images of same area, different dates | Change description / change-VQA |

### Architecture

```
User Query (text + images)
    │
    ▼
┌─────────────────────┐
│   AGENTIC CONTROLLER│
│                     │
│ - Classify task     │
│ - Select tools      │
│ - Execute pipeline  │
│ - Merge results     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   SPECIALIST TOOLS  │
│                     │
│ - VQA               │  Single-image questions
│ - Caption           │  Scene description
│ - Ground            │  Object localization (OBB)
│ - Change Desc       │  Bi-temporal analysis
│ - SAR Fusion        │  Cross-modal analysis
│ - Numeric           │  Quantitative answers
│ - Env Scan          │  24 environmental APIs
│ - Segment           │  Change masks (planned)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  EXECUTION SUMMARY  │
│                     │
│ - Task classified   │
│ - Tools invoked     │
│ - Confidence scores │
│ - GeoJSON export    │
└─────────────────────┘
```

## Quick Start

```bash
cd SatAI

# Install dependencies
pip install -r requirements.txt

# Run the server
python run.py

# Open browser
# http://localhost:8500
# Click "SatAI VLM" tab
```

### VLM Configuration

```bash
# Cloud mode (development)
VLM_MODE=cloud
OPENROUTER_API_KEY=your_key_here

# Local mode (ISRO finals — air-gapped)
VLM_MODE=local
VLM_LOCAL_URL=http://localhost:8000/v1
```

### Start Local VLM Server

```bash
# Requires GPU with 12+ GB VRAM
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-VL-7B-Instruct \
    --tensor-parallel-size 1 \
    --quantization awq \
    --port 8000
```

## Fine-Tuning

```bash
# Download BigEarthNet dataset first
# Then fine-tune with LoRA
python scripts/train_lora.py --dataset bigearthnet --epochs 3 --batch_size 4 --quantize

# Or dry-run to check config
python scripts/train_lora.py --dataset bigearthnet --dry_run
```

## Evaluation

```bash
# VRSBench (captioning, grounding, VQA)
python -m vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode caption
python -m vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode grounding
python -m vlm.eval.eval_vrsbench --data_dir data/vrsbench --mode vqa

# RSVQA (remote sensing VQA)
python -m vlm.eval.eval_rsvqa --data_dir data/rsvqa

# CDVQA (change detection VQA)
python -m vlm.eval.eval_cdvqa --data_dir data/cdvqa
```

## Project Structure

```
SatAI/
├── backend/
│   ├── api/
│   │   └── main.py              # FastAPI app + 70+ routes
│   ├── vlm/                      # VLM integration (NEW)
│   │   ├── vlm_client.py         # Cloud ↔ Local VLM interface
│   │   ├── controller.py         # Agentic task router
│   │   ├── tool_registry.py      # Specialist tool registry
│   │   ├── schemas.py            # Pydantic models
│   │   ├── routes.py             # FastAPI VLM endpoints
│   │   ├── tools/                # 8 specialist tools
│   │   │   ├── vqa_tool.py       # Single-image VQA
│   │   │   ├── caption_tool.py   # Image captioning
│   │   │   ├── ground_tool.py    # Visual grounding (OBB)
│   │   │   ├── change_tool.py    # Bi-temporal change analysis
│   │   │   ├── sar_fusion_tool.py# Optical-SAR cross-modal
│   │   │   ├── numeric_tool.py   # Numeric answers
│   │   │   ├── env_tool.py       # 24 environmental APIs
│   │   │   └── base.py           # Base tool class
│   │   ├── lora/                 # LoRA adapters
│   │   └── eval/                 # Evaluation scripts
│   │       ├── eval_vrsbench.py  # VRSBench eval
│   │       ├── eval_rsvqa.py     # RSVQA eval
│   │       └── eval_cdvqa.py     # CDVQA eval
│   └── pipeline/                 # Existing modules (kept)
├── frontend/
│   ├── index.html                # 10-tab dark terminal UI
│   ├── js/
│   │   ├── app.js                # Main app logic
│   │   └── vlm_chat.js           # VLM chat interface
│   └── css/style.css             # Dark terminal aesthetic
├── scripts/
│   └── train_lora.py             # LoRA fine-tuning
├── data/                         # Datasets (gitignored)
├── models/                       # Model weights (gitignored)
├── AGENTS.md                     # Full project spec
├── requirements.txt
└── run.py
```

## Tech Stack

| Component | Technology |
|---|---|
| VLM | Qwen2.5-VL-7B-Instruct |
| Fine-tuning | LoRA / QLoRA (rank=16, alpha=32) |
| Serving | vLLM (local) or OpenRouter (cloud) |
| Backend | FastAPI + Python 3.9+ |
| Frontend | HTML/CSS/JS (dark terminal) |
| Evaluation | VRSBench, RSVQA, CDVQA |
| Environmental APIs | 24 free-tier APIs |

## Mandatory Requirements Checklist

- [x] Remote-sensing VLM adaptation (BigEarthNet LoRA)
- [x] Single-image VQA (mandatory)
- [x] Single-image captioning OR grounding
- [x] Multi-image change analysis
- [x] Cross-modal optical-SAR analysis
- [x] Agentic orchestration (auto tool selection)
- [x] Auditable execution summary
- [x] Interactive GUI
- [x] GeoJSON export
- [x] Self-hosted (air-gapped capable)

## Problem Statement

**SIH26167** — ISRO

An agentic vision-language assistant for analyzing single and paired remote-sensing images through natural-language queries. The system must accept natural-language queries, automatically route to specialist models, return evidence-grounded results, and provide auditable execution summaries.

## License

Internal use — Smart India Hackathon 2026
