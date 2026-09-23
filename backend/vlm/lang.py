"""
SatAI — Multilingual query support (Hindi / Gujarati / Indic + others).

Qwen2.5-VL is multilingual; the pipeline just never told it to answer in the
user's language. This module provides:
- script detection (Devanagari, Gujarati, Bengali, Tamil, ... Arabic, CJK, Hangul)
- LANG_HINT: appended to every VLM tool prompt so answers follow the query's
  language while technical terms (NDVI, SAR, hectare...) stay standard.

Algorithmic tools (spectral_index, quantity band-math path) emit numeric /
English template output by design — figures are language-neutral and the
execution trace records the method.
"""
from __future__ import annotations

import re

LANG_HINT = (
    "Answer in the language the user wrote their question (Hindi, Gujarati, "
    "Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Arabic, etc. — "
    "match their language and script); keep established technical terms "
    "(NDVI, NDWI, NDBI, SAR, GSD, hectare, built-up, land cover) unchanged."
)

# Indic + common non-Latin scripts (BMP ranges)
_NON_LATIN_RE = re.compile(
    "["
    "\u0900-\u097F"   # Devanagari (Hindi, Marathi...)
    "\u0A80-\u0AFF"   # Gujarati
    "\u0980-\u09FF"   # Bengali
    "\u0B80-\u0BFF"   # Tamil
    "\u0C00-\u0C7F"   # Telugu
    "\u0D00-\u0D7F"   # Malayalam
    "\u0A70-\u0A7F"   # Gurmukhi (Punjabi)
    "\u0E00-\u0E7F"   # Thai
    "\u0600-\u06FF"   # Arabic
    "\u0750-\u077F"   # Arabic Supplement
    "\u3040-\u30FF"   # Hiragana / Katakana
    "\u4E00-\u9FFF"   # CJK Unified Ideographs
    "\uAC00-\uD7AF"   # Hangul
    "]"
)


def is_non_latin(text: str) -> bool:
    """True when the text contains characters from a non-Latin script."""
    return bool(_NON_LATIN_RE.search(text or ""))
