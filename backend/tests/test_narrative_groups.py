"""Tests for narrative_group classification + percentage normalization.

Pure function — no DB, no LLM. The parameterized case list mirrors the
classification table in plan `for-narrative-and-bias-nested-corbato.md`.
If you reclassify a source, update both that table and this test.
"""

from types import SimpleNamespace

import pytest

from app.services.narrative_groups import (
    NARRATIVE_GROUPS_ORDER,
    counts_to_percentages,
    narrative_group,
    side_of,
)


def _source(production_location, factional_alignment=None, state_alignment=None):
    return SimpleNamespace(
        production_location=production_location,
        factional_alignment=factional_alignment,
        state_alignment=state_alignment,
    )


# ─── 20 current sources, expected classification ───────────────────────

CURRENT_SOURCES = [
    # (slug, production_location, factional_alignment, state_alignment, expected_group)
    # درون‌مرزی — اصول‌گرا (5)
    ("tasnim",        "inside_iran",  "hardline",     "state",       "principlist"),
    ("press-tv",      "inside_iran",  "hardline",     "state",       "principlist"),
    ("fars-news",     "inside_iran",  "hardline",     "state",       "principlist"),
    ("mehr-news",     "inside_iran",  "principlist",  "semi_state",  "principlist"),
    ("tabnak",        "inside_iran",  "principlist",  "semi_state",  "principlist"),
    # درون‌مرزی — اصلاح‌طلب (3)
    ("isna",          "inside_iran",  "moderate",     "semi_state",  "reformist"),
    ("khabar-online", "inside_iran",  "moderate",     "semi_state",  "reformist"),
    ("etemad-online", "inside_iran",  "reformist",    "independent", "reformist"),
    # برون‌مرزی — میانه‌رو (10)
    ("bbc-persian",      "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    ("dw-persian",       "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    ("euronews-persian", "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    ("rfi-farsi",        "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    ("radio-farda",      "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    ("voa-farsi",        "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    ("iranwire",         "outside_iran", None,         "independent", "moderate_diaspora"),
    ("zeitoons",         "outside_iran", "reformist",  "independent", "moderate_diaspora"),
    ("hrana",            "outside_iran", None,         "independent", "moderate_diaspora"),
    ("radio-zamaneh",    "outside_iran", None,         "diaspora",    "moderate_diaspora"),
    # برون‌مرزی — رادیکال (2)
    ("iran-international", "outside_iran", "opposition", "diaspora", "radical_diaspora"),
    ("kayhan-london",      "outside_iran", "monarchist", "diaspora", "radical_diaspora"),
]


@pytest.mark.parametrize(
    "slug,loc,faction,state_align,expected",
    CURRENT_SOURCES,
    ids=[s[0] for s in CURRENT_SOURCES],
)
def test_existing_sources_classify_as_planned(slug, loc, faction, state_align, expected):
    src = _source(loc, faction, state_align)
    assert narrative_group(src) == expected


# ─── Edge cases ────────────────────────────────────────────────────────


def test_null_factional_alignment_outside_defaults_to_moderate():
    assert narrative_group(_source("outside_iran", None, "diaspora")) == "moderate_diaspora"


def test_null_factional_alignment_inside_defaults_to_reformist():
    # No faction tag + not state_alignment=state → reformist
    assert narrative_group(_source("inside_iran", None, "independent")) == "reformist"


def test_inside_left_faction_classifies_reformist():
    # `left` is a valid factional_alignment value but doesn't appear in
    # any current source. It should land in reformist (i.e. not-principlist).
    assert narrative_group(_source("inside_iran", "left", "independent")) == "reformist"


def test_outside_reformist_classifies_moderate_not_reformist():
    # A diaspora outlet tagged reformist (like Zeitoons) is moderate,
    # not a new "outside reformist" group — we only have 2 outside subgroups.
    assert narrative_group(_source("outside_iran", "reformist", "independent")) == "moderate_diaspora"


def test_state_alignment_state_forces_principlist_even_without_faction():
    # If a source is tagged state_alignment=state but has no factional_alignment
    # populated, still classify as principlist.
    assert narrative_group(_source("inside_iran", None, "state")) == "principlist"


def test_radical_faction_outside_classifies_radical():
    # Forward-looking: if we ever use "radical" as a factional_alignment,
    # it maps to radical_diaspora on the outside side.
    assert narrative_group(_source("outside_iran", "radical", "diaspora")) == "radical_diaspora"


# ─── side_of ───────────────────────────────────────────────────────────


def test_side_of_maps_each_group_correctly():
    assert side_of("principlist") == "inside"
    assert side_of("reformist") == "inside"
    assert side_of("moderate_diaspora") == "outside"
    assert side_of("radical_diaspora") == "outside"


# ─── counts_to_percentages ─────────────────────────────────────────────


def test_all_zeros_returns_all_zeros():
    counts = {g: 0 for g in NARRATIVE_GROUPS_ORDER}
    assert counts_to_percentages(counts) == counts


def test_percentages_sum_to_100():
    counts = {"principlist": 3, "reformist": 2, "moderate_diaspora": 1, "radical_diaspora": 1}
    pct = counts_to_percentages(counts)
    assert sum(pct.values()) == 100


def test_exact_quartile_split():
    counts = {"principlist": 1, "reformist": 1, "moderate_diaspora": 1, "radical_diaspora": 1}
    pct = counts_to_percentages(counts)
    assert pct == {"principlist": 25, "reformist": 25, "moderate_diaspora": 25, "radical_diaspora": 25}


def test_single_group_dominant():
    counts = {"principlist": 10, "reformist": 0, "moderate_diaspora": 0, "radical_diaspora": 0}
    pct = counts_to_percentages(counts)
    assert pct == {"principlist": 100, "reformist": 0, "moderate_diaspora": 0, "radical_diaspora": 0}


def test_missing_keys_treated_as_zero():
    # Partial dicts should not crash; missing groups contribute 0.
    counts = {"principlist": 3, "reformist": 1}  # omitted outside groups
    pct = counts_to_percentages(counts)  # type: ignore[arg-type]
    assert sum(pct.values()) == 100
    assert pct["moderate_diaspora"] == 0
    assert pct["radical_diaspora"] == 0
