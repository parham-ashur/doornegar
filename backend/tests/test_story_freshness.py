"""Risk-prioritized tests for `app/services/story_freshness.py`.

Pure-function module → no mocking, no DB. Tests pin the
update-signal contract that drives the orange "بروزرسانی" badge.

Coverage focus:
- Dispute / coverage / new-articles thresholds and their precedence
- Reader-facing copy (the 2026-05-05 dispute-number-removed change)
- Edge phrasing for one-sided stories (no parenthetical baseline)

Run: `cd backend && pytest tests/test_story_freshness.py -v`
"""

from app.services.story_freshness import (
    DISPUTE_DELTA_THRESHOLD,
    COVERAGE_PCT_DELTA_THRESHOLD,
    NEW_ARTICLES_THRESHOLD,
    build_snapshot,
    compute_update_signal,
    _bias_hash,
)


def _signal(*, dispute=None, inside=0, outside=0, articles=0, bias_text=None, snapshot=None):
    """Test helper that names every keyword arg explicitly so each
    test reads as a story rather than a tuple of magic numbers."""
    return compute_update_signal(
        current_article_count=articles,
        current_dispute_score=dispute,
        current_inside_pct=inside,
        current_outside_pct=outside,
        current_bias_explanation_fa=bias_text,
        snapshot=snapshot,
    )


# ═════════════════════════════════════════════════════════════════════
# 1. No-snapshot path — first day after a story appears
# ═════════════════════════════════════════════════════════════════════

class TestNoSnapshotMeansNoUpdate:
    """A freshly-created story has no snapshot yet. Returning
    `has_update=True` here would flash the orange badge on every brand
    new story, which is wrong: there's nothing to compare to."""

    def test_none_snapshot_returns_no_update(self):
        assert _signal(snapshot=None) == {
            "has_update": False, "kind": None, "reason_fa": None,
        }

    def test_non_dict_snapshot_returns_no_update(self):
        # Defensive — the JSONB column could in theory contain a list
        # or string from a corrupted write. Don't crash, don't badge.
        assert _signal(snapshot="not-a-dict")["has_update"] is False
        assert _signal(snapshot=[])["has_update"] is False


# ═════════════════════════════════════════════════════════════════════
# 2. Dispute-delta branch
# ═════════════════════════════════════════════════════════════════════

class TestDisputeBranch:
    """The dispute_score branch is the highest-precedence signal —
    fires when narratives become more or less contested by ≥0.2."""

    def test_increase_above_threshold_fires(self):
        sig = _signal(
            dispute=0.8,
            snapshot={"dispute_score": 0.5},
        )
        assert sig["has_update"] is True
        assert sig["kind"] == "dispute"
        assert "افزایش" in sig["reason_fa"]

    def test_decrease_above_threshold_fires(self):
        sig = _signal(
            dispute=0.4,
            snapshot={"dispute_score": 0.9},
        )
        assert sig["has_update"] is True
        assert sig["kind"] == "dispute"
        assert "کاهش" in sig["reason_fa"]

    def test_below_threshold_does_not_fire(self):
        # 0.1 delta is just under the 0.2 floor.
        sig = _signal(
            dispute=0.6,
            snapshot={"dispute_score": 0.5},
        )
        assert sig["has_update"] is False, (
            "Sub-threshold dispute moves must not flash a badge — "
            "noisy day-to-day jitter would burn through user trust."
        )

    def test_threshold_constant_pinned_at_0_2(self):
        # Anchor the threshold so accidentally lowering it (and flooding
        # the badge with noise) fails loudly.
        assert DISPUTE_DELTA_THRESHOLD == 0.2

    def test_reason_has_no_numbers(self):
        """2026-05-05 product decision: dispute_score is a 0-1 abstract
        metric readers have no intuition for. Reason text shows
        direction only — no parenthetical (1.0 ← 0.6).

        This regression test guards commit 3d0b986. Re-introducing the
        numeric parenthetical is a UX regression."""
        sig = _signal(dispute=0.8, snapshot={"dispute_score": 0.4})
        # No Persian or Latin digits should appear in the dispute reason.
        for ch in sig["reason_fa"]:
            assert not ch.isdigit(), (
                f"Dispute reason must not contain digits "
                f"(got {sig['reason_fa']!r}). dispute_score is opaque "
                f"to readers — direction is the signal. See commit 3d0b986."
            )
        assert "←" not in sig["reason_fa"]
        assert "(" not in sig["reason_fa"]

    def test_missing_current_dispute_falls_through(self):
        """A story without a current dispute_score (e.g. bias not yet
        scored) shouldn't badge on the dispute branch — but other
        branches can still fire."""
        sig = _signal(
            dispute=None,
            snapshot={"dispute_score": 0.5, "article_count": 0},
            articles=0,
        )
        # No dispute branch fires; coverage/articles also no signal.
        assert sig["kind"] != "dispute"


