"""
Tests for scripts/convert_referring.py — RSBench referring → SatAI grounding
JSONL conversion (regression: grounding eval ran with zero GT boxes).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from convert_referring import convert_row, corners_aabb, parse_gt_boxes  # noqa: E402


SAMPLE = {
    "image_id": "P0003_0002.png",
    "question": "The large yellow vehicle situated closest to the green area.",
    "ground_truth": "{<25><40><33><60>}",
    "dataset": "RSBench",
    "question_id": 0,
    "type": "ref",
    "unique": False,
    "obj_corner": [0.333984375, 0.58984375, 0.287109375, 0.603515625,
                   0.255859375, 0.416015625, 0.2890625, 0.400390625],
    "obj_cls": "vehicle",
    "obj_ids": [0],
    "size_group": "",
}


# ------------------------------------------------------------------ gt string
def test_parse_gt_string_scales_to_01():
    assert parse_gt_boxes("{<25><40><33><60>}") == [(0.25, 0.40, 0.33, 0.60)]


def test_parse_gt_string_unordered_coords_sorted():
    assert parse_gt_boxes("{<60><33><25><40>}") == [(0.25, 0.33, 0.60, 0.40)]


def test_parse_gt_string_multiple_groups():
    assert len(parse_gt_boxes("{<1><2><3><4>}{<10><20><30><40>}")) == 2


def test_parse_gt_string_garbage_is_empty():
    assert parse_gt_boxes("no boxes here") == []
    assert parse_gt_boxes("{<1><2>}") == []          # < 4 numbers
    assert parse_gt_boxes("") == []


# --------------------------------------------------------------- corner AABB
def test_corners_aabb_matches_sample_polygon():
    # Known sample: AABB ≈ (0.2559, 0.4004, 0.3340, 0.6035) — agrees with the
    # 0-100-grid gt string within quantisation error.
    box = corners_aabb(SAMPLE["obj_corner"])
    assert box == (0.255859375, 0.400390625, 0.333984375, 0.603515625)
    gt = parse_gt_boxes(SAMPLE["ground_truth"])[0]
    assert all(abs(a - b) <= 0.05 for a, b in zip(box, gt))


def test_corners_aabb_rejects_bad_input():
    assert corners_aabb(None) is None
    assert corners_aabb([]) is None
    assert corners_aabb([0.1, 0.2]) is None           # odd length / too short
    assert corners_aabb([1.5, 0.2, 0.3, 0.4]) is None  # outside 0-1


# ----------------------------------------------------------------- full row
def test_convert_row_prefers_gt_string():
    out, status = convert_row(SAMPLE)
    assert status == "ok"
    assert out["images"] == ["P0003_0002.png"]
    assert "The large yellow vehicle" in out["query"]
    assert out["boxes"][0]["bbox"] == [0.25, 0.4, 0.33, 0.6]
    assert out["boxes"][0]["label"] == "vehicle"


def test_convert_row_falls_back_to_corner_aabb():
    row = dict(SAMPLE, ground_truth="")
    out, status = convert_row(row)
    assert "corner AABB" in status
    assert out["boxes"][0]["bbox"][0] == round(0.255859375, 6)


def test_convert_row_flags_mismatch_beyond_tolerance():
    # gt string disagrees wildly with the polygon → corner AABB wins + warning
    row = dict(SAMPLE, ground_truth="{<80><80><90><90>}")
    out, status = convert_row(row)
    assert "mismatch" in status
    assert out["boxes"][0]["bbox"][0] == round(0.255859375, 6)


def test_convert_row_skips_unusable_rows():
    out, _ = convert_row(dict(SAMPLE, ground_truth="", obj_corner=None))
    assert out is None
    out, _ = convert_row(dict(SAMPLE, question=""))
    assert out is None
