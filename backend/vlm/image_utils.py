"""
SatAI — RS Image Utilities
Handles the messy reality of remote-sensing raster input that a generic VLM
pipeline ignores:

- GeoTIFF / multi-band TIFF (Cartosat-2S MS, Sentinel-2)  -> 8-bit RGB view
- Single-band SAR amplitude (RISAT-1, Sentinel-1)         -> log-stretched gray
- 16-bit optical with wild dynamic range                  -> 2-98% percentile stretch
- Oversized imagery                                       -> downscaled VLM view
- GeoTIFF georeference tags (pixel scale / tiepoint)      -> used for GeoJSON

Everything runs on PIL + numpy (+ tifffile when present). No GDAL dependency.
"""
from __future__ import annotations

import base64
import io
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("satai.image")

Image.MAX_IMAGE_PIXELS = 300_000_000  # allow large scene tiles safely

try:
    import tifffile  # lightweight, pure-python TIFF reader
    _HAS_TIFFFILE = True
except Exception:  # pragma: no cover
    _HAS_TIFFFILE = False

# PIL format -> canonical
_FMT_MAP = {"PNG": "png", "JPEG": "jpeg", "TIFF": "tiff", "MPO": "jpeg",
            "BMP": "bmp", "WEBP": "webp", "GIF": "gif"}

_SAR_NAME_RE = re.compile(
    r"(sar|risat|sentinel[-_ ]?1|s1[ab]|vv|vh|hh|hv|sigma|gamma0|backscatter)",
    re.IGNORECASE)


# ---------------------------------------------------------------------------
# Base64 helpers
# ---------------------------------------------------------------------------
def strip_data_uri(b64: str) -> str:
    """Accept both raw base64 and data-URI form."""
    if b64.startswith("data:"):
        _, _, payload = b64.partition(",")
        return payload.strip()
    return b64.strip()


def decode_b64(b64: str) -> bytes:
    """Base64 -> raw bytes; raises ValueError on garbage."""
    clean = strip_data_uri(b64)
    try:
        return base64.b64decode(clean, validate=False)
    except Exception as e:
        raise ValueError(f"Invalid base64 image data: {e}") from e


def sniff_format(raw: bytes) -> str:
    """Magic-byte format sniffing. Returns png|jpeg|tiff|geotiff|bmp|webp|gif|unknown."""
    if len(raw) < 12:
        return "unknown"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if raw[:4] in (b"II*\x00", b"MM\x00*"):
        # TIFF — check for GeoTIFF keys inside
        return "geotiff" if _looks_geotiff(raw) else "tiff"
    if raw[:2] == b"BM":
        return "bmp"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "unknown"


def _looks_geotiff(raw: bytes) -> bool:
    """Cheap check for GeoTIFF GeoKey / ModelTiepoint tags in the raw header."""
    keys = (b"ModelPixelScale", b"ModelTiepoint", b"GeoKeyDirectory",
            b"GTModelTypeGeoKey", b"ProjectedCSTypeGeoKey")
    return any(k in raw[:65536] for k in keys)


