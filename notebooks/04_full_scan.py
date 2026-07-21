# %% [markdown]
# # CHRONOVISOR — Full Scan Demo
# 
# Complete Chronovisor scan of a location — runs all engines:
# 1. Satellite time series + anomaly detection
# 2. Structural analysis (AI)
# 3. Temporal change detection
# 4. Spectral indices
# 5. Space weather (NOAA)
# 6. Environmental data (NASA POWER)
# 7. Historical maps

# %%
import sys
sys.path.insert(0, '..')

import numpy as np
import requests
import json

API = "http://localhost:8500"

# %% [markdown]
# ## Run Full Scan
# 
# Scan Mohenjo-daro — one of the earliest urban settlements.

# %%
lat, lon = 27.3242, 68.1375  # Mohenjo-daro
radius = 1000
start_date = "2020-01-01"

print(f"Scanning ({lat}, {lon}) — Mohenjo-daro")
print(f"Radius: {radius}m | From: {start_date}")
print("Running...")

resp = requests.get(f"{API}/api/full-scan", params={
    "lat": lat, "lon": lon, "radius_m": radius, "start_date": start_date
})
scan = resp.json()

# %% [markdown]
# ## Summary

# %%
summary = scan.get('summary', {})
print(f"Archaeological Potential: {summary.get('archaeological_potential', 0)}%")
print(f"Confidence: {summary.get('confidence', 'low')}")
print(f"\nFindings:")
for f in summary.get('findings', []):
    print(f"  - {f}")
print(f"\nRecommendation: {summary.get('recommendation', 'N/A')}")

# %% [markdown]
# ## Satellite Data

# %%
sat = scan.get('satellite', {})
print(f"Source: {sat.get('source', 'unknown')}")
print(f"Data points: {sat.get('data_points', 0)}")
if sat.get('error'):
    print(f"Error: {sat['error']}")

ts = sat.get('timeseries', [])
if ts:
    dates = [t['date'] for t in ts]
    ndvi_vals = [t['ndvi'] for t in ts]
    print(f"NDVI range: {min(ndvi_vals):.4f} - {max(ndvi_vals):.4f}")

# %% [markdown]
# ## Anomalies

# %%
anomalies = scan.get('anomalies', [])
print(f"Anomalies detected: {len(anomalies)}")
for a in anomalies[:10]:
    print(f"  {a['type']} on {a['date']}: dev={a['deviation']}σ — {a['interpretation']}")

# %% [markdown]
# ## Structural Analysis

# %%
struct = scan.get('structural_analysis', {})
if struct.get('error'):
    print(f"Error: {struct['error']}")
else:
    print(f"Structural probability: {struct.get('structural_probability', 0)}%")
    print(f"NDVI-thermal correlation: {struct.get('ndvi_thermal_correlation', 0)}")
    for line in struct.get('interpretation', []):
        print(f"  - {line}")

# %% [markdown]
# ## Space Weather

# %%
weather = scan.get('space_weather', {})
if weather.get('error'):
    print(f"Error: {weather['error']}")
else:
    print("Current conditions:")
    for line in weather.get('interpretation', []):
        print(f"  - {line}")

# %% [markdown]
# ## Historical Maps

# %%
maps = scan.get('historical_maps', [])
print(f"Available map sources: {len(maps)}")
for m in maps:
    print(f"  {m['name']}: {m['url']}")
