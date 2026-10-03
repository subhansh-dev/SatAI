"""
SatAI — Answer-language handling.

English is the default: when the query is written in Latin script (plain
English), every VLM tool prompt carries an unambiguous "Answer in English"
instruction that names no other language — so the model cannot latch onto
e.g. Hindi and reply in the wrong language.

Queries written in a non-Latin script (Hindi, Gujarati, Bengali, ...) keep
matching the user's language, and the controller records a language note in
the trace for those.

This module provides:
- script detection (Devanagari, Gujarati, Bengali, Tamil, ... Arabic, CJK, Hangul)
- language_hint(query): per-query instruction picked from the above rule.
- LANG_HINT: legacy match-the-user hint (kept for non-Latin queries).

Algorithmic tools (spectral_index, quantity band-math path) emit numeric /
English template output by design — figures are language-neutral and the
execution trace records the method.
"""
from __future__ import annotations

import re

ENGLISH_HINT = (
    "Answer in English. Keep established technical terms "
    "(NDVI, NDWI, NDBI, SAR, GSD, hectare, built-up, land cover) unchanged."
)

LANG_HINT = (
    "Answer in the language the user wrote their question (Hindi, Gujarati, "
    "Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Arabic, etc. — "
    "match their language and script); keep established technical terms "
    "(NDVI, NDWI, NDBI, SAR, GSD, hectare, built-up, land cover) unchanged."
)


def language_hint(query: str) -> str:
    """Answer-language instruction for this query.

    Latin-script (English) queries get a categorical English-only
    instruction; non-Latin-script queries get the match-the-user hint.
    """
    if is_non_latin(query):
        return LANG_HINT
    return ENGLISH_HINT

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