# ═════════════════════════════════════════════════════════════════════
# 3. Coverage-shift branch
# ═════════════════════════════════════════════════════════════════════

class TestCoverageShiftBranch:
    """Coverage shift fires when inside or outside-pct moves ≥15 pp.
    The one-sided edges (0 or 100) get phrase-only copy — no
    parenthetical numbers — so the reader doesn't read it as a
    precise historical claim."""

    def test_inside_started_phrasing_when_was_zero(self):
        sig = _signal(
            inside=46, outside=54,
            snapshot={"inside_pct": 0, "outside_pct": 100},
        )
        assert sig["has_update"] is True
        assert sig["kind"] == "coverage_shift"
        assert sig["reason_fa"] == "پوشش درون‌مرزی آغاز شد", (
            "When snap_inside == 0, must use 'آغاز شد' phrase without "
            "numbers — '0٪ ← 46٪' would imply we tracked the precise "
            "historical baseline, which we don't."
        )

    def test_outside_started_phrasing_when_was_zero(self):
        sig = _signal(
            inside=40, outside=60,
            snapshot={"inside_pct": 100, "outside_pct": 0},
        )
        # outside_delta = 60, inside_delta = 60 → tie → outside grows
        # from 0 path.
        assert sig["kind"] == "coverage_shift"
        assert "آغاز شد" in sig["reason_fa"]

    def test_nominal_increase_includes_persian_percentages(self):
        sig = _signal(
            inside=70, outside=30,
            snapshot={"inside_pct": 50, "outside_pct": 50},
        )
        assert sig["kind"] == "coverage_shift"
        # Persian digits + Persian percent sign required.
        assert "٪" in sig["reason_fa"]
        # Latin digits MUST NOT leak — display layer is Persian throughout.
        for ch in sig["reason_fa"]:
            assert not (ch.isdigit() and ch in "0123456789"), (
                f"Persian display must not leak Latin digits: "
                f"{sig['reason_fa']!r}"
            )

    def test_below_threshold_does_not_fire(self):
        # 10 pp shift is under COVERAGE_PCT_DELTA_THRESHOLD (15).
        sig = _signal(
            inside=60, outside=40,
            snapshot={"inside_pct": 50, "outside_pct": 50, "dispute_score": None},
        )
        assert sig["has_update"] is False

    def test_threshold_constant_pinned_at_15(self):
        assert COVERAGE_PCT_DELTA_THRESHOLD == 15

    def test_drop_to_zero_uses_retreat_phrasing(self):
        """The 'کمرنگ شد' (faded) branch fires when one side drops to
        zero while the OTHER side didn't grow — the missing percentage
        went to a third subgroup (e.g. independent/unspecified). The
        prior 'inside ↔ outside' swap branches handle pure flips."""
        # inside drops 50 → 0; outside stays at 50; missing 50 went to
        # a third bucket the snapshot doesn't track. inside_delta = 50
        # qualifies the 15pp threshold.
        sig = _signal(
            inside=0, outside=50,
            snapshot={"inside_pct": 50, "outside_pct": 50},
        )
        assert sig["kind"] == "coverage_shift"
        assert "کمرنگ شد" in sig["reason_fa"], (
            f"When inside drops to 0 and outside didn't grow, must use "
            f"'کمرنگ شد' (faded) phrase — got {sig['reason_fa']!r}."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. New-articles branch (lowest precedence)
# ═════════════════════════════════════════════════════════════════════

class TestNewArticlesBranch:
    """New-articles fires only when BOTH conditions hold:
      (a) at least NEW_ARTICLES_THRESHOLD new articles since snapshot
      (b) bias_explanation_fa was actually rewritten

    Either alone is not enough — (a) without (b) means repetitive
    pile-on coverage; (b) without (a) is a re-run of the same
    explanation against the same articles."""

    def test_articles_alone_does_not_fire(self):
        # 5 new articles but bias text unchanged.
        sig = _signal(
            articles=10, bias_text="same explanation",
            snapshot={
                "article_count": 5,
                "bias_hash": _bias_hash("same explanation"),
                "dispute_score": None,
            },
        )
        assert sig["has_update"] is False, (
            "Article growth without a bias rewrite is just pile-on "
            "coverage — not worth a badge."
        )

    def test_bias_change_alone_does_not_fire(self):
        # Bias rewrote but no new articles (re-summarize at same count).
        sig = _signal(
            articles=5, bias_text="new explanation",
            snapshot={
                "article_count": 5,
                "bias_hash": _bias_hash("old explanation"),
                "dispute_score": None,
            },
        )
        assert sig["has_update"] is False, (
            "Bias-text rewrite without article growth is just an LLM "
            "re-roll — not worth a badge."
        )

    def test_articles_and_bias_change_fires(self):
        sig = _signal(
            articles=10, bias_text="materially new explanation",
            snapshot={
                "article_count": 5,
                "bias_hash": _bias_hash("old explanation"),
                "dispute_score": None,
            },
        )
        assert sig["has_update"] is True
        assert sig["kind"] == "new_articles"
        assert "مقالهٔ جدید" in sig["reason_fa"]

    def test_articles_threshold_pinned(self):
        assert NEW_ARTICLES_THRESHOLD == 3


# ═════════════════════════════════════════════════════════════════════
# 5. Branch precedence (dispute > coverage > new_articles)
# ═════════════════════════════════════════════════════════════════════

class TestBranchPrecedence:
    """When multiple branches qualify, the most-significant one wins.
    Order is intentional — dispute is the strongest editorial signal,
    coverage is structural, new_articles is the weakest."""

    def test_dispute_beats_coverage(self):
        # Both branches qualify — dispute should win.
        sig = _signal(
            dispute=0.9, inside=70, outside=30,
            snapshot={
                "dispute_score": 0.5,        # +0.4, qualifies
                "inside_pct": 50,            # 20 pp shift, qualifies
                "outside_pct": 50,
            },
        )
        assert sig["kind"] == "dispute"

    def test_coverage_beats_new_articles(self):
        sig = _signal(
            inside=70, outside=30,
            articles=10, bias_text="rewritten",
            snapshot={
                "dispute_score": None,
                "inside_pct": 50,            # 20 pp shift, qualifies
                "outside_pct": 50,
                "article_count": 5,          # +5 with rewrite, qualifies
                "bias_hash": _bias_hash("old"),
            },
        )
        assert sig["kind"] == "coverage_shift"


# ═════════════════════════════════════════════════════════════════════
# 6. Snapshot truncation (build_snapshot stays under JSONB budget)
# ═════════════════════════════════════════════════════════════════════

class TestSnapshotTruncation:
    """`build_snapshot` caps each narrative text at 2000 chars so the
    400-500 stories × snapshot row stays under ~4 MB total. Without
    this cap, a single 100KB bias_explanation could blow the row size
    and slow every snapshot read."""

    def test_long_text_truncated_to_cap(self):
        long = "ا" * 5000
        snap = build_snapshot(
            article_count=10,
            dispute_score=0.5,
            inside_pct=50,
            outside_pct=50,
            bias_explanation_fa=long,
            state_summary_fa=long,
            diaspora_summary_fa=long,
        )
        assert len(snap["bias_text"]) == 2000
        assert len(snap["state_text"]) == 2000
        assert len(snap["diaspora_text"]) == 2000

    def test_short_text_passes_through(self):
        snap = build_snapshot(
            article_count=5,
            dispute_score=0.3,
            inside_pct=40,
            outside_pct=60,
            bias_explanation_fa="کوتاه",
        )
        assert snap["bias_text"] == "کوتاه"

    def test_none_text_stays_none(self):
        snap = build_snapshot(
            article_count=5,
            dispute_score=0.3,
            inside_pct=40,
            outside_pct=60,
            bias_explanation_fa=None,
        )
        assert snap["bias_text"] is None

    def test_bias_hash_round_trips(self):
        # The hash must be stable: same text → same hash, used for
        # the new_articles branch's "bias actually rewrote" check.
        snap = build_snapshot(
            article_count=5,
            dispute_score=0.3,
            inside_pct=40, outside_pct=60,
            bias_explanation_fa="abc",
        )
        assert snap["bias_hash"] == _bias_hash("abc")
        assert snap["bias_hash"] is not None


# ═════════════════════════════════════════════════════════════════════
# 7. _bias_hash defensive nulls
# ═════════════════════════════════════════════════════════════════════

class TestBiasHashNulls:
    def test_none_input(self):
        assert _bias_hash(None) is None

    def test_empty_string(self):
        assert _bias_hash("") is None

    def test_distinct_text_distinct_hash(self):
        # Sanity — a single-char change produces a different hash so
        # the new_articles branch detects rewrites.
        assert _bias_hash("a") != _bias_hash("b")
