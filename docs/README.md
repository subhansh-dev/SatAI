# SatAI — Engineering Documentation

**SatQuery AI** · Interactive Vision-Language Assistant for Multimodal Remote Sensing Image Analysis
Smart India Hackathon 2026 · Problem Statement **SIH26167** · ISRO / Department of Space

This folder is the complete, feature-by-feature engineering reference for the SatAI
system. Every document explains **what the feature is, why it exists (mapped to the
PS requirement it serves), how it works at code level, what it connects to, and what
its real-world impact is**. Nothing in the codebase is intentionally left undocumented.

---

## How to read this documentation

| You want to understand… | Read |
|---|---|
| The system in one sitting | 01 → 02 → 10 → 17 |
| How a query travels end-to-end | 01 (§ request lifecycle), 02, 19 |
| A specific specialist tool | 04–09 |
| How satellite pixels become map coordinates | 11, 13 |
| How inputs are checked before any model runs | 12 |
| How the model itself is adapted to remote sensing | 14, 15, 16 |
| How answers are made verifiable and tamper-evident | 10, 17 |
| How to run, configure, deploy, test | 19–22 |

## Document index

### Core system

| # | Document | What it covers |
|---|---|---|
| 01 | [System architecture](01-system-architecture.md) | Full module map, request lifecycle, dataflow, design principles |
| 02 | [Agentic controller](02-agentic-controller.md) | The PS-mandated orchestration loop: validate → classify → select → execute → combine → auditable report; query decomposition; parallel execution |
| 03 | [Tool registry & model registry](03-tool-registry.md) | How specialist tools are registered, selected and matched to tasks; how models are chosen per task |

### Specialist tools (the registry)

| # | Document | Covers |
|---|---|---|
| 04 | [VQA + Numeric tools](04-tool-vqa-numeric.md) | Single-image question answering; counting with self-consistency confidence |
| 05 | [Captioning tool](05-tool-caption.md) | Scene description (PS single-image task option A) |
| 06 | [Grounding tool](06-tool-grounding.md) | Text-guided region localisation with 0–1000 boxes (option B) |
| 07 | [Change detection tool](07-tool-change-detection.md) | Bi-temporal "what changed between these two dates" |
| 08 | [Optical+SAR fusion tool](08-tool-sar-fusion.md) | Cross-modal pair analysis with measured SAR statistics |
| 09 | [Spectral index tool](09-tool-spectral-indices.md) | Algorithmic NDVI/NDWI/NDBI band math on the original raster |

### Evidence, geospatial & trust layer

| # | Document | Covers |
|---|---|---|
| 10 | [Visual evidence engine](10-visual-evidence.md) | Annotated grounding renders, heuristic change maps, side-by-side composites, input views — the "answers backed by visual results" requirement |
| 11 | [GeoJSON & georeferencing](11-geojson-georeferencing.md) | Pixel → map coordinate math, UTM/EPSG, GeoTIFF georeference preserved in outputs |
| 12 | [Input validation](12-input-validation.md) | Compatibility checking, modality detection, all issue codes |
| 13 | [Image processing](13-image-processing.md) | Radiometric normalisation, GeoTIFF decode, SAR statistics |
| 14 | [VLM client](14-vlm-client.md) | Cloud (OpenRouter) / local (vLLM) dual backend, retries, model resolution |
| 15 | [LoRA fine-tuning](15-lora-finetuning.md) | Qwen2.5-VL + BigEarthNet-19 RS adaptation, QLoRA training, vLLM serving |
| 16 | [Evaluation harness](16-eval-harness.md) | CDVQA / RSVQA / VRSBench benchmarks and metrics |
| 17 | [Transparency & auditability](17-transparency-auditability.md) | Execution trace, chain of evidence, integrity digest (SHA-256), analyst feedback loop, downloadable reports |

### Interface & operations

| # | Document | Covers |
|---|---|---|
| 18 | [Frontend & UI system](18-frontend-ui.md) | Institutional design, tactile layer, dark mode, evidence UI, trace waterfall |
| 19 | [API reference](19-api-reference.md) | Every HTTP endpoint with schemas + curl examples |
| 20 | [Configuration](20-configuration.md) | Every constant and environment variable |
| 21 | [Testing](21-testing.md) | The 64-test offline suite and the mock-VLM design |
| 22 | [Deployment](22-deployment.md) | Local, Render, Vercel, split deployments, air-gapped topology |

---

## The one-paragraph version

SatAI is an **agentic** vision-language assistant: instead of throwing a satellite
image at a general model, it runs a deterministic pipeline — *validate inputs →
classify the task → select specialist tools and a model from a registry → execute
(with only permitted parameters) → combine results with visual evidence and
calibrated confidence → emit a tamper-evident, downloadable audit report*. Seven
specialist tools cover every mandatory PS capability (single-image VQA, counting,
captioning, grounding, bi-temporal change, optical+SAR fusion, spectral band-math),
a Qwen2.5-VL LoRA fine-tune on BigEarthNet provides the remote-sensing adaptation,
and every answer ships with numbered visual evidence (EV-1, EV-2, …), machine-readable
GeoJSON with preserved georeference, and an SHA-256 integrity digest.
