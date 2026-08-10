<p align="center">
  <br>
  <img src="https://img.shields.io/badge/SIH-2025-blue?style=for-the-badge" alt="sih">
  <img src="https://img.shields.io/badge/PS-SIH1563--NTRO-red?style=for-the-badge" alt="ps">
  <img src="https://img.shields.io/badge/version-0.6.0-green?style=for-the-badge" alt="version">
  <img src="https://img.shields.io/badge/API-70%2B-orange?style=for-the-badge" alt="endpoints">
  <img src="https://img.shields.io/badge/AI-Cerebras--120B-purple?style=for-the-badge" alt="ai">
  <img src="https://img.shields.io/badge/data-24--sources-yellow?style=for-the-badge" alt="sources">
  <br><br>
</p>

```
CHRONOVISOR v0.6.0
Multi-Source Satellite Intelligence Platform
for Change Detection & Anomaly Analysis
```

<p align="center">
  <b>Problem Statement: Automatic Change Detection in Synthetic Aperture Radar (SAR) Satellite Images</b><br>
  Ministry: National Technical Research Organisation (NTRO) &nbsp;|&nbsp; PS ID: SIH1563 &nbsp;|&nbsp; Category: Software &nbsp;|&nbsp; Theme: Space Technology
</p>

---

## What is this?

A platform that takes a location on a map and tells you whether the changes you're seeing in satellite imagery are man-made or natural. It pulls data from 24 different sources — SAR radar, optical, thermal, soil, seismic, magnetic, historical archives — and fuses them into a single score with confidence rating.

The core problem it solves: SAR change detection gives you a change map, but 40%+ of those "changes" are just floods, vegetation, or snow. This filters those out.

---

## The actual problem (from NTRO)

> *"Change detection between two SAR images is straightforward if co-registered — the difference or ratio gives the change map. But such maps invariably have many natural changes (water body extent, flood extent, snow cover, forest cover). Our interest is to detect only man-made changes and avoid natural changes."*
>
> — NTRO, Smart India Hackathon 2025

So the challenge isn't "can you detect changes" — it's "can you ignore the noise." That's what this project does.

---

## How it works

The main thing is a 7-component weighted scoring engine. When you scan a location, it pulls data from multiple sources and combines them:

```
┌─────────────────────────────────────┐
│     MULTI-SOURCE FUSION ENGINE      │
│        (Weighted 7-Layer Scoring)   │
└─────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   SAR Change    Optical/     Environmental
   Detection     Thermal      Context
        │             │             │
        └─────────────┼─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │  FUSED SCORE: 0-100%      │
        │  + Confidence rating      │
        │  + GeoJSON export         │
        └───────────────────────────┘
```

The 7 components and their weights:

| Component | Weight | What it does |
|---|---|---|
| Satellite anomalies | 35% | NDVI/thermal/SAR patterns from Sentinel-1/2 |
| Soil preservation | 20% | Clay content, pH, organic carbon — clay preserves structures, sand doesn't |
| Seismic filter | 10% | Penalizes active fault zones (geological noise) |
| Water table | 10% | Shallow water distorts thermal readings |
| OSM historical | 10% | Known sites = confirmed man-made |
| Temporal consistency | 10% | Real structures persist, natural changes don't |
| Web archive evidence | 5% | Academic papers = validated sites |

There are also stacking modifiers: high clay content adds 35%, active seismic zones subtract 25%, nearby archaeological sites add 30%.

---

## NTRO requirements mapping

This is the most important part — every requirement from the problem statement has a corresponding implementation:

| NTRO Requirement | What I Built |
|---|---|
| SAR change detection between co-registered images | Sentinel-1 GRD backscatter time series + NDVI change detection |
| Filter out natural changes (floods, vegetation, snow) | Seismic filter, soil preservation, water table, OSM context |
| Detect man-made changes only | 7-component weighted fusion with environmental modifiers |
| User-adjustable thresholds | Configurable in config.py + UI controls |
| Polygon output (GeoJSON/Shapefile) | `/api/export/json` returns GeoJSON with polygons |
| Scalable for large areas | Async FastAPI + parallel fetches + GEE backend |
| GUI for area specification | Leaflet map with click-to-scan, radius, date range |
| Runs on Google Earth Engine | GEE integration with demo fallback |

---

## Data sources (24 free APIs)

I'm pulling from 24 different free/public APIs. Here's what each one does:

### SAR & Satellite
- **Sentinel-1 SAR** (10m) — radar backscatter, the core signal for PS1563
- **Sentinel-2** (10m) — optical, vegetation stress, crop marks
- **Landsat 8** (30m) — thermal, surface temperature anomalies

### Environmental (the false positive filter)
- **ISRIC SoilGrids** — clay/sand/silt/pH at 250m
- **USGS Earthquakes** — seismic activity nearby
- **NOAA WMM** — magnetic field intensity (nT)
- **NASA POWER** — solar radiation baseline
- **Open-Elevation** — SRTM 30m terrain
- **Open-Meteo** — historical weather
- **ESA WorldCover** — land use at 10m
- **WorldPop** — population density

### Archaeological & Cultural
- **Wikidata (Pleiades)** — ancient sites, temples
- **GBIF** — species occurrences
- **Wayback Machine** — prior research
- **OpenStreetMap** — historic buildings & heritage
- **NASA VIIRS** — nighttime lights
- **Macrostrat** — geological formations

All of these are free. No paid APIs.

---

## The dashboard

9 tabs in a dark terminal-themed UI:

