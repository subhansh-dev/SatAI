"""
SatAI — Bundled Demo Sample Generator
Creates samples/samples.json + sample scenes (GeoTIFF/TIFF/PNG) so the demo
works with zero uploads and no network: judges click a preset, the scene is
attached, the query runs.

Scenes (synthetic but sensor-plausible, seeded -> reproducible):
  1. urban_flood_sar.tiff      — single-band SAR-style amplitude, dark flood
                                 basin + bright built-up double bounce
  2. agri_field_s2.tiff        — 4-band multispectral GeoTIFF w/ geotags
                                 (fields, water canal, NDVI-able)
  3. city_pair_{t0,t1}.tiff    — 4-band bi-temporal pair; t1 adds built-up
                                 growth along the east highway + shrinks a
                                 vegetation patch (change-detection demo)

Usage:  python scripts/generate_samples.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "samples"
OUT.mkdir(exist_ok=True)

try:
    import tifffile
except ImportError:
    sys.exit("tifffile is required: pip install tifffile")


# --------------------------------------------------------------------------
# geo helpers: a fictional-but-plausible scene near Bhuj, Gujarat (flood-prone)
# --------------------------------------------------------------------------
UL_LAT, UL_LON = 23.30, 69.60          # upper-left corner (north-up)
GSD = 10.0                             # metres/pixel (Sentinel-2-like)
EPSG_UTM_ZONE = 32643                  # UTM 43N

GEO_KEYS = [
    1, 1, 0, 4,                        # version, revision, minor, num keys
    2048, 0, 1, 1,                     # GTModelTypeGeoKey = ModelTypeProjected
    3072, 0, 1, EPSG_UTM_ZONE,         # ProjectedCSTypeGeoKey
]

# GeoTIFF tag IDs (tifffile has no named constants for these)
TAG_GEOKEYDIRECTORY, TAG_PIXELSCALE, TAG_TIEPOINT = 34735, 33550, 33922


def geo_tags(h: int, w: int):
    """(tag_id, tifffile-dtype-char, values) — H=uint16, d=double."""
    return [
        (TAG_GEOKEYDIRECTORY, "H", np.array(GEO_KEYS, dtype=np.uint16)),
        (TAG_PIXELSCALE, "d", np.array([GSD, GSD, 0.0], dtype=np.float64)),
        (TAG_TIEPOINT, "d",
         np.array([0, 0, 0, UL_LON, UL_LAT, 0.0], dtype=np.float64)),
    ]


def smooth_noise(rng, shape, scale: int) -> np.ndarray:
    """Cheap value-noise: random coarse grid, bilinear upscaled, tiled smooth."""
    h, w = shape
    gh, gw = max(2, h // scale), max(2, w // scale)
    grid = rng.random((gh, gw)).astype(np.float32)
    rows = np.linspace(0, gh - 1, h)
    cols = np.linspace(0, gw - 1, w)
    r0 = rows.astype(int); c0 = cols.astype(int)
    r1 = np.clip(r0 + 1, 0, gh - 1); c1 = np.clip(c0 + 1, 0, gw - 1)
    fr = (rows - r0)[:, None]; fc = (cols - c0)[None, :]
    top = grid[r0, c0] * (1 - fc) + grid[r0, c1] * fc
    bot = grid[r1, c0] * (1 - fc) + grid[r1, c1] * fc
    return top * (1 - fr) + bot * fr


def save_tiff(path: Path, bands: list[np.ndarray], tags=None,
              photometric: str | None = None) -> None:
    stack = np.stack(bands).astype(np.float32)
    kw = {}
    if tags:
        kw["extratags"] = [
            (tag, dt, arr.size, arr.tobytes(), True)
            for tag, dt, arr in tags
        ]
    if photometric:
        kw["photometric"] = photometric
    tifffile.imwrite(path, stack, **kw)


# --------------------------------------------------------------------------
# scene 1 — SAR flood scene
# --------------------------------------------------------------------------
def gen_sar_flood(path: Path, h=512, w=512) -> None:
    rng = np.random.default_rng(42)
    yy, xx = np.mgrid[0:h, 0:w]

    # flood basin: smooth dark ellipse lower-left
    cx, cy, rx, ry, ang = 190, 340, 170, 110, -0.5
    xr, yr = (xx - cx), (yy - cy)
    xr2 = xr * np.cos(ang) + yr * np.sin(ang)
    yr2 = -xr * np.sin(ang) + yr * np.cos(ang)
    flood = ((xr2 / rx) ** 2 + (yr2 / ry) ** 2) < 1.0

    # built-up grid upper-right: bright double-bounce blocks
    built = ((xx % 26) < 12) & ((yy % 26) < 12) & (xx > w * 0.55) & (yy < h * 0.45)

    base = 80 + 60 * smooth_noise(rng, (h, w), 24)          # rough land
    amp = np.where(flood, 18 + 6 * rng.random((h, w)), base) # calm water = dark
    amp = np.where(built, amp + 150, amp)                     # metal = bright
    amp += rng.gamma(4.0, 6.0, (h, w))                        # speckle
    amp = np.clip(amp, 1, 255).astype(np.float32)

    save_tiff(path, [amp], tags=geo_tags(h, w))


# --------------------------------------------------------------------------
# scene 2 — multispectral agri scene (4-band GeoTIFF)
# --------------------------------------------------------------------------
def gen_agri(path: Path, h=512, w=512) -> None:
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w]
    field = ((xx // 64) + (yy // 64)) % 2 == 0          # checkerboard fields
    canal = np.abs(yy - (h * 0.72 + 14 * np.sin(xx / 40))) < 5

    vig = smooth_noise(rng, (h, w), 48)
    red = np.where(field, 60 + 50 * vig, 95 + 40 * smooth_noise(rng, (h, w), 16))
    nir = np.where(field, 190 + 45 * vig, 70 + 30 * rng.random((h, w)))
    nir = np.where(canal, 15, nir)
    red = np.where(canal, 10, red)
    green = np.clip(0.8 * nir + 0.1 * red + 5 * rng.random((h, w)), 0, 255)
    blue = np.clip(0.45 * red + 20 * rng.random((h, w)), 0, 255)
    red, nir = np.clip(red, 0, 255), np.clip(nir, 0, 255)

    save_tiff(path, [blue, green, red, nir], tags=geo_tags(h, w))


# --------------------------------------------------------------------------
# scene 3 — bi-temporal city pair (built-up growth + veg loss)
# --------------------------------------------------------------------------
def gen_city_pair(p0: Path, p1: Path, h=512, w=512) -> None:
    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:h, 0:w]

    veg0 = (smooth_noise(rng, (h, w), 40) > 0.45) & (xx < w * 0.5)
    river = np.abs(yy - (h * 0.25 + 10 * np.sin(xx / 60))) < 7

    # growth mask: new blocks along east highway (t1 only)
    growth = (xx > w * 0.6) & (yy > h * 0.55) & (((xx // 24) + (yy // 24)) % 2 == 0)

    def render(t1: bool) -> list[np.ndarray]:
        veg = veg0 & ~(growth if t1 else np.zeros_like(veg0))
        b = np.where(river, 35, 55 + 25 * smooth_noise(rng, (h, w), 32))
        g = np.where(veg, 120 + 50 * smooth_noise(rng, (h, w), 24), 70 + 20 * rng.random((h, w)))
        r = np.where(veg, 55 + 25 * rng.random((h, w)), 105 + 35 * smooth_noise(rng, (h, w), 20))
        if t1:
            g = np.where(growth, g * 0.7, g)
            r = np.where(growth, r * 1.25, r)
        g = np.where(river, 45, g)
        return [np.clip(c, 0, 255) for c in (b, g, r, np.clip(1.6 * g - 0.4 * r, 0, 255))]

    save_tiff(p0, render(False), tags=geo_tags(h, w))
    save_tiff(p1, render(True), tags=geo_tags(h, w))


def b64_png_of(bands, max_side=384) -> str:
    """JPEG preview (b64) for the UI — light, renders everywhere."""
    import base64
    from PIL import Image
    arr = np.stack(bands[:3]) if len(bands) >= 3 else np.repeat(bands[0][None], 3, axis=0)
    img = Image.fromarray(np.clip(arr.transpose(1, 2, 0), 0, 255).astype(np.uint8))
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    urban_sar = OUT / "urban_flood_sar.tiff"
    agri = OUT / "agri_field_s2.tiff"
    city0, city1 = OUT / "city_pair_t0.tiff", OUT / "city_pair_t1.tiff"

    gen_sar_flood(urban_sar)
    gen_agri(agri)
    gen_city_pair(city0, city1)

    # previews
    import tifffile as tf
    def bands_of(p):
        a = tf.imread(p)
        return [a[i] for i in range(min(4, a.shape[0]))]

    idx = {
        "samples": [
            {
                "id": "sar_flood",
                "title": "Urban flood — SAR scene (single)",
                "mode": "single",
                "query": "Highlight the flooded areas and the built-up structures in this SAR scene.",
                "file": "urban_flood_sar.tiff",
                "preview_b64": b64_png_of(bands_of(urban_sar)),
                "note": "Sentinel-1-style amplitude: dark = smooth (flood water), bright = double-bounce (built-up).",
            },
            {
                "id": "agri_ndvi",
                "title": "Agricultural fields — multispectral GeoTIFF (single)",
                "mode": "single",
                "query": "Compute the NDVI of this scene and describe the vegetation health and water bodies.",
                "file": "agri_field_s2.tiff",
                "preview_b64": b64_png_of(bands_of(agri)),
                "note": "4-band Sentinel-2-style GeoTIFF with georeference — spectral band-math runs offline.",
            },
            {
                "id": "city_change",
                "title": "Built-up growth — bi-temporal pair",
                "mode": "bitemporal",
                "query": "What changed between these two dates, and where did the change occur?",
                "files": ["city_pair_t0.tiff", "city_pair_t1.tiff"],
                "preview_b64": b64_png_of(bands_of(city1)),
                "note": "Urban expansion along the east highway between the two dates.",
            },
        ]
    }
    (OUT / "samples.json").write_text(json.dumps(idx, indent=2), encoding="utf-8")
    print(f"wrote {OUT/'samples.json'} + 4 TIFF scenes")


if __name__ == "__main__":
    main()
