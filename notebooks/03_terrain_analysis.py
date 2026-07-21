# %% [markdown]
# # CHRONOVISOR — Terrain Analysis Demo
# 
# This notebook demonstrates the terrain pipeline:
# 1. Fetch real elevation data from Open-Elevation API
# 2. Generate 3D terrain model
# 3. Detect ridges, valleys, and anomalies
# 4. Visualize elevation profiles

# %%
import sys
sys.path.insert(0, '..')

import numpy as np
import matplotlib.pyplot as plt
from pipeline.data_ingestion import DataIngestion
from pipeline.ai_reconstructor import AIReconstructor

ingestion = DataIngestion()
ai = AIReconstructor()
ai.load_models()

# %% [markdown]
# ## Fetch Real Elevation Data
# 
# Get a 50x50 elevation grid from Open-Elevation (SRTM 30m).
# Using Hampi, Karnataka — known archaeological site.

# %%
lat, lon = 15.3350, 76.4600  # Hampi
grid_size = 30

print(f"Fetching {grid_size}x{grid_size} elevation grid for ({lat}, {lon})...")
terrain = ingestion.get_terrain_grid(lat, lon, grid_size=grid_size, span_deg=0.015)

if 'error' in terrain:
    print(f"Error: {terrain['error']}")
else:
    print(f"Source: {terrain['source']}")
    print(f"Elevation range: {terrain['min_elevation']}m - {terrain['max_elevation']}m")
    print(f"Ridge points: {terrain['ridge_points']}")
    print(f"Valley points: {terrain['valley_points']}")

# %% [markdown]
# ## Visualize Elevation Grid

# %%
elevation = np.array(terrain['elevation'])

fig, ax = plt.subplots(1, 1, figsize=(8, 8))
im = ax.imshow(elevation, cmap='terrain', origin='lower')
plt.colorbar(im, ax=ax, label='Elevation (m)')
ax.set_title(f'Elevation Grid — Hampi ({grid_size}x{grid_size})')
ax.set_xlabel('X')
ax.set_ylabel('Y')

# Mark ridges and valleys
for r in terrain['features']['ridges'][:5]:
    ax.plot(r['x'], r['y'], 'r^', markersize=8)
for v in terrain['features']['valleys'][:5]:
    ax.plot(v['x'], v['y'], 'bv', markersize=8)

plt.tight_layout()
plt.show()

# %% [markdown]
# ## 3D Terrain Analysis with AI

# %%
result = ai.reconstruct_3d_terrain(elevation, lat, lon)
print(f"Grid size: {result['grid_size']}")
print(f"Ridge points: {result['ridge_points']}")
print(f"Valley points: {result['valley_points']}")
print(f"Anomaly points: {result['anomaly_points']}")

print(f"\nTop ridges:")
for r in result['features']['ridges'][:5]:
    print(f"  ({r['x']}, {r['y']}) = {r['elevation']}m")

print(f"\nTop valleys:")
for v in result['features']['valleys'][:5]:
    print(f"  ({v['x']}, {v['y']}) = {v['elevation']}m")

print(f"\nGradient anomalies (sharp elevation changes):")
for a in result['features']['anomalies'][:5]:
    print(f"  ({a['x']}, {a['y']}) gradient={a['gradient']}")

# %% [markdown]
# ## Elevation Cross-Section

# %%
mid = grid_size // 2

fig, axes = plt.subplots(2, 1, figsize=(12, 6))

# Horizontal cross-section
axes[0].plot(elevation[mid, :], 'g-', linewidth=1.5)
axes[0].fill_between(range(grid_size), elevation[mid, :], alpha=0.2, color='green')
axes[0].set_title(f'Elevation Cross-Section (Y={mid})')
axes[0].set_ylabel('Elevation (m)')
axes[0].grid(True, alpha=0.3)

# Vertical cross-section
axes[1].plot(elevation[:, mid], 'b-', linewidth=1.5)
axes[1].fill_between(range(grid_size), elevation[:, mid], alpha=0.2, color='blue')
axes[1].set_title(f'Elevation Cross-Section (X={mid})')
axes[1].set_ylabel('Elevation (m)')
axes[1].set_xlabel('Grid position')
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# %% [markdown]
# ## Single-Point Elevation

# %%
single = ingestion.get_elevation(lat, lon)
if 'error' not in single:
    print(f"Elevation at ({lat}, {lon}): {single['elevation_m']}m")
    print(f"Source: {single['source']}")
else:
    print(f"Error: {single['error']}")
