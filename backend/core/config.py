"""
CHRONOVISOR — Core Configuration
"""
import os
from pathlib import Path

# Load .env file if present
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SATELLITE_DIR = DATA_DIR / "satellite"
SIGNALS_DIR = DATA_DIR / "signals"
MAPS_DIR = DATA_DIR / "maps"

# Create dirs
for d in [SATELLITE_DIR, SIGNALS_DIR, MAPS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Google Earth Engine
GEE_PROJECT_ID = os.getenv("GEE_PROJECT_ID", "")

# API
API_HOST = os.getenv("CHRONOVISOR_HOST", "0.0.0.0")
API_PORT = int(os.getenv("CHRONOVISOR_PORT", "8500"))

# Satellite data sources
SATELLITE_SOURCES = {
    "sentinel2": {
        "name": "Sentinel-2",
        "collection": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": ["B2", "B3", "B4", "B8", "B11", "B12"],
        "resolution": 10,  # meters
        "start_date": "2017-03-28",
        "description": "Multispectral optical imagery, 10m resolution"
    },
    "landsat8": {
        "name": "Landsat 8",
        "collection": "LANDSAT/LC08/C02/T1_L2",
        "bands": ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"],
        "resolution": 30,
        "start_date": "2013-03-18",
        "description": "Thermal + optical, good for vegetation stress detection"
    },
    "sentinel1": {
        "name": "Sentinel-1 SAR",
        "collection": "COPERNICUS/S1_GRD",
        "bands": ["VV", "VH"],
        "resolution": 10,
        "start_date": "2014-10-03",
        "description": "Radar — sees through clouds, detects subsurface features"
    }
}

# Anomaly detection thresholds
ANOMALY_CONFIG = {
    "ndvi_threshold": 0.15,       # vegetation anomaly
    "moisture_threshold": 0.1,    # soil moisture anomaly
    "thermal_threshold": 2.0,     # degrees C deviation
    "min_cluster_size": 5,        # minimum pixels for anomaly
}

# Signal processing
SIGNAL_CONFIG = {
    "sample_rate": 44100,
    "fft_size": 4096,
    "freq_range": (20, 20000),    # Hz
    "overlap": 0.5,
}
