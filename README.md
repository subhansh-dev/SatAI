<p align="center">
  <br>
  <img src="https://img.shields.io/badge/version-0.4.0-blue?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/python-3.9+-green?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/API-60+_endpoints-orange?style=flat-square" alt="endpoints">
  <img src="https://img.shields.io/badge/AI-Gemini_2.5-purple?style=flat-square" alt="ai">
  <img src="https://img.shields.io/badge/data_sources-24-red?style=flat-square" alt="sources">
  <img src="https://img.shields.io/badge/tabs-6-teal?style=flat-square" alt="tabs">
  <br><br>
</p>

```
CHRONOVISOR v0.4.0
Temporal Archaeology Engine
```

<h3 align="center">Temporal Archaeology Engine</h3>
<p align="center">
<strong>Give it GPS coordinates. It tells you what is buried beneath.</strong><br>
AI-powered archaeological analysis using 24 data sources,<br>
satellite imagery, environmental sensors, web archives, and Google Gemini 2.5.
</p>

<p align="center">
  <img src="map.png" alt="Chronovisor Dashboard" width="100%">
</p>

---

## What Is This?

Chronovisor is a scientific reinterpretation of the alleged Vatican Chronovisor device. A machine claimed to view past events by capturing electromagnetic echoes. While the original was pseudoscience, the underlying idea has real scientific grounding:

- **Light from distant stars** is literally seeing the past
- **Satellite imagery** lets us see how landscapes changed over decades
- **Electromagnetic anomalies** in soil reveal buried structures
- **AI** can interpret patterns humans miss

No hardware needed. No pseudoscience. Just remote sensing, public data APIs, and AI.

---

## Quick Start

```bash
git clone https://github.com/chronovisor/chronovisor.git
cd chronovisor
pip install -e .
```

Set your Gemini API key:

```bash
cp .env.example .env
# Edit .env and add GEMINI_API_KEY
# Free key: https://aistudio.google.com/apikey
```

```bash
chrono
```

Opens **http://localhost:8500** automatically.

---

## Features

### 24 Data Sources

> **Note:** Satellite imagery data (Sentinel-2, Landsat 8, Sentinel-1 SAR) is only available from **2013 onwards**. Sentinel-2 starts March 2017, Landsat 8 starts March 2013, Sentinel-1 starts October 2014. Selecting dates before 2013 will auto-clamp to 2013 and show a notice. Environmental, archaeological, and web archive data are not affected by date selection.

**Satellite Imagery:**

| Source | What It Provides | Coverage |
|---|---|---|
| **Sentinel-2** | 10m multispectral optical imagery | 2017-present |
| **Landsat 8** | 30m thermal + optical imagery | 2013-present |
| **Sentinel-1 SAR** | 10m radar, sees through clouds | 2014-present |

**Environmental Data:**

| Source | What It Provides | API |
|---|---|---|
| **ISRIC SoilGrids** | Clay/sand/silt/OC/pH at 250m, 6 depths | REST API (free) |
| **USGS Earthquakes** | Seismic activity + fault detection | FDSNWS API (free) |
| **NOAA WMM/IGRF** | Magnetic field intensity, declination, inclination | REST API (free) |
| **NASA VIIRS** | Nighttime lights (settlement patterns) | CMR API (free) |
| **WorldPop** | Population density over time | REST API (free) |
| **NOAA Space Weather** | Solar wind + geomagnetic indices | SWPC API (free) |
| **NASA POWER** | Solar radiation + atmospheric data | LARC API (free) |
| **Open-Elevation** | SRTM 30m terrain elevation | REST API (free) |
| **OpenTopography** | High-res DEM / LIDAR availability | REST API (free) |
| **Open-Meteo** | Climate: temperature, precipitation, humidity | Historical Weather API (free) |
| **ESA WorldCover** | Land use / land cover at 10m resolution | Terrascope API (free) |

**Archaeological Databases:**

| Source | What It Provides | API |
|---|---|---|
| **Wikidata (Pleiades)** | Ancient places, monuments, castles, temples | SPARQL (free) |
| **Wikidata (Archaeological)** | Known archaeological sites with coordinates | SPARQL (free) |
| **GBIF** | Species occurrences (environmental proxy) | REST API (free) |
| **Nominatim** | Geocoding — place name to coordinates | OSM Nominatim (free) |

