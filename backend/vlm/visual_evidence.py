"""
SatAI — Visual Evidence Engine
The PS requires answers backed by *visual results*, not just text. This module
renders, server-side and fully offline (PIL + numpy):

- grounding boxes drawn over the image with labels
- heuristic spatial change maps for bi-temporal pairs (diff -> threshold ->
  colour overlay + stats), usable as visual evidence when reference masks
  are unavailable
- labelled side-by-side composites (bi-temporal, optical|SAR)
- input thumbnails for the evidence strip
"""
from __future__ import annotations

import base64
import io
import logging
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from core import config
from .image_utils import decode_b64, downscale, load_pil

logger = logging.getLogger("satai.evidence")

# evidence palette (readable over imagery)
_STROKE = (255, 82, 82)
_TEXT_BG = (10, 12, 20, 200)
_TEXT_FG = (255, 255, 255)
_LABEL_BG = (255, 82, 82)
_PANEL_BG = (10, 14, 24)
_PANEL_FG = (236, 240, 248)
_ACCENT = (56, 189, 248)

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Grounding annotation
# ---------------------------------------------------------------------------
def render_grounding(image_b64: str, boxes: List[Dict[str, Any]],
                     max_side: int = None) -> Tuple[str, str]:
    """
    Draw normalised 0-1000 boxes onto the image.
    Returns (annotated_png_b64, description).
    """
    max_side = max_side or config.EVIDENCE_MAX_SIDE
    img = load_pil(decode_b64(image_b64)).convert("RGB")
    img = downscale(img, max_side)
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    f_label = _font(max(12, int(h * 0.028)))
    f_conf = _font(max(10, int(h * 0.023)))

    for i, box in enumerate(boxes, 1):
        try:
            x1, y1, x2, y2 = (float(v) for v in box["bbox"])
        except (KeyError, TypeError, ValueError):
            continue
        x1, x2 = sorted((x1 / 1000.0 * w, x2 / 1000.0 * w))
        y1, y2 = sorted((y1 / 1000.0 * h, y2 / 1000.0 * h))
        label = str(box.get("label", f"object {i}"))
        conf = box.get("confidence")

        # corner-style strokes (satellite-annotation look)
        corner = max(3, int(min(w, h) * 0.02))
        lw = max(2, int(min(w, h) * 0.004))
        for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2 - corner, y1, 0, 1),
                                 (x1, y2 - corner, 1, 0), (x2 - corner, y2 - corner, 0, 0)):
            draw.rectangle([cx, cy, cx + corner, cy + corner],
                           outline=_STROKE, width=lw)
        # faint full rect for readability
        draw.rectangle([x1, y1, x2, y2], outline=_STROKE + (120,), width=1)

        # label chip
        text = label + (f"  {conf:.0%}" if isinstance(conf, (int, float)) else "")
        tb = draw.textbbox((0, 0), text, font=f_label)
        tw, th = tb[2] - tb[0] + 10, tb[3] - tb[1] + 6
        tx, ty = x1, max(0, y1 - th - 2)
        draw.rectangle([tx, ty, tx + tw, ty + th], fill=_LABEL_BG)
        draw.text((tx + 5, ty + 2), text, font=f_label, fill=_TEXT_FG)
        draw.text((tx + 5, ty + th + 2), f"#{i}", font=f_conf, fill=_ACCENT)

    desc = (f"{len(boxes)} grounded region(s) rendered over the image with "
            f"labels and confidence scores.")
    return _to_b64(img), desc


