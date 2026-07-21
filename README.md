<p align="center">
  <br>
  <img src="https://img.shields.io/badge/version-0.4.0-blue?style=for-the-badge" alt="version">
  <img src="https://img.shields.io/badge/python-3.9+-green?style=for-the-badge" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=for-the-badge" alt="license">
  <img src="https://img.shields.io/badge/API-60+-endpoints-orange?style=for-the-badge" alt="endpoints">
  <img src="https://img.shields.io/badge/AI-Gemini_2.5-purple?style=for-the-badge" alt="ai">
  <img src="https://img.shields.io/badge/data-24_sources-red?style=for-the-badge" alt="sources">
  <br><br>
</p>

```
CHRONOVISOR v0.4.0
Temporal Archaeology Engine
```

<h3 align="center">What's buried beneath your feet?</h3>
<p align="center">
  Drop a pin on a map. Chronovisor pulls satellite imagery, soil data,<br>
  seismic readings, magnetic anomalies, and AI analysis to tell you<br>
  what might be hiding underground. No digging required.
</p>

---

## So what is this thing?

You know how you can look at a star and you're literally seeing light from millions of years ago? Same idea, but for the ground we walk on.

Satellites have been photographing Earth for decades. Soil sensors measure what's underground. Magnetic field data reveals buried structures. Web archives hold old maps and records. And now AI can connect those dots better than most humans can.

Chronovisor pulls all of that together. Give it coordinates — or just type "Angkor Wat" — and it runs 24 data sources in parallel, scores what it finds, and lets you chat with an AI about the results.

It's not magic. It's remote sensing + public data + AI. But it feels like it.

---

## Getting started

```bash
git clone https://github.com/subhansh-dev/chronovisor.git
cd chronovisor
pip install -e .
```

Set up your API key (free):

```bash
cp .env.example .env
# Get one at https://aistudio.google.com/apikey
```

```bash
chrono
```

Opens at **http://localhost:8500**. That's it.

---

## What it actually does

**24 data sources** all hitting free public APIs:

**Satellite stuff:**
| Source | What you get |
|---|---|
| Sentinel-2 | 10m optical imagery (2017+) |
| Landsat 8 | Thermal + optical (2013+) |
| Sentinel-1 SAR | Radar that sees through clouds (2014+) |

**Environmental data:**
| Source | What you get |
|---|---|
| ISRIC SoilGrids | Clay/sand/silt/pH at 250m |
| USGS Earthquakes | Seismic activity nearby |
| NOAA WMM | Magnetic field intensity |
| NASA VIIRS | Nighttime lights (settlement patterns) |
| WorldPop | Population density over time |
| NASA POWER | Solar radiation data |
| Open-Elevation | SRTM 30m terrain elevation |
| Open-Meteo | Historical temperature & rain |
| ESA WorldCover | Land use at 10m resolution |

**Archaeological databases:**
| Source | What you get |
|---|---|
| Wikidata (Pleiades) | Ancient places, temples, castles |
| Wikidata (Archaeological) | Known dig sites |
| GBIF | Species occurrences nearby |
| Nominatim | Place name search |

**Web archives:**
| Source | What you get |
|---|---|
| Wayback Machine | Old web pages about the area |
| OpenStreetMap | Historic buildings & features |
| Historical Maps | Links to old map overlays |

---

## The AI part

Powered by Gemini 2.5. It can:

- **Analyze a full scan** — interprets all 24 data sources together
- **Generate reports** — formal archaeological field reports
- **Explain anomalies** — gives you 3 ranked hypotheses for anything weird
- **Historical context** — civilization timeline for any coordinates
- **Plan investigations** — equipment, costs, permits, timeline
- **Compare sites** — find patterns across multiple locations
- **Chat** — ask it anything about what it found, it remembers your scan data

---

## The dashboard

6 tabs, dark theme, fully interactive:

- **Map** — Search by place name or coordinates. Leaflet with reverse geocoding.
- **Analysis** — Fused archaeological score, anomaly breakdown, soil data, water proximity, geology, elevation profiles, NDVI change detection.
- **Terrain** — 3D elevation model from SRTM data. Rotate it, zoom in, see the landscape.
- **Signals** — Magnetic field profile, SAR backscatter time series, solar radiation charts.
- **AI Analyst** — Chat with Gemini about your findings. Full scan context attached.
- **History** — Every scan you've ever run. Click to revisit.

---

## The scoring engine

It doesn't just dump data — it scores each location:

| Component | Weight | What it measures |
|---|---|---|
| Satellite anomalies | 35% | NDVI/thermal/moisture patterns |
| Soil preservation | 20% | Clay content, pH, organic carbon |
| Seismic filter | 10% | Geological false positive penalty |
| Water table | 10% | Thermal signal interpretation |
| OSM historical | 10% | Existing features confirm patterns |
| Temporal consistency | 10% | Anomalies that persist over time |
| Web archive evidence | 5% | Prior research confirmation |

---

## Running it on the cloud

**Render (free tier):**
1. Push to GitHub
2. render.com → New Web Service → Connect repo
3. Build: `pip install -r requirements.txt`
4. Start: `cd backend && uvicorn api.main:app --host 0.0.0.0 --port $PORT`
5. Add env vars: `GEMINI_API_KEY`, `GEMINI_MODEL`
6. Deploy

First request after idle takes ~30-50 seconds to wake up. After that it's fast.

---

## API (60+ endpoints)

Full interactive docs at **/docs** when running locally.

```
GET  /api/full-scan          Satellite + environmental scan
GET  /api/mega-scan          Everything at once
POST /api/gemini/analyze     AI interpretation
POST /api/gemini/report      Field report generation
GET  /api/gemini/history     Civilization timeline
POST /api/gemini/chat        Conversational AI
GET  /api/site/ndvi-change   Vegetation change detection
GET  /api/site/elevation     Cross-section profiles
GET  /api/site/water         Water source proximity
GET  /api/site/geology       Bedrock & lithology
GET  /api/arch/full          All archaeological databases
GET  /api/env/full           All environmental data
GET  /api/export/report      HTML report
GET  /api/export/json        Full scan as JSON
GET  /api/export/csv         Summary as CSV
```

---

## Tech stack

```
Backend:   Python 3.9+, FastAPI, NumPy, SciPy
Frontend:  Leaflet, Plotly, Three.js, GSAP
AI:        Google Gemini 2.5
Data:      24 free public APIs
```

---

## The backstory

The "Chronovisor" was supposedly built by Father Pellegrino Ernetti, a Vatican monk, who claimed it could view past events through electromagnetic echoes. It was debunked — the photos matched existing church statues, and the design looked like a 1947 sci-fi novel.

But the science behind it? That's real:

- Starlight is literally seeing the past
- Satellite archaeology has found lost cities in the Amazon and Cambodia
- MIT's Visual Microphone recovered sounds from a video of a plant
- The Cosmic Microwave Background is a 380,000-year-old signal

This project takes that real science and makes it accessible. No pseudoscience. Just data, sensors, and AI.

---

## Contributing

```bash
git clone https://github.com/subhansh-dev/chronovisor.git
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
  <sub>Built with satellite data, public APIs, and a lot of curiosity about what's buried beneath our feet.</sub>
</p>
