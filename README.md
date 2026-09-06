# SatAI — SatQuery AI

**Agentic Vision-Language Assistant for Multimodal Remote Sensing Image Analysis through Text Queries**

> Smart India Hackathon 2026 · **PS ID SIH26167** · Organisation: **ISRO / Department of Space** · Category: Software · Theme: Space Technology

SatAI is not a thin VLM wrapper. Every query runs through an **agentic
controller** that validates the input imagery, classifies the request, selects
specialist tools from a predefined registry, executes them with permitted
parameters only, and merges text + spatial output into an auditable answer with
visual evidence, confidence and a downloadable report — stamped with an
SHA-256 integrity digest and open to human analyst review.

---

## ✅ PS SIH26167 requirement coverage

| # | PS requirement | Where it lives | Status |
|---|----------------|----------------|--------|
| 1 | **RS adaptation** — VLM component fine-tuned on BigEarthNet | `scripts/train_lora.py` (multimodal QLoRA on Qwen2.5-VL), `scripts/download_datasets.py`, served via vLLM LoRA adapter (`vllm_config.yaml`) | ✅ |
| 2 | **Single-image VQA** (mandatory baseline) | `backend/vlm/tools/vqa_tool.py` + quantitative counting via `numeric_tool.py` | ✅ |
| 3 | **Second single-image task** — captioning **and** text-guided grounding | `caption_tool.py` (scene description) + `ground_tool.py` (0–1000 normalised boxes → GeoJSON) | ✅ both options |
| 4 | **Multi-image change analysis** (mandatory) — change description, change-VQA, spatial change map | `change_tool.py` + heuristic change mask in `visual_evidence.py` | ✅ |
| 5 | **Cross-modal optical + SAR pair analysis** | `sar_fusion_tool.py` (complementary built-up / water / roughness extraction) | ✅ |
| 6 | **Agentic orchestration** — parse query → classify → validate → registry select → execute → combine | `backend/vlm/controller.py` (9-step loop), `tool_registry.py` (task→tool mapping + param allowlists) | ✅ |
| 7 | **Input compatibility checking** — number, modality, format, metadata, pair compatibility | `input_validator.py` + `image_utils.py` (GeoTIFF geokeys, multi-band, SAR detection) | ✅ |
| 8 | **Visual evidence + confidence + execution summary + downloadable report** | `visual_evidence.py` (annotated boxes, change map, side-by-side), per-tool confidence protocol, `report.py` (HTML/JSON), `/vlm/report/{id}/download` | ✅ |
| 9 | **Interactive GUI/Web app** | `frontend/` — vanilla JS single-page app, zero build step | ✅ |
| 10 | **Benchmark evaluation** (VRSBench / RSVQA / CDVQA) | `backend/vlm/eval/` — BLEU·METEOR·ROUGE-L·CIDEr, grounding Acc@0.5/0.7 (IoU), VQA accuracy | ✅ |

Inputs: single optical/multispectral/SAR image · registered optical+SAR pair ·
bi-temporal pair. **GeoTIFF/TIFF are first-class** (georeference is carried into
the GeoJSON output); PNG/JPEG accepted for public benchmark data.

### What's new (Sept 2026 — transparency & experience pass)

- **Chain of evidence** — every answer ships with numbered, inspectable
  evidence (EV-1, EV-2, …); the UI manifest links claims to exhibits, reports
  carry the same EV prefixes, and grounding answers expose a machine-readable
  box table (label · confidence · bbox).
- **Tamper-evident audit records** — every response is stamped with an
  **SHA-256 integrity digest** over its canonical JSON; anyone can recompute it
  from the downloaded JSON report to prove the record was not altered.
- **Human-in-the-loop review** — 👍/👎 analyst feedback (with optional note) is
  recorded against the audit record via `POST /vlm/feedback`, tallied, and
  printed in the downloadable report — without ever mutating the frozen answer
  or its digest.
- **Deeper trace UX** — the execution drawer now shows pipeline stage chips,
  an **execution waterfall** (per-tool latency bars), the verbatim query,
  image-preparation notes and the integrity hash with copy button.
- **Dark mode** — a full mission-control night theme (topbar toggle,
  `prefers-color-scheme` aware, persisted, no first-paint flash).
- **Tactile institutional UI** — the government-portal aesthetic gained a
  skeuomorphic/neumorphic layer: film-grain paper, letterpress serif,
  stamped ISRO crest seal, extruded panels, etched input wells.
- **Model-hint passthrough repaired** — every specialist tool now honours the
  registry's model selection (previously only VQA/change did); the grounding
  tool distinguishes *honest empty results* from *parse failures* in its
  confidence; SAR spread statistics are honestly labelled as
  log-compressed-amplitude descriptors.

### What's new (Sept 2026 hardening + upgrade pass)