**Web Archives:**

| Source | What It Provides | API |
|---|---|---|
| **Wayback Machine** | Archived web pages + historical records | CDX API (free) |
| **OpenStreetMap** | Building history + historic features | Overpass API (free) |
| **Historical Maps** | Old Maps Online, USGS Topos, NASA Worldview | Direct links |

**Computed / Derived:**

| Source | What It Provides | Method |
|---|---|---|
| **AI Fusion Engine** | 7-component weighted archaeological score | Internal computation |
| **Site Suitability** | Multi-factor investigation priority score | Internal computation |
| **Cross-Reference** | Multi-database confidence scoring | Internal computation |

### 7 AI Capabilities (Gemini 2.5)

| Capability | What It Does | Endpoint |
|---|---|---|
| **Scan Analysis** | Expert interpretation of all data combined | `POST /api/gemini/analyze` |
| **Report Generation** | Formal archaeological field reports | `POST /api/gemini/report` |
| **Anomaly Explanation** | 3 ranked hypotheses per anomaly | `POST /api/gemini/explain-anomaly` |
| **Historical Context** | Timeline of civilizations at any location | `GET /api/gemini/history` |
| **Investigation Planning** | Equipment, costs, permits, timeline | `POST /api/gemini/investigate` |
| **Location Comparison** | Cross-site pattern analysis | `POST /api/gemini/compare` |
| **Conversational AI** | Chat about findings with scan context | `POST /api/gemini/chat` |

### AI Fusion Engine

Weighted scoring system combining all data sources:

| Component | Weight | Measures |
|---|---|---|
| Satellite Anomalies | 35% | NDVI/thermal/moisture patterns |
| Soil Preservation | 20% | Clay content, pH, organic carbon |
| Seismic Filter | 10% | Geological false positive penalty |
| Water Table | 10% | Thermal signal interpretation |
| OSM Historical | 10% | Confirmation from existing features |
| Temporal Consistency | 10% | Persistent anomalies over time |
| Web Archive Evidence | 5% | Prior research confirmation |

---

## Dashboard

6-tab interface with glass morphism dark theme:

- **Map** -- Interactive Leaflet map with place name search, coordinate display, scale bar, reverse geocoding. Type "Angkor Wat" and hit Enter.
- **Analysis** -- Fused score, site suitability, component breakdown, anomalies, structural analysis, environmental data, web archives, archaeological databases. Includes **Site Intelligence** section with NDVI change detection, elevation cross-section, water proximity, geological context, and nearby places.
- **Terrain** -- 3D elevation model in Three.js from SRTM data with wireframe overlay, anomaly markers.
- **Signals** -- Magnetic field profile (NOAA WMM, real data), SAR backscatter time series (Sentinel-1, real data), solar radiation from NASA POWER.
- **AI Analyst** -- Gemini chat with full scan context (satellite data, anomalies, soil, water table, magnetic field), AI analysis, report generation, historical context, investigation planning.
- **History** -- Browse all past scans, click to view details, persistent across restarts.

---

## CLI

```bash
chrono                        # Start on port 8500, auto-open browser
chrono --port 3000            # Custom port
chrono --no-browser           # Do not auto-open
chrono --check                # Verify dependencies
```

---

## API (52+ endpoints)

Full interactive docs at **http://localhost:8500/docs**

### Satellite & Analysis
```
GET  /api/full-scan?lat=&lon=&radius_m=&start_date=
GET  /api/mega-scan?lat=&lon=&radius_m=&start_date=&place_name=
POST /api/satellite/timeseries
POST /api/satellite/anomalies
POST /api/satellite/spectral
GET  /api/sar/backscatter?lat=&lon=   Sentinel-1 SAR time series
POST /api/signal/analyze              (demo mode if no data)
POST /api/signal/em-field             (demo mode if no data)
GET  /api/signal/magnetic-gradient    NOAA WMM magnetic profile
POST /api/ai/temporal-change
POST /api/ai/terrain?lat=&lon=&grid_size=
```

