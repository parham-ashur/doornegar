"""Unit tests for blindspot detection logic.

Pure function — no DB, no LLM, no network.
"""

import pytest

from app.services.clustering import _compute_blindspot


@pytest.mark.parametrize(
    "state,diaspora,cs,cd,expected_b,expected_t",
    [
        # Small-cluster rule (total < 6)
        (2, 1, True, True, True, "state_only"),       # 2-1 split, diaspora is lone voice
        (1, 2, True, True, True, "diaspora_only"),    # 1-2 split, state is lone voice
        (3, 1, True, True, True, "state_only"),       # 3-1 small cluster
        (1, 3, True, True, True, "diaspora_only"),    # 1-3 small cluster
        (4, 1, True, True, True, "state_only"),       # 4-1 small cluster (total=5)

        # Edge: 5-1 at total=6 is NOT a small cluster → falls to pct rule (17% < 20% → blindspot)
        (5, 1, True, True, True, "state_only"),

        # Balanced small clusters
        (1, 1, True, True, False, None),              # 1-1 equal
        (2, 2, True, True, False, None),              # 2-2 equal

        # Percentage rule on larger clusters (minority < 20%)
        (10, 2, True, True, True, "state_only"),      # 17% — flagged under 20% rule
        (11, 1, True, True, True, "state_only"),      # 8% — flagged
        (100, 5, True, True, True, "state_only"),     # ~5% — flagged
        (8, 2, True, True, False, None),              # 20% exactly — strict < fails, balanced
        (7, 3, True, True, False, None),              # 30% — clearly balanced

        # One side entirely absent
        (5, 0, True, False, True, "state_only"),      # diaspora absent
        (0, 3, False, True, True, "diaspora_only"),   # state absent

        # Empty input
        (0, 0, False, False, False, None),
    ],
)
def test_blindspot_rules(state, diaspora, cs, cd, expected_b, expected_t):
    """Verify _compute_blindspot returns correct (is_blindspot, type) tuple."""
    is_b, btype = _compute_blindspot(
        state_count=state,
        diaspora_count=diaspora,
        covered_by_state=cs,
        covered_by_diaspora=cd,
    )
    assert (is_b, btype) == (expected_b, expected_t)


def test_small_cluster_boundary():
    """4-1 (total=5) caught by the small-cluster rule; 5-1 (total=6) caught
    by the 20% percentage rule (17% minority). Both blindspots."""
    b5, _ = _compute_blindspot(state_count=4, diaspora_count=1, covered_by_state=True, covered_by_diaspora=True)
    b6, _ = _compute_blindspot(state_count=5, diaspora_count=1, covered_by_state=True, covered_by_diaspora=True)
    assert b5 is True
    assert b6 is True


def test_twenty_percent_threshold_is_strict():
    """20% exactly is balanced; 17% (10+2) is a blindspot."""
    b20, _ = _compute_blindspot(state_count=8, diaspora_count=2, covered_by_state=True, covered_by_diaspora=True)
    b17, _ = _compute_blindspot(state_count=10, diaspora_count=2, covered_by_state=True, covered_by_diaspora=True)
    assert b20 is False  # 20% exactly — strict < fails
    assert b17 is True   # ~17% — flagged as blindspot
