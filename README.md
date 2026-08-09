<p align="center">
  <br>
  <img src="https://img.shields.io/badge/SIH-2025-blue?style=for-the-badge" alt="sih">
  <img src="https://img.shields.io/badge/PS-SIH1563--NTRO-red?style=for-the-badge" alt="ps">
  <img src="https://img.shields.io/badge/version-0.5.0-green?style=for-the-badge" alt="version">
  <img src="https://img.shields.io/badge/API-70%2B-orange?style=for-the-badge" alt="endpoints">
  <img src="https://img.shields.io/badge/AI-Cerebras--120B-purple?style=for-the-badge" alt="ai">
  <img src="https://img.shields.io/badge/data-24--sources-yellow?style=for-the-badge" alt="sources">
  <br><br>
</p>

```
CHRONOVISOR v0.5.0
Multi-Source Satellite Intelligence Platform
for Change Detection & Anomaly Analysis
```

<h3 align="center">Problem Statement: Automatic Change Detection in Synthetic Aperture Radar (SAR) Satellite Images</h3>
<p align="center">
  <b>Ministry: National Technical Research Organisation (NTRO)</b><br>
  PS ID: SIH1563 &nbsp;|&nbsp; Category: Software &nbsp;|&nbsp; Theme: Space Technology
</p>
<p align="center">
  Drop a pin on a map. Chronovisor fuses SAR backscatter, optical NDVI,<br>
  thermal anomalies, magnetic field data, soil preservation, seismic filtering,<br>
  and AI analysis to detect man-made changes while suppressing natural false positives.
</p>

---

## The Problem (NTRO PS1563)

> *"Change detection between two SAR images is straightforward if co-registered — the difference or ratio gives the change map. But such maps invariably have many natural changes (water body extent, flood extent, snow cover, forest cover). Our interest is to detect only man-made changes and avoid natural changes."*
>
> — NTRO, Smart India Hackathon 2024/2025

**Existing tools fail because:**
- Single-source SAR = 40%+ false alarms from natural phenomena (floods, vegetation, snow)
- No cross-validation with optical, thermal, or environmental data
- No archaeological/cultural context to distinguish man-made from geological features
- No scalable, deployable, free solution exists for Indian agencies

---

## Our Solution

Chronovisor solves this with **multi-source data fusion** — not just SAR, but 24 independent data sources cross-validated to suppress false positives:

```
                    ┌─────────────────────────────────────┐
                    │     MULTI-SOURCE FUSION ENGINE      │
                    │        (Weighted 7-Layer Scoring)   │
                    └─────────────────────────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
    ┌───────▼───────┐        ┌───────▼───────┐        ┌───────▼───────┐
    │  SAR Change   │        │   Optical     │        │ Environmental │
    │  Detection    │        │   NDVI/Thermal│        │   Context     │
    │               │        │               │        │               │
    │ Sentinel-1    │        │ Sentinel-2    │        │ Soil/Seismic  │
    │ VV/VH ratio   │        │ Vegetation    │        │ Magnetic/Water│
    │ Backscatter   │        │ Stress        │        │ Population    │
    └───────────────┘        └───────────────┘        └───────────────┘
            │                         │                         │
            └─────────────────────────┼─────────────────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │  MAN-MADE vs NATURAL CLASSIFIER   │
                    │  Fused Score: 0-100%              │
                    │  Confidence: Low/Medium/High      │
                    │  GeoJSON export with polygons      │
                    └───────────────────────────────────┘
```

---

## How It Maps to NTRO Requirements

| NTRO Requirement | Chronovisor Implementation | Status |
|---|---|---|
| SAR change detection between co-registered images | Sentinel-1 GRD backscatter time series + NDVI change detection | ✅ Built |
| Filter out natural changes (floods, vegetation, snow) | Seismic filter (10%), soil preservation (20%), water table (10%), OSM context (10%) | ✅ Built |
| Detect man-made changes only | 7-component weighted fusion with environmental modifiers | ✅ Built |
| User-adjustable thresholds | Configurable NDVI/thermal/moisture thresholds in config.py + UI controls | ✅ Built |
| Polygon output (GeoJSON/Shapefile) | `/api/export/json` → GeoJSON with georeferenced anomaly polygons | ✅ Built |
| Scalable for large areas | Async FastAPI + 12-thread parallel fetch + GEE planet-scale backend | ✅ Built |
| GUI for area specification | Leaflet dark-tile map with click-to-scan, radius config, date range | ✅ Built |
| Runs on Google Earth Engine | GEE integration (Sentinel-1/2, Landsat 8) with mock fallback | ✅ Built |

---

## Data Sources (24 Free APIs)

