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
| 2 | **Single-image VQA** (mandatory baseline) | `backend/vlm/tools/vqa_tool.py` + quantitative counting via `numeric_tool.py` + measured area extents via `quantity_tool.py` | ✅ |
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

### What's new (Sept 2026 — trust & reach pass)

- **Blind-test hallucination gate** — after answering a VQA/count/area/change
  question, the controller re-asks the *same question with no image* (one
  extra VLM call). If the blind control reproduces the reported answer, the
  answer likely came from language priors, not the pixels: the response is
  flagged in the trace, its confidence is down-weighted, and the blind answer
  is stored in the tool metadata for audit. Honest refusals by the control
  ("I can't see an image") pass untouched. Opt out per query with
  `metadata={"blind_test": false}` (eval harnesses do this to keep runs at
  one API call per sample).
- **Area / quantity quantifier** — a new `single_vqa_area` task and
  `quantity` specialist tool answer "how much area…", "…in hectares",
  "what percentage of the scene…" with **measured band-math**: NDWI / NDVI /
  NDBI computed on the original GeoTIFF, converted to hectares/km² from the
  ground sample distance (colour-ramped index map ships as evidence). On
  PNG/JPEG (or a raster without usable bands) it falls back to a clearly
  labelled scale-cue VLM estimate — never presented as measurement.
- **Multilingual queries (Hindi / Gujarati / Indic)** — non-Latin scripts are
  detected and every VLM tool prompt now instructs the model to answer in the
  user's language; the trace records a language note. Algorithmic outputs
  (areas, indices) stay numeric/English by design so evidence remains
  machine-checkable.
- **Evidence-citation verification** — every `[EV-n]` reference the model
  writes is validated against the actual evidence list (bogus ids raise a
  trace warning instead of pointing at nothing), and uncited answers get a
  **Evidence:** footer listing the exhibits they rest on — so the chain of
  claims → exhibits is closed in both directions. Eval harnesses score the
  answer only, never the footer.

### What's new (Sept 2026 — demo-readiness pass)

- **Georeferenced map view** — grounding boxes and changed-region polygons are
  now rendered on an interactive Leaflet map ("show on map" in the answer),
  with theme-aware tiles, per-feature popups and auto-fit bounds. Requires
  only a public tile CDN; degrades gracefully offline.
- **True PDF reports** — every query exports a paginated PDF audit report
  (`↓ pdf`, `?format=pdf`) with validation tables, the execution summary,
  embedded evidence images and the integrity digest. Graceful 501 if
  `reportlab` is absent from the deployment.
- **One-click demo scenes** — `samples/` ships seeded, sensor-plausible
  bundled imagery (SAR flood basin, 4-band multispectral agri GeoTIFF,
  bi-temporal urban-growth pair — all with real GeoTIFF geo-tags). The
  welcome screen gains sample cards + disaster-response presets (flood
  mapping, crop health/NDVI, urban growth, cloud-piercing optical+SAR).