# ---------------------------------------------------------------------------
# PIL / TIFF metadata
# ---------------------------------------------------------------------------
def load_pil(raw: bytes) -> Image.Image:
    """Decode bytes into a PIL image, applying EXIF orientation."""
    img = Image.open(io.BytesIO(raw))
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def tiff_metadata(raw: bytes) -> Dict[str, Any]:
    """
    Extract bands / dtype / georeference from a TIFF using tifffile.
    Falls back to PIL tags when tifffile is unavailable.
    """
    meta: Dict[str, Any] = {"num_bands": 0, "dtype": None, "bit_depth": None,
                            "georeferenced": False, "ground_sample_dist_m": None,
                            "crs_note": None, "band_descriptions": []}
    if not _HAS_TIFFFILE:
        return meta
    try:
        with tifffile.MemoryFile(raw) as mf:
            series = mf.series[0]
            page = series.pages[0] if series.pages else None
            # band count: S axis position, else trailing dimension, else 1
            if "S" in series.axes:
                meta["num_bands"] = int(series.shape[series.axes.index("S")])
            elif series.ndim >= 3:
                meta["num_bands"] = int(series.shape[-1])
            else:
                meta["num_bands"] = 1
            meta["dtype"] = str(series.dtype)
            if meta["dtype"] and meta["dtype"].startswith(("uint", "int", "float")):
                try:
                    meta["bit_depth"] = str(int(meta["dtype"].replace("uint", "")
                                                .replace("int", "").replace("float", "")))
                except ValueError:
                    pass
            if page is not None:
                tags = {t.name: t.value for t in page.tags.values()}
                scale = tags.get("ModelPixelScaleTag")      # (sx, sy, sz)
                tie = tags.get("ModelTiepointTag")          # (i,k,x,y,z,...)
                if scale and len(scale) >= 2 and float(scale[0]) > 0:
                    meta["ground_sample_dist_m"] = round(float(scale[0]), 3)
                    meta["pixel_scale"] = [float(scale[0]), float(scale[1])]
                    meta["georeferenced"] = True
                if tie and len(tie) >= 6:
                    meta["tiepoint"] = [float(v) for v in tie[:6]]
                    meta["georeferenced"] = True
                if tags.get("GeoKeyDirectoryTag"):
                    meta["georeferenced"] = True
                    meta["crs_note"] = "GeoTIFF GeoKeys present (EPSG CRS encoded)"
    except Exception as e:
        logger.debug("tifffile metadata parse failed: %s", e)
    return meta