### SAR & Satellite (The Core Signal)
| Source | Resolution | What It Detects | PS Relevance |
|---|---|---|---|
| **Sentinel-1 SAR** | 10m radar | Surface roughness, subsurface features | Primary — PS1563 target |
| **Sentinel-2** | 10m optical | Vegetation stress, crop marks, soil marks | Cross-validation |
| **Landsat 8** | 30m thermal | Surface temperature anomalies | Thermal confirmation |

### Environmental (The False Positive Filter)
| Source | What It Does | How It Reduces False Alarms |
|---|---|---|
| ISRIC SoilGrids | Clay/sand/silt/pH at 250m | Sandy soil = geological anomaly, not man-made |
| USGS Earthquakes | Seismic activity nearby | Active faults create false positives |
| NOAA WMM | Magnetic field intensity (nT) | Buried stone/brick distort local field |
| NASA POWER | Solar radiation (W/m²) | Baseline for thermal anomaly detection |
| Open-Elevation | SRTM 30m terrain | Gradient anomalies from buried structures |
| Open-Meteo | Historical weather | Water table estimation, preservation conditions |
| ESA WorldCover | Land use at 10m | Urban vs forest classification |

### Archaeological & Cultural (The Context Layer)
| Source | What It Provides |
|---|---|
| Wikidata (Pleiades) | Ancient sites, temples, castles |
| GBIF | Species occurrences (land use history proxy) |
| Wayback Machine | Prior research about the area |
| OpenStreetMap | Historic buildings & heritage features |
| NASA VIIRS | Nighttime lights (settlement density) |

---

## The Scoring Engine

**Weighted 7-Layer Fusion** — this is what reduces false alarms:

| Component | Weight | What It Measures | False Alarm Reduction |
|---|---|---|---|
| **Satellite anomalies** | 35% | NDVI/thermal/SAR patterns | Baseline signal |
| **Soil preservation** | 20% | Clay content, pH, organic carbon | Clay preserves man-made structures; sand = natural |
| **Seismic filter** | 10% | Geological false positive penalty | Active faults = geological noise, not man-made |
| **Water table** | 10% | Thermal signal interpretation | Shallow water distorts thermal readings |
| **OSM historical** | 10% | Existing features confirm patterns | Known sites = confirmed man-made |
| **Temporal consistency** | 10% | Anomalies that persist over time | Real structures persist; natural changes don't |
| **Web archive evidence** | 5% | Prior research confirmation | Academic papers = validated sites |

**Modifiers stack on top:**
- High clay content → +score (preserves stone foundations for millennia)
- Active seismic zone → -score (geological anomalies mimic structures)
- Shallow water table → modifies thermal interpretation
- Known archaeological sites nearby → +score
- Dense vegetation → reduces SAR reliability

---

## The Dashboard (6 Tabs)

### Map Tab
- Leaflet dark tiles with click-to-scan
- Place name search with geocoding (Nominatim)
- Configurable: satellite source, radius, date range
- One-click: Full Spectrum Scan, SAR Analysis, AI Analysis, Anomaly Detection
- Export: HTML report, JSON (GeoJSON), CSV

### Analysis Tab
- Fused archaeological potential score (0-100%)
- NDVI time series chart (Plotly)
- Thermal time series chart
- Anomaly detection with "Explain" buttons
- Structural analysis (NDVI-thermal correlation)
- Environmental data (soil, seismic, water table)
- Web archives + OSM historic features
- Archaeological databases (Pleiades, Wikidata, GBIF)
- NDVI change detection between two periods
- Elevation cross-section profiles
- Water proximity analysis

### Terrain Tab
- Three.js 3D elevation model from SRTM 30m
- Wireframe overlay, anomaly markers, orbiting camera

### Signals Tab
- **Magnetic Field** — NOAA WMM gradient profile (buried structures distort local field)
- **SAR Backscatter** — Sentinel-1 VV/VH time series (PS1563 primary)
- **Solar Radiation** — NASA POWER irradiance (thermal baseline)
- **FFT Spectrum Analysis** — frequency pattern detection + AI interpretation
- **EM Field Intensity Map** — 2D heatmap of electromagnetic anomalies

### AI Analyst Tab
- Scan interpretation (reads all 24 sources)
- Anomaly explanation (3 ranked hypotheses)
- Civilization timeline
- Investigation plan (equipment, budget, timeline)
- Chat with full scan context

### History Tab
- Scan history (last 200 scans)
- Compare scans side-by-side
- Batch scan + rank by suitability

---

## API (70+ Endpoints)

