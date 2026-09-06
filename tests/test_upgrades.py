"""
SatAI — Tests for the 2026-09 upgrade batch:
confidence parsing, GeoTIFF detection, band picking, nodata safety,
EPSG/UTM georeferencing, SAR stats, spectral indices, query decomposition,
model registry, aspect-preserving change regions.
"""
from __future__ import annotations

import base64
import io

import numpy as np
import pytest

from backend.vlm.image_utils import (
    _epsg_from_geokeys, _pick_channels, _looks_geotiff, pixel_to_geo,
    prepare_for_vlm, sar_stats, sniff_format, spectral_index,
    utm_zone_from_epsg,
)
from backend.vlm.tools.base import BaseTool
from backend.vlm.visual_evidence import label_changed_regions


# ---------------------------------------------------------------- fixtures
def _rgb_png_bytes(w=64, h=48, seed=1) -> bytes:
    from PIL import Image
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def _geotiff_bytes(w=32, h=32, bands=4, epsg=32633) -> bytes:
    """Synthetic multispectral GeoTIFF with pixel-scale + tiepoint + UTM geokeys."""
    import tifffile
    rng = np.random.default_rng(7)
    data = rng.integers(0, 4000, (h, w, bands), dtype=np.uint16)
    # geokeys: [ver, rev, minor, nkeys, (2048 GeographicType...) ...]
    geokeys = [1, 1, 0, 2,
               2048, 0, 1, 4326,          # GeographicTypeGeoKey = WGS84
               3072, 0, 1, epsg]          # ProjectedCSTypeGeoKey = UTM 33N
    buf = io.BytesIO()
    tifffile.imwrite(
        buf, data, photometric="minisblack", planarconfig="contig",
        resolution=(10.0, 10.0),
        metadata=None,
        extratags=[
            (33550, 12, 3, (10.0, 10.0, 0.0), False),      # ModelPixelScale
            (33922, 12, 6, (0.0, 0.0, 0.0, 442000.0, 4420000.0, 0.0), False),
            (34735, 3, len(geokeys), geokeys, False),       # GeoKeyDirectory
        ])
    return buf.getvalue()


def _plain_tiff_bytes(w=32, h=32) -> bytes:
    import tifffile
    buf = io.BytesIO()
    tifffile.imwrite(buf, np.zeros((h, w, 3), dtype=np.uint8))
    return buf.getvalue()


# ---------------------------------------------------------------- confidence
class TestConfidenceParsing:
    def test_decimal_confidence_not_zero(self):
        conf, reported = BaseTool._extract_confidence("blah\nCONFIDENCE: 0.85")
        assert reported and conf == pytest.approx(0.85)

    def test_percent_scale(self):
        conf, reported = BaseTool._extract_confidence("x\nCONFIDENCE: 85")
        assert reported and conf == pytest.approx(0.85)

    def test_equals_sign(self):
        conf, reported = BaseTool._extract_confidence("CONFIDENCE = 92")
        assert reported and conf == pytest.approx(0.92)

    def test_missing_falls_back_flagged(self):
        conf, reported = BaseTool._extract_confidence("no confidence line")
        assert not reported and conf == 0.6


# ---------------------------------------------------------------- geotiff
class TestGeoTiffDetection:
    def test_plain_tiff_not_geotiff(self):
        assert sniff_format(_plain_tiff_bytes()) == "tiff"
        assert _looks_geotiff(_plain_tiff_bytes()) is False

    def test_geotiff_detected_via_tags(self):
        raw = _geotiff_bytes()
        assert sniff_format(raw) == "geotiff"
        assert _looks_geotiff(raw) is True