# ---------------------------------------------------------------------------
# Modality heuristics (PS: "check input modality")
# ---------------------------------------------------------------------------
def detect_modality(raw: bytes, name: Optional[str] = None,
                    declared: Optional[str] = None,
                    pil_image: Optional[Image.Image] = None,
                    tmeta: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """
    Best-effort optical vs SAR detection.
    Order: explicit user declaration > filename cues > band count > speckle stats.
    Returns (modality, reason).
    """
    if declared in ("sar", "optical"):
        return declared, "declared by user"
    if name and _SAR_NAME_RE.search(name):
        return "sar", f"filename cue ('{name}')"
    if tmeta and tmeta.get("num_bands") == 1:
        cov = _speckle_cov(pil_image) if pil_image is not None else None
        if cov is not None and cov > 0.55:
            return "sar", f"single-band + high speckle (CoV={cov:.2f})"
        return "optical", "single-band, low speckle"
    return "unknown", "no distinguishing cues"


def _speckle_cov(img: Image.Image, sample: int = 96) -> Optional[float]:
    """Coefficient of variation on a downsampled patch — SAR speckle proxy."""
    try:
        g = np.asarray(img.convert("L").resize((sample, sample)), dtype=np.float32) / 255.0
        mean = float(g.mean())
        if mean <= 1e-6:
            return None
        return float(g.std() / mean)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# VLM-facing rendering (the core RS adaptation for *inputs*)
# ---------------------------------------------------------------------------
def _percentile_stretch(arr: np.ndarray, low_pct: float = 2.0, high_pct: float = 98.0) -> np.ndarray:
    lo, hi = np.percentile(arr, [low_pct, high_pct])
    if hi - lo < 1e-6:
        hi = lo + 1.0
    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def _sar_stretch(arr: np.ndarray) -> np.ndarray:
    """Log(1+x) amplitude transform (before shared percentile bounds)."""
    return np.log1p(np.clip(arr.astype(np.float64), 0, None))


def _decode_arr(raw: bytes) -> Tuple[np.ndarray, str]:
    """Decode bytes to a numpy array (TIFF via tifffile, else PIL)."""
    fmt = sniff_format(raw)
    if fmt in ("tiff", "geotiff") and _HAS_TIFFFILE:
        try:
            with tifffile.TiffFile(io.BytesIO(raw)) as tif:
                return tif.pages[0].asarray(), fmt
        except Exception as e:
            logger.warning("tifffile decode failed (%s); falling back to PIL", e)
    img = load_pil(raw)
    return np.asarray(img), fmt


def _pick_channels(arr: np.ndarray, is_sar: bool, fmt: str) -> Tuple[List[np.ndarray], str]:
    """Choose the 3 display channels (already log-transformed for SAR)."""
    if arr.ndim == 2:
        arr = arr[..., None]
    c = arr.shape[2] if arr.ndim == 3 else 1
    if c == 1:
        ch = arr[..., 0]
        ch = _sar_stretch(ch) if is_sar else ch.astype(np.float64)
        return [ch] * 3, ("log1p" if is_sar else "percentile_2_98")
    if c == 2:
        ch = arr[..., 0]
        ch = _sar_stretch(ch) if is_sar else ch.astype(np.float64)
        return [ch] * 3, ("log1p" if is_sar else "percentile_2_98")
    if is_sar:
        chans = [_sar_stretch(arr[..., min(i, c - 1)]) for i in (0, 1, 2)]
        return chans, "sar_falsecolor"
    picks = (c - 1, c - 2, c - 3) if (c > 3 and fmt in ("tiff", "geotiff")) else (0, 1, 2)
    return [arr[..., i].astype(np.float64) for i in picks], "percentile_2_98"


def _joint_bounds(channel_sets: List[List[np.ndarray]],
                  low_pct: float = 2.0, high_pct: float = 98.0) -> List[Tuple[float, float]]:
    """Percentile bounds computed across ALL images per channel — keeps a
    bi-temporal pair radiometrically comparable (independent stretches fake
    change)."""
    bounds = []
    for ci in range(3):
        joined = np.concatenate([chans[ci].ravel() for chans in channel_sets])
        lo, hi = np.percentile(joined, [low_pct, high_pct])
        if hi - lo < 1e-6:
            hi = lo + 1.0
        bounds.append((float(lo), float(hi)))
    return bounds


def prepare_for_vlm(raw: bytes, is_sar: bool = False, max_side: int = 1344,
                    jpeg_quality: int = 88,
                    shared_bounds: Optional[List[Tuple[float, float]]] = None
                    ) -> Tuple[str, Dict[str, Any]]:
    """
    Convert any supported raster (PNG/JPEG/TIFF/GeoTIFF, 8/16-bit, 1..N bands,
    optical or SAR) into an 8-bit RGB JPEG base64 tuned for VLM consumption.

    shared_bounds: [(lo, hi) x3] from prepare_pair_for_vlm — use for pairs so
    both images are normalised identically.
    Returns (b64_jpeg, info_dict).
    """
    fmt = sniff_format(raw)
    info: Dict[str, Any] = {"source_format": fmt, "stretch": "none",
                            "bands_used": None}
    try:
        arr, fmt = _decode_arr(raw)
        info["source_shape"] = list(arr.shape)
    except Exception as e:
        # absolute fallback: let PIL decide
        img = load_pil(raw)
        arr = np.asarray(img)
        info["source_shape"] = list(arr.shape)

    chans, stretch = _pick_channels(arr, is_sar, fmt)
    info["stretch"] = ("sar_falsecolor" if is_sar and arr.ndim == 3 and arr.shape[2] > 2
                       and stretch == "sar_falsecolor" else stretch)
    if is_sar:
        info["stretch"] = "log1p" if stretch == "log1p" else info["stretch"]

    bounds = shared_bounds or _joint_bounds([chans])
    if shared_bounds:
        info["normalisation"] = "shared_pair_bounds"
    arr_n = np.dstack([np.clip((ch - lo) / (hi - lo), 0.0, 1.0)
                       for ch, (lo, hi) in zip(chans, bounds)])

    rgb8 = (arr_n * 255).astype(np.uint8)
    img_out = Image.fromarray(rgb8)
    orig_w, orig_h = img_out.size
    img_out = downscale(img_out, max_side)
    if img_out.size != (orig_w, orig_h):
        info["downscaled_from"] = [orig_w, orig_h]
        info["downscaled_to"] = list(img_out.size)

    buf = io.BytesIO()
    img_out.save(buf, format="JPEG", quality=jpeg_quality)
    info["vlm_input_size"] = list(img_out.size)
    return base64.b64encode(buf.getvalue()).decode(), info


def prepare_pair_for_vlm(raw_a: bytes, raw_b: bytes,
                         is_sar_a: bool = False, is_sar_b: bool = False,
                         max_side: int = 1344, jpeg_quality: int = 88,
                         ) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
    """
    Jointly-normalised VLM views of a two-image pair. Essential for
    bi-temporal change analysis (identical radiometric scaling) — for
    cross-modal (optical+SAR) pairs the modalities stay independently
    normalised when their band semantics differ.
    """
    arr_a, fmt_a = _decode_arr(raw_a)
    arr_b, fmt_b = _decode_arr(raw_b)
    if is_sar_a != is_sar_b:
        # different sensors: independent normalisation is correct
        b64_a, info_a = prepare_for_vlm(raw_a, is_sar_a, max_side, jpeg_quality)
        b64_b, info_b = prepare_for_vlm(raw_b, is_sar_b, max_side, jpeg_quality)
        info_a["normalisation"] = "independent (mixed modalities)"
        info_b["normalisation"] = "independent (mixed modalities)"
        return b64_a, b64_b, info_a, info_b
    chans_a, st_a = _pick_channels(arr_a, is_sar_a, fmt_a)
    chans_b, st_b = _pick_channels(arr_b, is_sar_b, fmt_b)
    if st_a != st_b:
        b64_a, info_a = prepare_for_vlm(raw_a, is_sar_a, max_side, jpeg_quality)
        b64_b, info_b = prepare_for_vlm(raw_b, is_sar_b, max_side, jpeg_quality)
        return b64_a, b64_b, info_a, info_b
    bounds = _joint_bounds([chans_a, chans_b])
    b64_a, info_a = prepare_for_vlm(raw_a, is_sar_a, max_side, jpeg_quality,
                                    shared_bounds=bounds)
    b64_b, info_b = prepare_for_vlm(raw_b, is_sar_b, max_side, jpeg_quality,
                                    shared_bounds=bounds)
    return b64_a, b64_b, info_a, info_b


def downscale(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    scale = max_side / max(w, h)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def to_thumb_b64(raw_b64: str, max_side: int = 512, quality: int = 80) -> str:
    """Cheap thumbnail for UI display (already-encoded b64 input)."""
    try:
        img = load_pil(decode_b64(raw_b64))
        img = downscale(img.convert("RGB"), max_side)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return raw_b64


def pixel_to_geo(bbox_px: List[float], img_w: int, img_h: int,
                 geo: Optional[Dict[str, Any]]) -> Tuple[str, Any]:
    """
    Map a pixel-space [x1,y1,x2,y2] to geo coordinates when the source is a
    GeoTIFF carrying ModelPixelScale + ModelTiepoint (north-up assumption).

    Returns (crs_label, ring_coordinates).
    """
    scale = geo.get("pixel_scale") if geo else None
    tie = geo.get("tiepoint") if geo else None
    if not (scale and tie and len(scale) >= 2 and len(tie) >= 6):
        return "image-pixel", None

    sx, sy = float(scale[0]), float(scale[1])
    ox, oy = float(tie[3]), float(tie[4])   # map coords of pixel (tie[0], tie[1])
    px0, py0 = float(tie[0]), float(tie[1])

    def to_map(x: float, y: float) -> Tuple[float, float]:
        mx = ox + ((x - px0) + 0.5) * sx
        my = oy - ((y - py0) + 0.5) * sy   # north-up: y grows downward in pixels
        return round(mx, 8), round(my, 8)

    x1, y1, x2, y2 = bbox_px
    ring = [to_map(x1, y1), to_map(x2, y1), to_map(x2, y2), to_map(x1, y2), to_map(x1, y1)]
    return "GeoTIFF geotransform (north-up)", ring