### Core (PS1563 Direct)
```
GET  /api/mega-scan              Full spectrum (15 parallel sources)
GET  /api/sar/backscatter        Sentinel-1 VV/VH time series
GET  /api/site/ndvi-change       Vegetation change between periods
POST /api/satellite/anomalies    Anomaly detection
GET  /api/export/json            GeoJSON export with polygons
GET  /api/export/csv             CSV summary
```

### Environmental & Archaeological
```
GET  /api/env/soil               ISRIC SoilGrids
GET  /api/env/faults             USGS earthquakes
GET  /api/env/water-table        Water table estimation
GET  /api/arch/pleiades          Ancient sites
GET  /api/arch/wikidata          Archaeological sites
GET  /api/arch/crossref          Cross-reference all databases
POST /api/arch/batch             Batch scan multiple locations
```

### AI
```
POST /api/gemini/analyze         Full AI interpretation
POST /api/gemini/explain-anomaly 3 hypotheses per anomaly
POST /api/gemini/chat            Conversational AI
POST /api/gemini/investigate     Field investigation plan
POST /api/gemini/synthesize-crossref  Multi-database synthesis
```

Full interactive docs at **http://localhost:8500/docs**

---

## Tech Stack

```
Backend:   Python 3.9+, FastAPI, NumPy, SciPy, scikit-learn
Frontend:  Leaflet, Plotly.js, Three.js, GSAP
AI:        Cerebras GOPT-120B (or OpenRouter/Groq/Gemini)
SAR:       Google Earth Engine (Sentinel-1 GRD)
Data:      24 free public APIs
```

---

## Deployment

**Google Earth Engine (production):**
- Real Sentinel-1 GRD backscatter data
- Real NDVI change detection
- Planet-scale processing

**Mock Mode (demo/offline):**
- Synthetic 36-point time series with realistic patterns
- All 70+ endpoints work without GEE
- Demo runs in 1 command: `python run.py`

**Render (free cloud deploy):**
```bash
pip install -r requirements.txt
uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
```
First request after idle: ~30-50s wake-up. After that: fast.

---

## Architecture

```
Frontend (HTML/JS/CSS — dark terminal aesthetic)
    │
    │ 70+ HTTP endpoints + WebSocket
    ▼
FastAPI Server (backend/api/main.py)
    │
    ├── SatelliteEngine ──── Google Earth Engine (Sentinel-1/2, Landsat 8)
    ├── AIReconstructor ◄── scipy/numpy (the brain)
    │       └── fuse_all_data() ← 7-component weighted fusion
    ├── DataIngestion ───── NOAA, NASA POWER, Open-Elevation, OSM
    ├── EnvironmentalData ─ ISRIC SoilGrids, USGS Earthquakes, WorldPop
    ├── ArchaeologicalDB ── Wikidata SPARQL, GBIF, NOAA WMM, VIIRS
    ├── HistoricalWeb ───── Internet Archive CDX, OSM Overpass
    ├── SignalProcessor ─── scipy FFT, spectrogram, interpolation
    ├── GeminiAnalyzer ──── Multi-provider LLM (Cerebras/Groq/OpenRouter/Gemini)
```

---

## What Makes This Different From SIH 2024 Winners

| | IIT Bombay (HexaSAR) | Alt_24 (Grapevine) | **Chronovisor** |
|---|---|---|---|
| **PS** | SIH1563 SAR Change | SIH1565 Hyperspectral | Both (mapped to SIH1563) |
| **Data sources** | Sentinel-1 only | Hyperion/AVIRIS only | **24 sources** (SAR + optical + thermal + soil + seismic + magnetic + web) |
| **False alarm reduction** | Filtering thresholds | GAN + Autoencoder | **7-component weighted fusion** with environmental modifiers |
| **AI layer** | None specified | Deep learning anomaly | **Dual-layer: ML (local) + LLM (interpretation)** |
| **Output** | Polygons | Spectral signatures | **GeoJSON + HTML report + AI chat + batch scan** |
| **Deployment** | GEE scripts | Jupyter notebook | **Full-stack web app, deployable on Render in 5 min** |
| **Team** | 6 IIT Bombay students | 6 SVCE students | **1 person, 95K lines, 70+ endpoints** |

---

## Getting Started

```bash
git clone https://github.com/subhansh-dev/chronovisor.git
cd chronovisor
pip install -e .
cp .env.example .env  # add CEREBRAS_API_KEY (free)
python run.py
# → http://localhost:8500
```

---

## License

MIT

---

<p align="center">
  <sub>Built for Smart India Hackathon 2025 — NTRO PS1563</sub><br>
  <sub>Multi-source satellite intelligence. Zero false alarm compromise.</sub>
</p>