# ---------------------------------------------------------------- bands
class TestBandPicking:
    def test_true_colour_for_13_band_s2(self):
        arr = np.zeros((8, 8, 13), dtype=np.uint16)
        arr[..., 1], arr[..., 2], arr[..., 3] = 10, 20, 30   # B2,B3,B4
        chans, stretch, picks = _pick_channels(arr, False, "geotiff")
        assert picks == (3, 2, 1)          # R=B4, G=B3, B=B2

    def test_true_colour_for_4_band_bgrn(self):
        arr = np.zeros((8, 8, 4), dtype=np.uint16)
        chans, stretch, picks = _pick_channels(arr, False, "geotiff")
        assert picks == (2, 1, 0)          # RGB from B,G,R,NIR

    def test_rgb_untouched(self):
        arr = np.zeros((8, 8, 3), dtype=np.uint8)
        _, _, picks = _pick_channels(arr, False, "png")
        assert picks == (0, 1, 2)


# ---------------------------------------------------------------- nodata
class TestNodataSafety:
    def test_nan_pixels_do_not_poison_stretch(self):
        raw = _rgb_png_bytes()
        # NaN can't live in a PNG; feed a synthetic float TIFF instead
        import tifffile
        buf = io.BytesIO()
        arr = np.full((32, 32, 3), 1000.0, dtype=np.float32)
        arr[0, 0, 0] = np.nan
        tifffile.imwrite(buf, arr)
        b64, info = prepare_for_vlm(buf.getvalue())
        assert b64 and info["source_format"] == "tiff"

    def test_nodata_const_image(self):
        import tifffile
        buf = io.BytesIO()
        tifffile.imwrite(buf, np.full((32, 32), -9999.0, dtype=np.float32))
        b64, _ = prepare_for_vlm(buf.getvalue())
        assert b64                          # must not crash / produce garbage


# ---------------------------------------------------------------- geo
class TestGeoreference:
    def test_epsg_from_geokeys(self):
        gk = [1, 1, 0, 2, 2048, 0, 1, 4326, 3072, 0, 1, 32633]
        assert _epsg_from_geokeys(gk) == 32633

    def test_utm_zone_decode(self):
        assert utm_zone_from_epsg(32633) == (33, True)
        assert utm_zone_from_epsg(32707) == (7, False)
        assert utm_zone_from_epsg(4326) is None

    def test_pixel_to_geo_wgs84(self):
        geo = {"pixel_scale": [10.0, 10.0],
               "tiepoint": [0.0, 0.0, 0.0, 442000.0, 4420000.0, 0.0],
               "epsg": 32633}
        label, ring = pixel_to_geo([0, 0, 1000, 1000], 100, 100, geo)
        assert "WGS84" in label
        lon1, lat1 = ring[0]
        lon2, lat2 = ring[2]
        assert lon2 > lon1 and lat2 < lat1        # east & south corners
        assert abs(ring[0][0] - ring[4][0]) < 1e-6  # closed ring

    def test_pixel_to_geo_projected_fallback(self):
        geo = {"pixel_scale": [10.0, 10.0],
               "tiepoint": [0.0, 0.0, 0.0, 442000.0, 4420000.0, 0.0]}
        label, ring = pixel_to_geo([0, 0, 10, 10], 10, 10, geo)
        assert "projected" in label
        assert ring[0] == [442000.0, 4420000.0]

    def test_no_geo_returns_pixel(self):
        label, ring = pixel_to_geo([0, 0, 1, 1], 10, 10, None)
        assert label == "image-pixel" and ring is None


# ---------------------------------------------------------------- SAR stats
class TestSarStats:
    def test_stats_measured(self):
        import tifffile
        rng = np.random.default_rng(3)
        arr = rng.gamma(4.0, 50.0, (64, 64)).astype(np.float32)
        arr[:16, :] = 5.0                       # "dark water" quadrant
        buf = io.BytesIO()
        tifffile.imwrite(buf, arr)
        st = sar_stats(buf.getvalue())
        assert "speckle_cov" in st and "dark_fraction" in st
        assert st["dark_fraction"] > 0.1        # dark quadrant detected