# ---------------------------------------------------------------------------
# Change map (heuristic, no reference mask needed)
# ---------------------------------------------------------------------------
def render_change_map(before_b64: str, after_b64: str) -> Dict[str, Any]:
    """
    Estimate a spatial change map from a bi-temporal pair:
    grayscale -> blur -> |diff| -> threshold (mean + k*std) -> dilate ->
    red overlay on the AFTER image + side-by-side + changed-region boxes.

    The analysis scale PRESERVES ASPECT RATIO (the old version forced both
    frames into 512x512, skewing every non-square satellite tile).

    Returns dict(mask_b64, side_b64, description, stats, regions).
    `regions` = top changed clusters as 0-1000-normalised boxes for the
    audit trace and georeferenced GeoJSON export.
    """
    before = load_pil(decode_b64(before_b64)).convert("RGB")
    after = load_pil(decode_b64(after_b64)).convert("RGB")

    # common analysis size: fit within a square budget WITHOUT distortion
    max_analysis = 512
    scale = max_analysis / max(before.size[0], before.size[1], 1)
    aw = max(32, int(before.size[0] * scale))
    ah = max(32, int(before.size[1] * scale))
    a_small = before.resize((aw, ah), Image.BILINEAR)
    b_small = after.resize((aw, ah), Image.BILINEAR)
    ga = np.asarray(a_small.convert("L"), dtype=np.float32)
    gb = np.asarray(b_small.convert("L"), dtype=np.float32)

    blur = config.CHANGE_DIFF_BLUR
    ga = np.asarray(Image.fromarray(ga.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(blur)), dtype=np.float32)
    gb = np.asarray(Image.fromarray(gb.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(blur)), dtype=np.float32)

    diff = np.abs(gb - ga)
    thr = diff.mean() + config.CHANGE_DIFF_K * diff.std()
    mask = (diff > max(thr, 8.0))

    if mask.any():
        mask_img = Image.fromarray((mask * 255).astype(np.uint8))
        mask_img = mask_img.filter(ImageFilter.MaxFilter(5))       # dilate
        mask_img = mask_img.filter(ImageFilter.MinFilter(3))       # despeckle
        mask = np.asarray(mask_img) > 128
    changed_pct = float(mask.mean() * 100.0)

    # colour overlay on AFTER: red where changed, alpha by diff magnitude
    overlay = np.asarray(b_small, dtype=np.float32).copy()
    heat = np.clip((diff - thr) / max(float(diff.max()) - thr, 1.0), 0, 1)
    for c, gain in ((0, 255.0), (1, 40.0), (2, 40.0)):
        overlay[..., c] = np.where(mask, overlay[..., c] * (1 - heat) + gain * heat,
                                   overlay[..., c])
    result = Image.fromarray(overlay.astype(np.uint8)).resize(after.size,
                                                              Image.BILINEAR)
    draw = ImageDraw.Draw(result)
    f = _font(max(14, int(after.size[1] * 0.03)))
    draw.rectangle([8, 8, 8 + f.size * 9, 14 + f.size * 1.6], fill=_TEXT_BG)
    draw.text((16, 12), f"CHANGE MAP · {changed_pct:.1f}% pixels changed",
              font=f, fill=_TEXT_FG)

    # changed-region clusters (connected components, largest first)
    regions = label_changed_regions(mask, max_regions=6)

    stats = {
        "method": "aspect-preserving grayscale diff, gaussian blur, "
                  "mean+%.1f*std threshold" % config.CHANGE_DIFF_K,
        "analysis_size": [aw, ah],
        "changed_pixels_pct": round(changed_pct, 2),
        "regions": regions,
        "verdict": ("significant change detected" if changed_pct >= config.CHANGE_MIN_REGION_PCT * 100
                    else "little or no significant change detected"),
        "note": "heuristic estimate — reference masks were not provided",
    }
    mask_b64 = _to_b64(result)

    # labelled side-by-side
    side_b64, _ = render_side_by_side(before, after, "BEFORE", "AFTER")
    desc = (f"Spatial change map: {changed_pct:.1f}% of pixels exceed the change "
            f"threshold ({stats['verdict']}); {len(regions)} dominant region(s) "
            f"extracted.")
    return {"mask_b64": mask_b64, "side_b64": side_b64,
            "description": desc, "stats": stats, "regions": regions}