### Site Intelligence
```
GET  /api/site/ndvi-change?lat=&lon=  NDVI before/after comparison
GET  /api/site/elevation-profile      Elevation cross-section (E-W/N-S/etc)
GET  /api/site/water?lat=&lon=        Water sources via OSM Overpass
GET  /api/site/geology?lat=&lon=      Bedrock from Macrostrat + SoilGrids
GET  /api/site/places?lat=&lon=       Nearby settlements via OSM Overpass
```

### Gemini AI
```
POST /api/gemini/analyze              Scan + Gemini interpretation
POST /api/gemini/report               Formal archaeological report
POST /api/gemini/explain-anomaly      3 hypotheses per anomaly
GET  /api/gemini/history?lat=&lon=    Historical timeline
POST /api/gemini/compare              Multi-site comparison
POST /api/gemini/chat                 Conversational AI
POST /api/gemini/investigate          Investigation plan
```

### Environmental Data
```
GET  /api/env/soil?lat=&lon=&depth=   ISRIC SoilGrids
GET  /api/env/faults?lat=&lon=        USGS earthquakes
GET  /api/env/population?lat=&lon=    WorldPop
GET  /api/env/water-table?lat=&lon=   Elevation-based estimate
GET  /api/env/full?lat=&lon=          All environmental in parallel
```

### Archaeological Databases
```
GET  /api/arch/pleiades?lat=&lon=     Ancient places (Wikidata)
GET  /api/arch/wikidata?lat=&lon=     Archaeological sites (Wikidata)
GET  /api/arch/gbif?lat=&lon=         Species occurrences
GET  /api/arch/magnetic?lat=&lon=     NOAA WMM magnetic field
GET  /api/arch/nightlights?lat=&lon=  NASA VIIRS nighttime lights
GET  /api/arch/lidar?lat=&lon=        OpenTopography DEM
GET  /api/arch/climate?lat=&lon=      Open-Meteo historical weather
GET  /api/arch/landcover?lat=&lon=    ESA WorldCover land use
GET  /api/arch/suitability?lat=&lon=  Site suitability scoring
GET  /api/arch/crossref?lat=&lon=     Multi-database cross-reference
GET  /api/arch/temporal?lat=&lon=     Temperature trend analysis
GET  /api/arch/full?lat=&lon=         All archaeological in parallel
POST /api/arch/batch                  Batch scan multiple locations
```

### Web Archives
```
GET  /api/web/wayback?lat=&lon=       Wayback Machine
GET  /api/web/osm?lat=&lon=           OpenStreetMap features
GET  /api/web/full?lat=&lon=          All web archives in parallel
```

### Search
```
GET  /api/geocode?q=                  Place name to coordinates
```

### Data Sources
```
GET  /api/data/space-weather          NOAA solar wind + Kp index
GET  /api/data/lightning              Lightning (guidance)
GET  /api/data/historical-maps        Map source links
GET  /api/data/radio-astronomy        NASA POWER solar radiation
```

### Export
```
GET  /api/export/report?lat=&lon=     HTML report (print-ready)
GET  /api/export/json?lat=&lon=       Full scan as JSON
GET  /api/export/csv?lat=&lon=        Scan summary as CSV
```

### System
```
GET  /api/health                      Engine status + version
GET  /api/history                     All scan history
GET  /api/history/{index}             Specific scan result
GET  /api/compare?indices=0,1,2       Compare scans from history
WS   /ws                              WebSocket for real-time chat
```

---

## Architecture

```
Frontend (6 tabs: Map, Analysis, Terrain, Signals, AI Analyst, History)
  |
FastAPI Server (52+ endpoints, WebSocket, rate limiting, CORS)
  |
  +-- Satellite Engine (Earth Engine: Sentinel-2, Landsat 8, Sentinel-1 SAR)
  +-- Signal Processor (FFT, pattern detection, EM field mapping)
  +-- AI Reconstructor (structural analysis + 7-component fusion engine)
  +-- Gemini Analyzer (7 AI capabilities via Google Gemini 2.5)
  +-- Environmental Data (SoilGrids, USGS, WorldPop, water table)
  +-- Historical Web (Wayback Machine, OpenStreetMap)
  +-- Archaeological DB (Wikidata, GBIF, VIIRS, WMM, OpenTopography, climate, land cover)
  |
External APIs (24 sources, all free)
  |
AI Fusion Engine (7-component weighted scoring)
  +-- Site Suitability Engine (multi-factor investigation priority)
  +-- Cross-Reference Engine (multi-database confidence scoring)
  +-- Retry Logic (2 attempts with 1s delay)
  +-- Persistent History (JSON file, survives restarts)
```

