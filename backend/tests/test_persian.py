"""Unit tests for Persian text normalization.

No DB / no LLM. Guards against regression in a convention that CLAUDE.md
calls out as load-bearing: "Persian text MUST be normalized before any
comparison or storage".
"""

import pytest

from app.nlp.persian import normalize


def test_normalize_empty_returns_empty():
    assert normalize("") == ""
    assert normalize(None) == ""  # type: ignore[arg-type]


def test_normalize_maps_arabic_kaf_to_persian_kaf():
    """ك (U+0643 Arabic kaf) must become ک (U+06A9 Persian kaf)."""
    arabic_kaf = "كتاب"
    out = normalize(arabic_kaf)
    # Either hazm or the fallback branch rewrites it — both must produce Persian kaf.
    assert "\u0643" not in out
    assert "\u06A9" in out


def test_normalize_maps_arabic_yeh_to_persian_yeh():
    """ي (U+064A Arabic yeh) must become ی (U+06CC Persian yeh)."""
    arabic_yeh = "ايران"
    out = normalize(arabic_yeh)
    assert "\u064A" not in out
    assert "\u06CC" in out


def test_normalize_collapses_whitespace():
    assert normalize("سلام    دنیا\n\n") == "سلام دنیا"


def test_normalize_is_idempotent():
    """Running normalize twice must equal running it once."""
    text = "كتاب ايران  با فاصله‌های اضافی"
    once = normalize(text)
    twice = normalize(once)
    assert once == twice