def label_changed_regions(mask: np.ndarray,
                          max_regions: int = 6) -> List[Dict[str, Any]]:
    """
    Connected-component labelling (BFS, 4-neighbourhood) on the change mask.
    Returns the largest clusters as 0-1000-normalised bboxes with pixel areas:
    [{bbox_norm, pixels}] — consumable by the trace UI and the GeoJSON
    change-polygon export (normalised, so georeference applies cleanly).
    """
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    regions: List[Tuple[int, int, int, int, int]] = []   # x1,y1,x2,y2,area
    for sy in range(h):
        row = mask[sy]
        for sx in range(w):
            if not row[sx] or visited[sy, sx]:
                continue
            q = deque([(sy, sx)])
            visited[sy, sx] = True
            x1 = x2 = sx
            y1 = y2 = sy
            area = 0
            while q:
                cy, cx = q.popleft()
                area += 1
                if cx < x1: x1 = cx
                if cx > x2: x2 = cx
                if cy < y1: y1 = cy
                if cy > y2: y2 = cy
                for ny, nx in ((cy-1, cx), (cy+1, cx), (cy, cx-1), (cy, cx+1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] \
                            and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))
            if area >= 12:                     # ignore specks
                regions.append((x1, y1, x2, y2, area))
    regions.sort(key=lambda r: -r[4])
    out = []
    for x1, y1, x2, y2, area in regions[:max_regions]:
        out.append({
            "bbox_norm": [round(x1 / w * 1000, 1), round(y1 / h * 1000, 1),
                          round((x2 + 1) / w * 1000, 1), round((y2 + 1) / h * 1000, 1)],
            "pixels": int(area),
        })
    return out


# ---------------------------------------------------------------------------
# Side-by-side composite
# ---------------------------------------------------------------------------
def render_side_by_side(img_a: Image.Image, img_b: Image.Image,
                        label_a: str, label_b: str,
                        height: int = None) -> Tuple[str, str]:
    height = height or min(img_a.size[1], img_b.size[1],
                           config.EVIDENCE_MAX_SIDE // 2 + 256)
    def fit(im: Image.Image) -> Image.Image:
        w, h = im.size
        scale = height / max(h, 1)
        return im.resize((max(1, int(w * scale)), height), Image.LANCZOS)
    a, b = fit(img_a), fit(img_b)
    gap, header = 12, 40
    total_w = a.size[0] + b.size[0] + gap
    canvas = Image.new("RGB", (total_w, height + header), _PANEL_BG)
    canvas.paste(a, (0, header))
    canvas.paste(b, (a.size[0] + gap, header))
    draw = ImageDraw.Draw(canvas)
    f = _font(18)
    draw.text((10, 10), label_a, font=f, fill=_ACCENT)
    draw.text((a.size[0] + gap + 10, 10), label_b, font=f, fill=_STROKE)
    desc = f"Labelled side-by-side composite: {label_a} | {label_b}."
    return _to_b64(canvas), desc


def side_by_side_b64(b64_a: str, b64_b: str, label_a: str, label_b: str) -> Tuple[str, str]:
    a = load_pil(decode_b64(b64_a)).convert("RGB")
    b = load_pil(decode_b64(b64_b)).convert("RGB")
    return render_side_by_side(a, b, label_a, label_b)


# ---------------------------------------------------------------------------
# Input view
# ---------------------------------------------------------------------------
def input_view_b64(b64: str, label: str) -> Tuple[str, str]:
    img = load_pil(decode_b64(b64)).convert("RGB")
    img = downscale(img, config.THUMB_MAX_SIDE)
    header = 34
    canvas = Image.new("RGB", (img.size[0], img.size[1] + header), _PANEL_BG)
    canvas.paste(img, (0, header))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), label, font=_font(16), fill=_PANEL_FG)
    return _to_b64(canvas), f"Input image — {label}."


def _to_b64(img: Image.Image) -> str:
    """Evidence images as high-quality JPEG — satellite imagery needs no
    alpha, and this cuts the JSON payload ~5-8x versus PNG."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=87)
    return base64.b64encode(buf.getvalue()).decode()