---

## Project Structure

```
chronovisor/
├── backend/
│   ├── cli.py                    # CLI entry point (chrono command)
│   ├── api/main.py               # FastAPI server, 52+ endpoints
│   ├── core/config.py            # Configuration, .env loader
│   ├── core/cache.py             # Two-tier cache (memory + disk)
│   └── pipeline/
│       ├── satellite_engine.py   # Google Earth Engine
│       ├── data_ingestion.py     # NOAA, NASA, elevation
│       ├── signal_processor.py   # FFT, patterns, EM field
│       ├── ai_reconstructor.py   # Structural + fusion engine
│       ├── gemini_analyzer.py    # Gemini 2.5 AI
│       ├── environmental_data.py # SoilGrids, USGS, WorldPop
│       ├── historical_web.py     # Wayback Machine, OSM
│       └── archaeological_db.py  # Wikidata, GBIF, VIIRS, climate
├── frontend/
│   ├── index.html                # Dashboard (6 tabs)
│   ├── js/app.js                 # Frontend logic
│   └── css/style.css             # Glass morphism theme
├── data/scan_history.json        # Persistent scan history
├── pyproject.toml                # Package config
├── requirements.txt              # Dependencies
├── .env.example                  # Environment template
└── run.py                        # Entry point
```

---

## Background

The Chronovisor was allegedly invented by **Father Pellegrino Ernetti**, a Benedictine monk at the Vatican. He claimed it could view past events. The device was debunked (the crucifixion photo matched a church statue, the design resembled a 1947 sci-fi novella).

**What is scientifically valid:**
- Starlight = seeing the past
- Cosmic Microwave Background = 380,000-year-old signal
- MIT Visual Microphone (2014) recovered sounds from video
- Satellite archaeology discovered lost cities in Amazon, Cambodia

**This project:** Satellite imagery + public APIs + AI. No pseudoscience.

---

## Production Features

- **Rate limiting** — 30 requests/minute per IP, 429 responses
- **Persistent history** — Scans saved to `data/scan_history.json`, survive restarts
- **Retry logic** — Failed API calls retry once with 1s delay
- **Error isolation** — One failed data source doesn't crash the scan
- **Global exception handler** — Consistent JSON error responses
- **CORS enabled** — Works from any frontend origin
- **Async parallel execution** — Mega scan runs 14 API calls simultaneously
- **Cache layer** — In-memory + disk cache with configurable TTL
- **Export formats** — HTML report, JSON, CSV
- **Place name search** — Geocoding via OpenStreetMap Nominatim

## Requirements

- Python 3.9+
- Gemini API key (free at https://aistudio.google.com/apikey)
- Internet connection (for satellite and environmental APIs)
- 4GB RAM minimum (heavy processing runs on Google's servers)

---

## Development History

**Batch 1** — Core archaeological databases: Pleiades, Wikidata, GBIF, NOAA WMM, NASA VIIRS, OpenTopography

**Batch 2** — Environmental enrichment: Open-Meteo climate data, ESA WorldCover land cover

**Batch 3** — Intelligence layer: Site suitability scoring, IGRF magnetic model, multi-factor analysis

**Batch 4** — User experience: Geocoding (place name search), database cross-reference, temporal change detection

**Batch 5** — Data management: Batch scanning, JSON/CSV export, suitability in dashboard summary

**Batch 6** — Production hardening: Persistent history, retry logic, rate limiting, error handling, history UI, comparison tool

## Contributing

```bash
git clone https://github.com/chronovisor/chronovisor.git
cd chronovisor
pip install -e ".[dev]"
pytest tests/
chrono
```

---

## License

MIT

---

<p align="center">
  <sub>Built with satellite data, public APIs, and curiosity about what is buried beneath our feet.</sub>
</p>