- **Agentic depth** — compound queries are *decomposed* into sub-questions and
  routed to specialist tools which run **in parallel**; the **model registry**
  routes tasks between the cloud flagship and the locally-served RS-LoRA
  weights (`tool_registry.select_model`), with the decision recorded in the
  audit trace.
- **Calibrated confidence** — counting queries use *self-consistency sampling*
  (modal answer of n samples + agreement bonus); the `CONFIDENCE` protocol now
  parses decimal self-reports correctly (`0.85` used to parse as `0.0`).
- **Algorithmic SAR layer** — speckle CoV, dB dynamic range, dark/bright
  fractions are *measured* on the raw backscatter and injected into fusion
  prompts (verifiable numbers, not VLM guesses).
- **Spectral index tool** — NDVI / NDWI / NDBI computed from the original
  multispectral GeoTIFF bands (Sentinel-2 & 4-band conventions), with a
  colour-ramped map, class fractions and **km² area estimates from the ground
  sampling distance**. Works fully offline — no VLM key required.
- **GeoTIFF-first fixes** — true-colour band selection for 10–13-band stacks
  (was showing SWIR false colour), NaN/nodata-safe percentile stretching,
  WGS84 UTM→lon/lat conversion for GeoJSON (RFC 7946), server-side JPEG
  previews so TIFFs render in the browser, aspect-preserving change maps with
  changed-region polygons exported as georeferenced GeoJSON.
- **Local vLLM mode repaired** — the client probes `/v1/models`, resolves the
  LoRA adapter / base model against what is actually served, and
  `max-model-len` raised to 8192 so pair tasks fit in context.
- **Performance** — raster validation/preparation/evidence rendering moved off
  the event loop (`asyncio.to_thread`), independent tools executed via
  `asyncio.gather`, evidence payloads switched to JPEG (~5-8× smaller), and
  VLM retries now honour `Retry-After` with exponential backoff + jitter.
- **Fine-tuning correctness** — `train_lora.py` now uses the *official*
  BigEarthNet v1→19-class label conversion (RSIM `label_indices.json`); the
  previous identity-style map learned wrong labels.

---

## 🚀 Quickstart

```bash
pip install -r requirements.txt

# 1. configure
cp .env.example .env         # add OPENROUTER_API_KEY (cloud dev mode)

# 2. run
python run.py                # → http://localhost:8500
```

**Modes**

| Mode | When | How |
|------|------|-----|
| `VLM_MODE=cloud` | development, demos | Any OpenRouter vision model (`CLOUD_MODEL`) |
| `VLM_MODE=local` | ISRO finals / air-gapped | vLLM serving the RS-adapted weights — `vllm serve --config vllm_config.yaml` |

Both paths speak the OpenAI vision wire format (images as `image_url` content
parts — works with vLLM and OpenRouter alike). Deploying on Render is
`render.yaml` out of the box; the frontend is also a pure-static folder for
Vercel (`?api=https://your-backend` to point at a remote backend).

---

## 🧠 The agentic loop (what actually happens on `/vlm/query`)

```
query + images ─▶ 1. VALIDATE     number / format / modality / dims / pair compatibility
                  2. CLASSIFY     rule-based router, VLM-as-judge for ambiguity
                  3. SELECT       task → tools from the predefined registry
                  4. PREPARE      GeoTIFF decode, band pick, SAR stretch, pair-norm, downscale
                  5. EXECUTE      only registry-declared parameters passed to tools
                  6. COMBINE      merged answer + weighted confidence
                  7. EVIDENCE     annotated boxes · change map · side-by-side · input views
                  8. GEOJSON      grounding boxes → pixel or map coordinates (GeoTIFF)
                  9. AUDIT        execution trace + HTML/JSON report, history store
```

Every response embeds: `validation` report, `trace` (task, classification
reason, tools selected/invoked, parameters, timings, confidence sources),
`visual_evidence`, `geojson`, and a `report_url`.

**Confidence is honest, not fabricated** — tools self-report via a
`CONFIDENCE:` protocol, grounding derives it from box scores × parse success,
counting from answer-parse success; the controller down-weights unparsed
fallbacks.

---

## 🛰️ RS adaptation (PS requirement #1)

```bash
# data: BigEarthNet (~18 GB, Sentinel-2, 19-class land cover)
python scripts/download_datasets.py --bigearthnet

# multimodal LoRA fine-tune (assistant-only supervision, vision tokens real)
python scripts/train_lora.py --dataset bigearthnet --quantize --dry_run
python scripts/train_lora.py --dataset bigearthnet --quantize --epochs 3

# serve the adapter
vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
    --lora-modules satai-rs=backend/vlm/lora/checkpoints \
    --config vllm_config.yaml
export VLM_MODE=local VLM_LORA_ADAPTER=satai-rs
```

