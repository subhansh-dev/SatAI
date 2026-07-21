# %% [markdown]
# # CHRONOVISOR — Satellite Archaeology Demo
# 
# This notebook demonstrates the satellite analysis pipeline:
# 1. Query real Sentinel-2 imagery from Google Earth Engine
# 2. Compute NDVI/moisture/thermal indices
# 3. Run anomaly detection for buried structures
# 4. Visualize temporal changes

# %%
import sys
sys.path.insert(0, '..')

import numpy as np
import matplotlib.pyplot as plt
from pipeline.satellite_engine import SatelliteEngine
from pipeline.ai_reconstructor import AIReconstructor

# Initialize Earth Engine
sat = SatelliteEngine()
sat.initialize()

ai = AIReconstructor()
ai.load_models()

# %% [markdown]
# ## Query Satellite Data
# 
# Pull NDVI, moisture, and thermal time series for a location.
# Using Delhi, India as example.

# %%
lat, lon = 28.6139, 77.2090
result = sat.get_satellite_timeseries(lat, lon, radius_m=500, start_date="2024-01-01")

print(f"Source: {result['source']}")
print(f"Data points: {result['count']}")

ts = result['timeseries']
dates = [t['date'] for t in ts]
ndvi = [t['ndvi'] for t in ts]
moisture = [t['moisture'] for t in ts]
thermal = [t['thermal'] for t in ts]

# %% [markdown]
# ## Plot Time Series

# %%
fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)

axes[0].plot(dates, ndvi, 'g-', linewidth=1.5)
axes[0].set_ylabel('NDVI')
axes[0].set_title('Vegetation Index')
axes[0].grid(True, alpha=0.3)

axes[1].plot(dates, moisture, 'b-', linewidth=1.5)
axes[1].set_ylabel('Moisture')
axes[1].set_title('Soil Moisture')
axes[1].grid(True, alpha=0.3)

axes[2].plot(dates, thermal, 'r-', linewidth=1.5)
axes[2].set_ylabel('Thermal (°C)')
axes[2].set_title('Surface Temperature')
axes[2].grid(True, alpha=0.3)

plt.tight_layout()
plt.xticks(rotation=45)
plt.show()

# %% [markdown]
# ## Anomaly Detection
# 
# Find vegetation stress and thermal anomalies that indicate buried structures.

# %%
anomalies = sat.detect_anomalies(ts)
print(f"Anomalies found: {len(anomalies)}")

for a in anomalies:
    print(f"  {a['type']} on {a['date']}: {a['value']:.4f} (mean={a['mean']}, dev={a['deviation']}σ)")

# %% [markdown]
# ## Structural Analysis
# 
# Use AI to detect buried structures from NDVI-thermal correlation.

# %%
structural = ai.detect_buried_structures(ndvi, thermal, dates)
print(f"Structural probability: {structural['structural_probability']}%")
print(f"NDVI-thermal correlation: {structural['ndvi_thermal_correlation']}")
print(f"Confidence: {structural['confidence']}")
for interp in structural['interpretation']:
    print(f"  - {interp}")

# %% [markdown]
# ## Spectral Indices
# 
# Compute NDVI, NDWI, NDBI for the latest imagery.

# %%
spectral = sat.compute_spectral_indices(lat, lon)
print(f"NDVI: {spectral['NDVI']}")
print(f"NDWI: {spectral['NDWI']}")
print(f"NDBI: {spectral['NDBI']}")
for interp in spectral['interpretation']:
    print(f"  - {interp}")
