"""Unit tests for the homepage same-event de-dup core (Parham 2026-06-16).

Mirrors the live calibration: the 3 Iran-US deal clusters must group into
ONE, while the related-but-distinct "US strikes" story (high title overlap,
low cosine) and a distinct Lebanon story (cosine anomaly, no shared tokens)
must each stay separate. Precision over recall.
"""
import math
from datetime import datetime, timezone

from app.services.homepage_dedup import (
    normalize_title_tokens, centroid_cosine, token_jaccard,
    plan_dedup, DedupRow, DEDUP_COSINE_MIN,
)


DT = datetime(2026, 6, 16, tzinfo=timezone.utc)


def _row(id, title, centroid, prio=0, ts=10.0, ac=20):
    return DedupRow(id=id, title_fa=title, centroid=list(centroid),
                    priority=prio, trending_score=ts, last_updated_at=DT, article_count=ac)


# ---- primitives ----

def test_normalize_unifies_glyphs_and_drops_stopwords():
    toks = normalize_title_tokens("توافق ايران و آمریكا در سوئيس")  # arabic ي/ك
    assert "ایران" in toks and "آمریکا" in toks and "سوئیس" in toks
    assert "و" not in toks and "در" not in toks   # stopwords gone

def test_cosine_basic():
    assert abs(centroid_cosine([1, 0], [1, 0]) - 1.0) < 1e-9
    assert abs(centroid_cosine([1, 0], [0, 1]) - 0.0) < 1e-9
    assert centroid_cosine([], [1, 0]) is None
    assert centroid_cosine([0, 0], [1, 0]) is None     # degenerate
    assert centroid_cosine([1, 0, 0], [1, 0]) is None  # length mismatch

def test_jaccard():
    assert token_jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert token_jaccard({"a"}, {"b"}) == 0.0
    assert token_jaccard(set(), {"a"}) == 0.0


# ---- pin-anchored dedup (the calibration, reproduced) ----

def _deal_set():
    # 4D geometry: deal cluster lives near axis e1 (mutual cos >= 0.81); the
    # "US strikes" story sits mostly on e4 (cos ~0.585 to the pinned hero, and
    # < 0.64 to every deal story); the Lebanon anomaly is identical to the hero
    # centroid (cos 1.0) but shares no title tokens.
    hero = _row("hero", "توافق ایران آمریکا پایان جنگ امضای جمعه سوئیس", [1, 0, 0, 0], prio=50, ts=18, ac=60)
    d1 = _row("d1", "توافق ایران آمریکا سوئیس جزئیات بندها واکنش", [0.9, 0.4359, 0, 0], prio=0, ts=54, ac=43)
    d2 = _row("d2", "توافق آتش‌بس ایران آمریکا نقش رسانه‌ها", [0.9, 0, 0.4359, 0], prio=0, ts=30, ac=20)
    us = _row("us", "حملات ایران آمریکا ترامپ توافق قریب‌الوقوع", [0.585, 0, 0, 0.811], prio=-50, ts=13, ac=18)
    leb = _row("leb", "حملات اسرائیل لبنان کشته زخمی", [1, 0, 0, 0], prio=0, ts=30, ac=22)
    return hero, d1, d2, us, leb

def test_pin_anchored_hides_only_direct_deal_dupes():
    hero, d1, d2, us, leb = _deal_set()
    plans = plan_dedup([hero, d1, d2, us, leb])
    assert len(plans) == 1
    rep, hide = plans[0]
    assert rep.id == "hero"                       # the pin is the representative
    assert {h.id for h in hide} == {"d1", "d2"}   # only direct same-event non-pins

def test_us_strikes_not_hidden_cosine_gate():
    """Shares 3 tokens with the pinned hero but cosine 0.585 < 0.64 → kept."""
    hero, d1, d2, us, leb = _deal_set()
    plans = plan_dedup([hero, us])
    assert plans == []

def test_cosine_anomaly_not_hidden_shared_token_guard():
    """Lebanon story has a degenerate cosine=1.0 to the pinned hero but shares
    NO content tokens — the min-shared/jaccard guard keeps it."""
    hero, d1, d2, us, leb = _deal_set()
    assert leb.centroid == hero.centroid  # the anomaly
    plans = plan_dedup([hero, leb])
    assert plans == []

def test_no_pin_means_no_dedup():
    """Without a pinned anchor, NOTHING is hidden — even three mutually-similar
    deal-like stories (the dry-run lesson: don't auto-merge un-pinned stories)."""
    a = _row("a", "توافق ایران آمریکا پایان جنگ سوئیس امضا", [1, 0, 0, 0], prio=0)
    b = _row("b", "توافق ایران آمریکا سوئیس جزئیات بندها", [0.9, 0.4359, 0, 0], prio=0)
    c = _row("c", "توافق ایران آمریکا بندها واکنش استقبال", [0.85, 0.527, 0, 0], prio=0)
    assert plan_dedup([a, b, c]) == []

def test_never_hides_another_pin():
    """A second pinned story that's same-event is NOT hidden — the operator
    pinned both on purpose."""
    hero = _row("hero", "توافق ایران آمریکا پایان جنگ سوئیس", [1, 0, 0, 0], prio=50, ts=99)
    pin2 = _row("pin2", "توافق ایران آمریکا سوئیس جزئیات بندها", [0.9, 0.4359, 0, 0], prio=50, ts=10)
    d1 = _row("d1", "توافق ایران آمریکا سوئیس واکنش بین‌المللی", [0.88, 0.475, 0, 0], prio=0, ts=40)
    plans = plan_dedup([hero, pin2, d1])
    # hero wins as anchor (higher ts among pins); only the non-pin d1 is hidden
    assert len(plans) == 1
    rep, hide = plans[0]
    assert rep.id == "hero"
    assert [h.id for h in hide] == ["d1"]

def test_distinct_war_stories_not_hidden():
    """Pinned deal hero must NOT absorb genuinely distinct war stories that
    share only a generic token or sit below the cosine gate."""
    hero = _row("hero", "توافق ایران آمریکا پایان جنگ سوئیس امضا", [1, 0, 0, 0], prio=50)
    leb = _row("leb", "حملات اسرائیل به جنوب لبنان؛ ۸ کشته", [0, 1, 0, 0], prio=0)
    strike = _row("strike", "حملات موشکی ایران به ۱۸ هدف نظامی آمریکا", [0.55, 0, 0.83, 0], prio=0)
    plans = plan_dedup([hero, leb, strike])
    assert plans == []

def test_generic_token_overlap_alone_not_hidden():
    """The 2026-06-16 dry-run failure mode: a war-strike story with HIGH
    cosine to the diffuse pinned deal hero but sharing only generic actor
    tokens {ایران, آمریکا} must NOT be hidden — it needs an EVENT-specific
    shared token (توافق/امضا/سوئیس…)."""
    hero = _row("hero", "توافق ایران آمریکا پایان جنگ سوئیس امضا", [1, 0, 0, 0], prio=50)
    strike = _row("strike", "حملات هوایی آمریکا به ایران؛ ۴۹ موشک تاماهاوک شلیک شد",
                  [0.95, 0.31, 0, 0], prio=0)   # cosine ~0.95 >= 0.64
    assert plan_dedup([hero, strike]) == []
    # but a real deal fragment sharing «توافق»+«سوئیس» at the same cosine IS hidden
    frag = _row("frag", "توافق ایران آمریکا در سوئیس؛ جزئیات بندها", [0.95, 0.31, 0, 0], prio=0)
    plans = plan_dedup([hero, frag])
    assert len(plans) == 1 and [h.id for h in plans[0][1]] == ["frag"]
