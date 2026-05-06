"""Tripwire tests for the worldview-digest grounding floor.

The grounding floor is what makes the four worldview cards trustworthy
— every published belief must be cited evidence, not LLM speculation.
But the floor is also the reason the radical_diaspora card was empty
on 2026-05-06: with only 3 tracked sources, requiring ≥2 distinct
sources per belief is structurally near-impossible if the LLM cites
articles from a single dominant outlet.

These tests pin the small-bundle relaxation so it can't silently
regress.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.services.worldview_digest import (
    BundleAggregate,
    MIN_ARTICLES_PER_BELIEF,
    MIN_SOURCES_PER_BELIEF,
    SMALL_BUNDLE_MIN_SOURCES_PER_BELIEF,
    SMALL_BUNDLE_SOURCE_CAP,
    _validate_and_trim,
)


def _make_agg(source_count: int) -> BundleAggregate:
    """A minimal aggregate where article_to_source maps every UUID we'll
    use in tests to a deterministic source id (article-i → source-(i%N))."""
    article_to_source = {
        f"00000000-0000-0000-0000-{i:012d}": f"src-{i % source_count}"
        for i in range(20)
    }
    return BundleAggregate(
        bundle="radical_diaspora",
        window_start=datetime(2026, 4, 27, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 4, tzinfo=timezone.utc),
        article_count=20,
        source_count=source_count,
        article_to_source=article_to_source,
    )


def _make_belief(article_count: int, ids: list[str]) -> dict:
    return {
        "text": "test claim",
        "article_count": article_count,
        "example_article_ids": ids,
    }


class TestGroundingFloorSmallBundleRelaxation:
    """Small bundles (≤3 sources) drop the per-belief diversity floor
    from 2 → 1. This is the fix that unblocked radical_diaspora's
    silently-empty card."""

    def test_constant_values_match_2026_05_06_decision(self):
        """Pin the constants so a future drop-in 'cleanup' can't quietly
        re-tighten the floor and break radical again."""
        assert MIN_ARTICLES_PER_BELIEF == 3
        assert MIN_SOURCES_PER_BELIEF == 2
        assert SMALL_BUNDLE_SOURCE_CAP == 3
        assert SMALL_BUNDLE_MIN_SOURCES_PER_BELIEF == 1

    def test_small_bundle_3_sources_keeps_single_source_belief(self):
        """A bundle with 3 sources is small. A belief citing 3 articles
        from a single source must SURVIVE the floor — that's the
        relaxation."""
        agg = _make_agg(source_count=3)
        # All three article_ids map to the same source (i % 3 collisions
        # with source-0 if we pick 0, 3, 6).
        ids = [f"00000000-0000-0000-0000-{i:012d}" for i in (0, 3, 6)]
        parsed = {"core_beliefs": [_make_belief(article_count=3, ids=ids)]}
        synthesis, evidence = _validate_and_trim(parsed, agg)
        assert len(synthesis["core_beliefs"]) == 1, (
            "Single-source belief in a 3-source bundle must pass the "
            "relaxed floor — this is the radical_diaspora unblock."
        )
        assert evidence["core_beliefs:0"] == ids

    def test_normal_bundle_5_sources_still_requires_2_sources(self):
        """A 5-source bundle is NOT small. The full diversity floor
        applies — single-source beliefs must still be dropped."""
        agg = _make_agg(source_count=5)
        # All ids hit source-0 because i % 5 == 0 for i in (0, 5, 10).
        ids = [f"00000000-0000-0000-0000-{i:012d}" for i in (0, 5, 10)]
        parsed = {"core_beliefs": [_make_belief(article_count=3, ids=ids)]}
        synthesis, _ = _validate_and_trim(parsed, agg)
        assert synthesis["core_beliefs"] == [], (
            "Single-source belief in a 5-source bundle must be dropped — "
            "the diversity floor still protects normally-sized bundles."
        )

    def test_article_count_floor_still_enforced_for_small_bundles(self):
        """The relaxation is ONLY on diversity. A small-bundle belief
        with article_count=2 must still be dropped — 3 articles is
        the volume floor, regardless of bundle size."""
        agg = _make_agg(source_count=3)
        ids = [f"00000000-0000-0000-0000-{i:012d}" for i in (0, 1)]
        parsed = {"core_beliefs": [_make_belief(article_count=2, ids=ids)]}
        synthesis, _ = _validate_and_trim(parsed, agg)
        assert synthesis["core_beliefs"] == [], (
            "Small-bundle relaxation only drops the source floor; "
            "the article-count floor (≥3) is still enforced."
        )

    def test_hallucinated_uuids_dropped_for_small_bundles_too(self):
        """If the LLM cites UUIDs that don't appear in the bundle's
        input data, the belief must be dropped — relaxation doesn't
        admit hallucinations."""
        agg = _make_agg(source_count=3)
        bogus_ids = [
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        ]
        parsed = {"core_beliefs": [_make_belief(article_count=3, ids=bogus_ids)]}
        synthesis, _ = _validate_and_trim(parsed, agg)
        assert synthesis["core_beliefs"] == [], (
            "Hallucinated UUIDs must be dropped even for small bundles "
            "— evidence chain must point to real ingested articles."
        )

    def test_2_source_bundle_treated_as_small(self):
        """Edge: a bundle with exactly 2 sources is also small.
        Single-source beliefs survive, just like the 3-source case."""
        agg = _make_agg(source_count=2)
        ids = [f"00000000-0000-0000-0000-{i:012d}" for i in (0, 2, 4)]
        parsed = {"core_beliefs": [_make_belief(article_count=3, ids=ids)]}
        synthesis, _ = _validate_and_trim(parsed, agg)
        assert len(synthesis["core_beliefs"]) == 1
