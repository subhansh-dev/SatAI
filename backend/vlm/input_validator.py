"""
SatAI — Input Validator
PS SIH26167 mandates the agentic controller to *check input images*:
number, modality, format, metadata and compatibility — BEFORE any model runs.

Policy (from the PS):
- GeoTIFF / TIFF are first-class inputs (ISRO/SAC Cartosat-2S + RISAT pairs).
- PNG / JPEG are accepted (public benchmark datasets + demo), but flagged.
- Single-image modes need exactly 1 image; pair modes need exactly 2.
- Cross-modal pairs must contain one optical and one SAR source.
- Bi-temporal pairs should be dimension-compatible (pre-georeferenced eval data).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from core import config
from .schemas import (
    ImageMeta, ImageInput, Modality, Severity, ValidationIssue, ValidationReport,
)
from .image_utils import (
    decode_b64, detect_modality, load_pil, sniff_format, tiff_metadata,
)

logger = logging.getLogger("satai.validator")

_FORMAT_ISSUE = {
    "png": ("info", "benchmark-format",
            "PNG input — per the PS, raster formats are preferred for geospatial "
            "imagery; PNG/JPEG are accepted for public benchmark datasets."),
    "jpeg": ("info", "benchmark-format",
             "JPEG input — accepted for benchmark datasets and quick demos; "
             "GeoTIFF/TIFF is preferred for geospatial analysis."),
    "bmp": ("warning", "non-standard-format",
            "BMP input — will be converted, but GeoTIFF/TIFF/PNG/JPEG are the "
            "supported formats."),
    "webp": ("warning", "non-standard-format",
             "WEBP input — will be converted, but GeoTIFF/TIFF/PNG/JPEG are the "
             "supported formats."),
    "gif": ("warning", "non-standard-format",
            "GIF input — will be converted, but GeoTIFF/TIFF/PNG/JPEG are the "
            "supported formats."),
}


def validate_inputs(images: List[ImageInput], mode: str,
                    metadata: Optional[Dict[str, Any]] = None) -> ValidationReport:
    """Full compatibility check. Never raises — a structured report is the product."""
    metadata = metadata or {}
    issues: List[ValidationIssue] = []
    metas: List[ImageMeta] = []
    # NOTE: pydantic v2 copies lists on model construction — build the report
    # fields at the end, not by reference at the start.
    report = ValidationReport(issues=[], images=[])

    # ---------------- number of images ----------------
    n = len(images)
    if n == 0:
        report.accepted = False
        issues.append(ValidationIssue(
            level=Severity.ERROR, code="no-images",
            message="No image provided. Upload 1 image for single-image analysis, "
                    "or 2 images for bi-temporal / cross-modal analysis."))
    if mode == "bitemporal" and n != 2:
        report.accepted = False
        issues.append(ValidationIssue(
            level=Severity.ERROR, code="pair-count",
            message=f"Bi-temporal analysis needs exactly 2 images (before/after), got {n}"))
    if mode == "crossmodal" and n != 2:
        report.accepted = False
        issues.append(ValidationIssue(
            level=Severity.ERROR, code="pair-count",
            message=f"Cross-modal analysis needs exactly 2 images (1 optical + 1 SAR), got {n}"))
    if mode == "single" and n != 1:
        report.accepted = False
        issues.append(ValidationIssue(
            level=Severity.ERROR, code="single-count",
            message=f"Single-image analysis needs exactly 1 image, got {n}"))
    if n > config.MAX_IMAGES_PER_QUERY:
        report.accepted = False
        issues.append(ValidationIssue(
            level=Severity.ERROR, code="too-many",
            message=f"More than {config.MAX_IMAGES_PER_QUERY} images are not supported."))

    # ---------------- per-image checks ----------------
    total_bytes = 0
    for idx, img_in in enumerate(images):
        meta = ImageMeta(index=idx, name=img_in.name or None)
        try:
            raw = decode_b64(img_in.data)
        except ValueError as e:
            issues.append(ValidationIssue(
                level=Severity.ERROR, code="undecodable",
                message=f"Image {idx + 1}: {e}", image_index=idx))
            report.accepted = False
            meta.format = "unknown"
            metas.append(meta)
            continue

        meta.file_size_bytes = len(raw)
        total_bytes += len(raw)
        if len(raw) > config.MAX_IMAGE_BYTES:
            issues.append(ValidationIssue(
                level=Severity.ERROR, code="image-too-large",
                message=f"Image {idx + 1} is {len(raw) / 1e6:.1f} MB "
                        f"(limit {config.MAX_IMAGE_BYTES / 1e6:.0f} MB)", image_index=idx))
            report.accepted = False

        fmt = sniff_format(raw)
        meta.format = fmt
        if fmt in ("tiff", "geotiff") or fmt == "unknown":
            pass  # handled below
        elif fmt in _FORMAT_ISSUE:
            lvl, code, msg = _FORMAT_ISSUE[fmt]
            issues.append(ValidationIssue(level=Severity(lvl), code=code,
                                          message=f"Image {idx + 1}: {msg}", image_index=idx))
        else:
            issues.append(ValidationIssue(
                level=Severity.ERROR, code="unsupported-format",
                message=f"Image {idx + 1}: unsupported format '{fmt}'. "
                        f"Supported: GeoTIFF/TIFF (geospatial), PNG/JPEG (benchmarks).",
                image_index=idx))
            report.accepted = False

        try:
            pil = load_pil(raw)
        except Exception as e:
            issues.append(ValidationIssue(
                level=Severity.ERROR, code="undecodable",
                message=f"Image {idx + 1} could not be decoded: {e}", image_index=idx))
            report.accepted = False
            metas.append(meta)
            continue

        meta.width, meta.height = pil.size
        if pil.size[0] < config.MIN_IMAGE_DIM or pil.size[1] < config.MIN_IMAGE_DIM:
            issues.append(ValidationIssue(
                level=Severity.ERROR, code="image-too-small",
                message=f"Image {idx + 1} is {pil.size[0]}x{pil.size[1]} px — "
                        f"minimum is {config.MIN_IMAGE_DIM}x{config.MIN_IMAGE_DIM}.",
                image_index=idx))
            report.accepted = False
        if pil.size[0] > config.MAX_IMAGE_DIM or pil.size[1] > config.MAX_IMAGE_DIM:
            issues.append(ValidationIssue(
                level=Severity.WARNING, code="image-very-large",
                message=f"Image {idx + 1} is {pil.size[0]}x{pil.size[1]} px — it will be "
                        f"downscaled to {config.VLM_MAX_SIDE}px for the VLM.",
                image_index=idx))

        # TIFF/GeoTIFF specifics
        if fmt in ("tiff", "geotiff"):
            tmeta = tiff_metadata(raw)
            meta.num_bands = tmeta.get("num_bands") or _pil_bands(pil)
            meta.dtype = tmeta.get("dtype")
            meta.bit_depth = tmeta.get("bit_depth")
            meta.georeferenced = tmeta.get("georeferenced", False)
            meta.ground_sample_dist_m = tmeta.get("ground_sample_dist_m")
            meta.crs_note = tmeta.get("crs_note")
            meta.extra_geo = {k: v for k, v in tmeta.items()
                              if k in ("pixel_scale", "tiepoint")}  # type: ignore[attr-defined]
            if fmt == "tiff":
                issues.append(ValidationIssue(
                    level=Severity.INFO, code="plain-tiff",
                    message=f"Image {idx + 1}: TIFF without GeoTIFF geokeys — pixel-space "
                            f"coordinates will be used for localisation output.",
                    image_index=idx))
            if meta.georeferenced:
                gsd = meta.ground_sample_dist_m
                issues.append(ValidationIssue(
                    level=Severity.INFO, code="geotiff-ok",
                    message=f"Image {idx + 1}: GeoTIFF detected"
                            + (f", ~{gsd} m/px" if gsd else "")
                            + " — localisation can be mapped to map coordinates.",
                    image_index=idx))
        else:
            meta.num_bands = _pil_bands(pil)

        # ---------------- modality ----------------
        detected, reason = detect_modality(
            raw, name=img_in.name, declared=img_in.modality or img_in.tag,
            pil_image=pil, tmeta={"num_bands": meta.num_bands})
        meta.declared_modality = (img_in.modality or img_in.tag or Modality.UNKNOWN.value)
        meta.detected_modality = detected
        meta.modality_reason = reason
        metas.append(meta)

    # ---------------- payload budget ----------------
    report.raw_size_bytes = total_bytes
    if total_bytes > config.MAX_TOTAL_PAYLOAD_BYTES:
        report.accepted = False
        issues.append(ValidationIssue(
            level=Severity.ERROR, code="payload-too-large",
            message=f"Total upload {total_bytes / 1e6:.0f} MB exceeds the "
                    f"{config.MAX_TOTAL_PAYLOAD_BYTES / 1e6:.0f} MB request budget."))

    # ---------------- pair compatibility ----------------
    if n == 2 and len(metas) == 2 and all(m.width for m in metas):
        a, b = metas
        if (a.width, a.height) == (b.width, b.height):
            report.pair_compatibility = ("dimensions match — consistent with a "
                                         "pre-georeferenced, co-registered pair")
        else:
            ratio = max(a.width / max(b.width, 1), b.width / max(a.width, 1))
            if ratio <= 1.05:
                report.pair_compatibility = ("minor dimension mismatch — acceptable "
                                             "if the pair is pre-registered")
            else:
                report.pair_compatibility = (
                    f"dimension mismatch ({a.width}x{a.height} vs {b.width}x{b.height}) — "
                    "verify both scenes cover the same area")
            issues.append(ValidationIssue(
                level=Severity.WARNING, code="pair-dimensions",
                message=f"Pair dimensions differ: image 1 is {a.width}x{a.height}, "
                        f"image 2 is {b.width}x{b.height}.", image_index=1))

        if mode == "crossmodal":
            mods = {a.detected_modality, b.detected_modality}
            if a.detected_modality == b.detected_modality and a.detected_modality != "unknown":
                issues.append(ValidationIssue(
                    level=Severity.WARNING, code="crossmodal-modalities",
                    message=f"Both images look '{a.detected_modality}'. Cross-modal "
                            f"analysis expects one optical + one SAR image — tag them "
                            f"explicitly if detection is wrong.", image_index=1))
            elif mods == {"optical", "sar"}:
                issues.append(ValidationIssue(
                    level=Severity.INFO, code="crossmodal-ok",
                    message="Optical + SAR pair confirmed by modality detection."))

    report.total_pixels = sum(m.width * m.height for m in metas)
    report.issues = issues
    report.images = metas
    report.ok = not any(i.level == Severity.ERROR for i in issues)
    return report


def _pil_bands(img: Image.Image) -> int:
    try:
        return len(img.getbands())
    except Exception:
        return 0