`train_lora.py` is a **real multimodal pipeline**: images are encoded by the
Qwen2.5-VL processor (chat template + `<|image_pad|>` tokens), prompt tokens
are masked (`-100`) so only the assistant reply is supervised, and adapters
can cover the vision tower too (`--train_vision`).

## 📊 Benchmarks

```bash
python scripts/download_datasets.py --placeholder       # smoke data
python -m backend.vlm.eval.eval_vrsbench --mode caption  # BLEU/METEOR/ROUGE-L/CIDEr
python -m backend.vlm.eval.eval_vrsbench --mode grounding # Acc@0.5 / Acc@0.7 (IoU)
python -m backend.vlm.eval.eval_vrsbench --mode vqa
python -m backend.vlm.eval.eval_rsvqa                    # VQA accuracy by type
python -m backend.vlm.eval.eval_cdvqa                    # change-VQA accuracy
```

## 🧪 Tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/          # 64 tests — full agentic loop on a mock VLM
```

Covers the orchestration loop, validation, tools, GeoTIFF handling, spectral
band-math, the transparency layer (audit digest, feedback, reports) and the
HTTP API — all offline via a deterministic mock VLM.

## 📚 Deep documentation

Every feature — what it is, why it exists (PS mapping), how it works at code
level, what it connects to — is documented in [`docs/`](docs/README.md):

| | | |
|---|---|---|
| [01 Architecture](docs/01-system-architecture.md) | [02 Agentic controller](docs/02-agentic-controller.md) | [03 Tool & model registry](docs/03-tool-registry.md) |
| [04 VQA + numeric](docs/04-tool-vqa-numeric.md) | [05 Captioning](docs/05-tool-caption.md) | [06 Grounding](docs/06-tool-grounding.md) |
| [07 Change detection](docs/07-tool-change-detection.md) | [08 SAR fusion](docs/08-tool-sar-fusion.md) | [09 Spectral indices](docs/09-tool-spectral-indices.md) |
| [10 Visual evidence](docs/10-visual-evidence.md) | [11 GeoJSON & georeferencing](docs/11-geojson-georeferencing.md) | [12 Input validation](docs/12-input-validation.md) |
| [13 Image processing](docs/13-image-processing.md) | [14 VLM client](docs/14-vlm-client.md) | [15 LoRA fine-tuning](docs/15-lora-finetuning.md) |
| [16 Eval harness](docs/16-eval-harness.md) | [17 Transparency & audit](docs/17-transparency-auditability.md) | [18 Frontend & UI](docs/18-frontend-ui.md) |
| [19 API reference](docs/19-api-reference.md) | [20 Configuration](docs/20-configuration.md) | [21 Testing](docs/21-testing.md) |
| [22 Deployment](docs/22-deployment.md) | | |

## 🔌 API

| Endpoint | Purpose |
|----------|---------|
| `POST /vlm/query` | full agentic pipeline (query, images[], mode) |
| `POST /vlm/caption` `/vlm/ground` `/vlm/change` `/vlm/sar-fusion` | direct specialist-tool endpoints |
| `POST /vlm/upload` | image probe: format, dims, bands, modality, GeoTIFF metadata |
| `POST /vlm/validate` | dry-run of the compatibility checker |
| `POST /vlm/feedback` | analyst review (👍/👎 + note) appended to the audit record |
| `GET /vlm/status` · `/vlm/history` · `/vlm/report/{id}` | status, audit history, HTML/JSON reports |
| `GET /api/health` | liveness + VLM readiness |

## 📁 Repository layout

```
backend/
  api/main.py            FastAPI app, rate limiting, static hosting
  core/config.py         all SATAI_* settings, .env bootstrap
  vlm/
    controller.py        9-step agentic orchestration loop
    tool_registry.py     predefined task→tool mapping + param allowlists
    input_validator.py   PS compatibility checker
    image_utils.py       GeoTIFF/multi-band/SAR handling, pair normalisation
    vlm_client.py        cloud (OpenRouter) ⇄ local (vLLM) client
    visual_evidence.py   annotated boxes, change map, side-by-side renders
    report.py            auditable HTML/JSON reports
    tools/               vqa · numeric · caption · ground · change · sar_fusion · spectral_index
    eval/                VRSBench / RSVQA / CDVQA harnesses + metrics
frontend/                vanilla-JS SPA (chat, evidence gallery, trace drawer, dark mode)
docs/                    22 deep-dive engineering documents (see table above)
scripts/                 dataset downloader + multimodal LoRA trainer
tests/                   64-test suite (mock VLM, no network needed)
```

## 🔒 Security notes

`.env` is gitignored; keys are read from the environment only. The history
store is in-memory and bounded (50 queries). Rate limiting protects the VLM
quota per IP.

## 👥 Team

Team SatAI — subhansh-dev · built for SIH 2026, PS SIH26167.