# ---------------------------------------------------------------- spectral
class TestSpectralIndex:
    def test_ndvi_from_4band_geotiff(self):
        import tifffile
        rng = np.random.default_rng(5)
        arr = rng.integers(100, 300, (32, 32, 4), dtype=np.uint16)
        arr[..., 2] = 200                        # Red
        arr[..., 3] = 2000                       # NIR -> NDVI = 1600/2200 ≈ .727
        buf = io.BytesIO()
        tifffile.imwrite(buf, arr, photometric="minisblack", planarconfig="contig")
        out = spectral_index(buf.getvalue(), "ndvi")
        assert "error" not in out
        st = out["stats"]
        assert st["mean"] == pytest.approx(1800 / 2200, abs=0.02)   # (NIR-Red)/(NIR+Red)
        assert st["threshold_fraction"]["fraction"] == pytest.approx(1.0, abs=0.01)
        assert out.get("index_preview_b64")

    def test_ndwi_band_convention_10band(self):
        import tifffile
        arr = np.zeros((16, 16, 10), dtype=np.uint16)
        arr[..., 1] = 1000    # B3 green
        arr[..., 6] = 100     # B8 NIR -> NDWI = 900/1100 ≈ .818
        buf = io.BytesIO()
        tifffile.imwrite(buf, arr, photometric="minisblack", planarconfig="contig")
        out = spectral_index(buf.getvalue(), "ndwi")
        assert "error" not in out
        assert out["stats"]["mean"] == pytest.approx(900 / 1100, abs=0.02)

    def test_rejects_png(self):
        out = spectral_index(_rgb_png_bytes(), "ndvi")
        assert "error" in out

    def test_rejects_unknown_index(self):
        out = spectral_index(_geotiff_bytes(), "evi")
        assert "error" in out


# ---------------------------------------------------------------- change
class TestChangeRegions:
    def test_connected_regions_found(self):
        mask = np.zeros((100, 100), dtype=bool)
        mask[10:20, 10:20] = True               # region 1
        mask[60:90, 60:80] = True               # region 2 (larger)
        regions = label_changed_regions(mask)
        assert len(regions) == 2
        assert regions[0]["pixels"] == 20 * 30  # larger first
        x1, y1, x2, y2 = regions[1]["bbox_norm"]
        assert (x1, y1, x2, y2) == (100.0, 100.0, 200.0, 200.0)


# ---------------------------------------------------------------- agentic
class TestDecompositionAndRegistry:
    @pytest.fixture
    def controller(self, monkeypatch):
        monkeypatch.setenv("VLM_MODE", "cloud")
        monkeypatch.setattr("backend.vlm.controller.VLMClient", object)
        from backend.vlm.controller import Controller
        # build with a stubbed VLMClient
        ctrl = object.__new__(Controller)
        from tests.mock_vlm import MockVLM
        ctrl.vlm = MockVLM()
        ctrl.store = __import__("backend.vlm.controller",
                                fromlist=["QueryStore"]).QueryStore(10)
        return ctrl

    def test_decompose_three_intents(self, controller):
        plan = controller._decompose(
            "Describe the land cover and also how many buildings are there, "
            "then highlight the water bodies", 1)
        tids = [t for _q, t in plan]
        assert "caption" in tids and "numeric" in tids and "ground" in tids
        assert tids[0] == "caption" and tids[-1] == "ground"   # analyst order

    def test_decompose_single_intent_returns_empty(self, controller):
        assert controller._decompose("What changed between these two dates?",
                                     2) == []

    def test_model_registry_routing(self):
        from backend.vlm.tool_registry import select_model
        hint, _ = select_model("single_caption", "local", lora_served=True)
        assert hint == "lora"
        hint, reason = select_model("single_caption", "local", lora_served=False)
        assert hint == "base" and "not served" in reason
        hint, _ = select_model("single_vqa", "cloud")
        assert hint == "flagship"

    def test_spectral_classification_route(self, controller):
        task = controller._rule_classify("compute the NDVI of this field", 1)
        assert task == "spectral_index"
