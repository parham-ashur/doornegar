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

        # Edge: 5-1 at total=6 is NOT a small cluster → falls to pct rule (17% > 10%)
        (5, 1, True, True, False, None),

        # Balanced small clusters
        (1, 1, True, True, False, None),              # 1-1 equal
        (2, 2, True, True, False, None),              # 2-2 equal

        # Percentage rule on larger clusters
        (10, 2, True, True, False, None),             # 17% minority — not a blindspot
        (11, 1, True, True, True, "state_only"),      # 8% minority — blindspot
        (100, 5, True, True, True, "state_only"),     # ~5% minority

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


def test_small_cluster_is_inclusive_of_five():
    """Total of 5 with a 4-1 split is a blindspot; total of 6 with 5-1 is not."""
    b5, _ = _compute_blindspot(state_count=4, diaspora_count=1, covered_by_state=True, covered_by_diaspora=True)
    b6, _ = _compute_blindspot(state_count=5, diaspora_count=1, covered_by_state=True, covered_by_diaspora=True)
    assert b5 is True
    assert b6 is False


def test_ten_percent_threshold_is_strict():
    """10% exactly is not a blindspot (strict <); 9% is."""
    b10, _ = _compute_blindspot(state_count=9, diaspora_count=1, covered_by_state=True, covered_by_diaspora=True)
    b9, _ = _compute_blindspot(state_count=10, diaspora_count=1, covered_by_state=True, covered_by_diaspora=True)
    assert b10 is False  # 10% diaspora, strict <10 fails
    assert b9 is True    # ~9% diaspora, strict <10 passes