- **Render keep-alive** — a lightweight self-ping daemon
  (`SATAI_KEEPALIVE=1`, Render's `RENDER_EXTERNAL_URL`) prevents free-tier
  sleep, so a judge never meets a cold 503.
- **GEE fetch routes mounted** — `/vlm/fetch-sentinel2`, `/vlm/fetch-sentinel1`,
  `/vlm/fetch-bitemporal`, `/vlm/fetch-crossmodal` were implemented but never
  wired into the app; they are live now.
- **Agentic-controller hardening** — fixed a crash where every *successfully
  decomposed* compound query died with a `NameError` when the trace was
  assembled (the decomposition path now records its tool plan correctly, with
  a regression test); the "no separable clauses" fallback is now audited in
  the trace notes.

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
  routes tasks between the locally-served base model and the RS-LoRA adapter
  (`tool_registry.select_model`), with the decision recorded in the audit trace.
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
cp .env.example .env         # local vLLM is the primary path (see Modes)

# 2. run
python run.py                # → http://localhost:8500
```

**Modes**

| Mode | When | How |
|------|------|-----|
| `VLM_MODE=local` | **primary** — ISRO finals / air-gapped | vLLM serving the RS-adapted weights — `vllm serve --config vllm_config.yaml` |
| `VLM_MODE=cloud` | optional dev convenience | any OpenAI-compatible vision endpoint (`CLOUD_MODEL`) |

Both paths speak the OpenAI vision wire format (images as `image_url` content
parts). Deploying on Render is
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

### 📈 Measured results — baseline vs fine-tuned

Setup: `Qwen2.5-VL-7B-Instruct-AWQ` served locally via **vLLM on a Kaggle T4**;
both arms run through the same eval harness on the same held-out slice (n=100).
Fine-tuned arm: **LoRA trained on 4,000 remote-sensing samples** (VQA, caption
and referring-expression box annotations).

| Eval | Metric | Base (zero-shot) | Fine-tuned (LoRA, 4k samples) |
|---|---|---|---|
| VQA (n=100) | accuracy | **33%** | **45%** |
| Caption (n=100) | BLEU-1 / CIDEr | 0.076 / 0.0003* | **0.22 / 0.011** |
| Grounding (n=100) | Acc@0.5 / mean IoU | — | **0.29 / 0.23** |

The 33% zero-shot accuracy is the point, not a shortcoming: the PS premise is
that **a generic VLM fails on remote-sensing imagery** — this is that failure,
measured. The RS-adapted arm closes it end-to-end (data prep → QLoRA training →
adapter export → vLLM serving → benchmark eval) on free cloud hardware:
**VQA 33% → 45% (+12 points)**, **caption BLEU-1 +189% (0.076 → 0.22)**, and
grounding — trained on referring-expression boxes for the first time — reaches
**Acc@0.5 0.29, mean IoU 0.23** from a localisation-untrained baseline.

**Grounding context.** The earlier 200-sample smoke adapter scored 0.0 / 0.008
because it never saw box annotations — adaptation had transferred semantics,
not spatial localization. After training on 4k samples including referring
expressions, Acc@0.5 rises to 0.29. For reference: GeoChat fine-tuned scores
49.8% with 318K instruction samples — the gap is training-data scale, not
approach, and SatAI still performs grounding through a **dedicated
deterministic tool over the VLM's output** (validated boxes, overlay rendering,
pixel-true GeoJSON) rather than trusting raw VLM coordinate regression.

**Scope & limitations.** Fine-tuning ran on a free-tier cloud GPU (Kaggle T4)
under hackathon time limits on **4,000 training samples** with a
**7B-parameter VLM** — larger runs will push these numbers further; this table
reflects the measured 4k-sample checkpoint.

\* literal n-gram overlap vs reference captions — BLEU/CIDEr are sensitive to
phrasing and style, not only correctness; interpreted alongside the VQA and
grounding numbers.

## 🧪 Tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/          # 126 tests — full agentic loop on a mock VLM
```

Covers the orchestration loop, validation, tools, GeoTIFF handling, spectral
band-math, the blind-test gate, area quantification, multilingual routing,
evidence-citation verification, the transparency layer (audit digest,
feedback, reports) and the HTTP API — all offline via a deterministic mock VLM.

## 🔌 API

| Endpoint | Purpose |
|----------|---------|
| `POST /vlm/query` | full agentic pipeline (query, images[], mode) |
| `POST /vlm/caption` `/vlm/ground` `/vlm/change` `/vlm/sar-fusion` | direct specialist-tool endpoints |
| `POST /vlm/upload` | image probe: format, dims, bands, modality, GeoTIFF metadata |
| `POST /vlm/validate` | dry-run of the compatibility checker |
| `POST /vlm/feedback` | analyst review (👍/👎 + note) appended to the audit record |
| `GET /vlm/samples` · `/samples/*` | bundled demo scenes index + scene files |
| `POST /vlm/fetch-sentinel2` `/fetch-sentinel1` `/fetch-bitemporal` `/fetch-crossmodal` | Google Earth Engine scene fetch |
| `GET /vlm/status` · `/vlm/history` · `/vlm/report/{id}` | status, audit history, HTML/JSON/PDF reports (`?format=`) |
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
    vlm_client.py        VLM client — local vLLM (base ⇄ RS-LoRA adapter)
    visual_evidence.py   annotated boxes, change map, side-by-side renders
    report.py            auditable HTML/JSON reports
    tools/               vqa · numeric · caption · ground · change · sar_fusion · quantity · spectral_index
    eval/                VRSBench / RSVQA / CDVQA harnesses + metrics
frontend/                vanilla-JS SPA (chat, evidence gallery, trace drawer, map view, dark mode)
docs/                    22 deep-dive engineering documents (see table above)
scripts/                 dataset downloader + multimodal LoRA trainer + sample-scene generator
samples/                 bundled demo scenes (GeoTIFF/TIFF, geo-tagged) + index
tests/                   126-test suite (mock VLM, no network needed)
```

## 🔒 Security notes

`.env` is gitignored; keys are read from the environment only. The history
store is in-memory and bounded (50 queries). Rate limiting protects the VLM
quota per IP.

## 👥 Team

Team SatAI — subhansh-dev · built for SIH 2026, PS SIH26167.
