"""Option A (2026-06-25): stale-frozen-homepage canary threshold logic.

The freeze-cliff condition: the homepage is frozen-dominated AND fresh
clusterable coverage is orphaning AND no live pinned hero exists. Seeding +
pinning a hero (live_hero>=1) must clear it — that's the whole point.
"""
from app.api.v1.admin import (
    _stale_homepage_status,
    STALE_HP_FROZEN_SHARE,
    STALE_HP_MIN_FRESH_ORPHAN,
)


def test_warns_on_freeze_cliff_condition():
    # ≥80% frozen, fresh coverage orphaning, no live hero → warn
    assert _stale_homepage_status(0.95, 40, 0) == "warn"
    assert _stale_homepage_status(STALE_HP_FROZEN_SHARE, STALE_HP_MIN_FRESH_ORPHAN, 0) == "warn"


def test_live_pinned_hero_clears_it():
    # A pinned live hero exists → ok even when everything else is frozen/orphaning.
    assert _stale_homepage_status(0.99, 100, 1) == "ok"


def test_ok_when_homepage_not_frozen_dominated():
    assert _stale_homepage_status(0.50, 100, 0) == "ok"


def test_ok_when_no_fresh_coverage_orphaning():
    # All frozen but nothing fresh waiting → not the freeze-cliff (quiet news).
    assert _stale_homepage_status(0.95, 0, 0) == "ok"
    assert _stale_homepage_status(0.95, STALE_HP_MIN_FRESH_ORPHAN - 1, 0) == "ok"


def test_zero_homepage_is_ok():
    # Empty homepage (0/0 → share 0.0) must not warn (no division blow-up upstream).
    assert _stale_homepage_status(0.0, 50, 0) == "ok"