| Tab | What's in it |
|---|---|
| **Map** | Leaflet dark tiles, click-to-scan, place search, configurable satellite source/radius/date, export |
| **Analysis** | Fused score (0-100%), NDVI/thermal charts, anomaly detection with "Explain" buttons, structural analysis |
| **Environment** | Soil data, geological context, water proximity, lightning, space weather |
| **Intelligence** | NDVI change detection between two periods, elevation profiles, nearby places |
| **Archives** | Wayback Machine, OSM historic, archaeological databases, suitability scoring |
| **Terrain** | 3D elevation model (SRTM 30m) with wireframe overlay and anomaly markers |
| **Signals** | Magnetic gradient, SAR backscatter, solar radiation, FFT analysis, EM field heatmap |
| **AI Analyst** | Full scan interpretation, anomaly explanations (3 hypotheses), investigation plan, chat |
| **History** | Scan history (200 scans), compare scans, batch scan + rank by suitability |

---

## API endpoints

70+ endpoints. Here are the important ones:

### Core (directly solves PS1563)
```
GET  /api/mega-scan              Full spectrum (15 parallel sources)
GET  /api/sar/backscatter        Sentinel-1 VV/VH time series
GET  /api/site/ndvi-change       Vegetation change between periods
POST /api/satellite/anomalies    Anomaly detection + classification
GET  /api/export/json            GeoJSON export with polygons
```

### Environmental & Archaeological
```
GET  /api/env/soil               ISRIC SoilGrids
GET  /api/env/faults             USGS earthquake data
GET  /api/arch/pleiades          Ancient sites (Wikidata SPARQL)
GET  /api/arch/crossref          Cross-reference all databases
POST /api/arch/batch             Batch scan + rank locations
```

### AI
```
POST /api/gemini/analyze         Full AI interpretation
POST /api/gemini/explain-anomaly 3 ranked hypotheses per anomaly
POST /api/gemini/chat            Conversational AI with scan context
GET  /api/llm/status             Provider/model status
```

Full interactive docs at **http://localhost:8500/docs** (auto-generated by FastAPI)

---

## Tech stack

```
Backend:   Python 3.9+, FastAPI, NumPy, SciPy
Frontend:  Leaflet, Plotly.js, Three.js, GSAP
AI:        Cerebras GOPT-120B (or OpenRouter/Groq/Gemini)
SAR:       Google Earth Engine (Sentinel-1 GRD)
Data:      24 free public APIs, zero paid dependencies
```

---

## Architecture

```
Frontend (HTML/JS/CSS — dark terminal aesthetic)
    │
    │ 70+ HTTP endpoints + WebSocket
    ▼
FastAPI Server (backend/api/main.py — 1,294 lines)
    │
    ├── SatelliteEngine ──── Google Earth Engine (Sentinel-1/2, Landsat 8)
    ├── AIReconstructor ◄── scipy/numpy (the brain)
    │       └── fuse_all_data() ← 7-component weighted fusion
    ├── DataIngestion ───── NOAA, NASA POWER, Open-Elevation, OSM
    ├── EnvironmentalData ─ ISRIC SoilGrids, USGS Earthquakes, WorldPop
    ├── ArchaeologicalDB ── Wikidata SPARQL, GBIF, NOAA WMM, VIIRS
    ├── HistoricalWeb ───── Internet Archive CDX, OSM Overpass
    ├── SignalProcessor ─── scipy FFT, spectrogram, interpolation
    └── GeminiAnalyzer ──── Multi-provider LLM (Cerebras/Groq/OpenRouter/Gemini)
```

8 backend modules, each handling a specific pipeline stage. The main.py file (1,294 lines) wires everything together with 70+ FastAPI routes.

---

## Code breakdown

| What | Lines | Where |
|---|---|---|
| Backend (all modules) | 5,371 | `backend/` |
| Frontend JS | 1,496 | `frontend/js/app.js` |
| Frontend CSS | 1,323 | `frontend/css/style.css` |
| Frontend HTML | 749 | `frontend/index.html` |
| Tests | 170 | `tests/test_api.py` |
| Notebooks | 438 | `notebooks/` |
| **Total** | **9,547** | |

---

## Getting started

```bash
git clone https://github.com/subhansh-dev/chronovisor.git
cd chronovisor
pip install -e .
cp .env.example .env  # add CEREBRAS_API_KEY (free tier available)
python run.py
# → http://localhost:8500
```

**Demo mode:** All 70+ endpoints work without GEE authentication. I built a synthetic satellite data generator that produces realistic timeseries with seasonal patterns. This means the demo never fails — no API keys needed for the demo.

**Production with real satellite data (GEE):**

The service account key is at `backend/credentials/gee-service-account.json`. For local use, it's already configured in `.env`.

For Render deployment:
1. Go to Render Dashboard → Your Service → Environment
2. Add env var `GOOGLE_APPLICATION_CONTENTS` with the full JSON content of the service account key
3. The app auto-detects this and authenticates with GEE on startup

```bash
pip install -r requirements.txt
uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
```

First request after idle: ~30-50s wake-up. After that: fast.

---

## What makes this different from most SIH submissions

Most teams solving this problem submit a Jupyter notebook with Sentinel-1 differencing. That gives you a change map with 40%+ false alarms.

This is a full-stack web application that:
1. Pulls from 24 sources instead of 1
2. Fuses them with a weighted scoring engine
3. Has a GUI that non-technical users can actually use
4. Exports GeoJSON (the format NTRO asked for)
5. Has AI interpretation on top of the ML analysis
6. Works offline in demo mode

The key insight: you can't solve the false alarm problem with SAR alone. You need environmental context to filter out natural changes.

---

## License

MIT

---

<p align="center">
  <sub>Built for Smart India Hackathon 2025 — NTRO PS1563</sub><br>
  <sub>Multi-source satellite intelligence. Zero false alarm compromise.</sub>
</p>
