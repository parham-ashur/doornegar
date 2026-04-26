"""Daily-change signal for homepage slot rotation.

Parham's rule: a story can stay in the hero / blindspot slot across days
only if its narrative has shifted meaningfully. "Gained new articles" is
not enough — we need a dispute-score move, a coverage-distribution shift,
or a bias-comparison rewrite.

The primitive is `Story.analysis_snapshot_24h`, a JSONB column refreshed
once per nightly maintenance run. At any point during the day we can
compare "right now" to "~20–24h ago" to produce a single `update_signal`
dict that the frontend renders as an orange "بروزرسانی" badge.

Thresholds are intentionally conservative — a tiny dispute-score wobble
doesn't qualify. These are the lines a reasonable reader would notice.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


DISPUTE_DELTA_THRESHOLD = 0.2       # dispute_score moves 0.3 → 0.5 or more
COVERAGE_PCT_DELTA_THRESHOLD = 15   # any subgroup pct shifts 30% → 45% or more
NEW_ARTICLES_THRESHOLD = 3          # at least this many new articles…
# …AND the bias explanation hash changed (so the new articles actually
# moved the narrative, not just piled on repetitive coverage).


def _bias_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def build_snapshot(
    *,
    article_count: int,
    dispute_score: float | None,
    inside_pct: int | None,
    outside_pct: int | None,
    bias_explanation_fa: str | None,
    state_summary_fa: str | None = None,
    diaspora_summary_fa: str | None = None,
) -> dict:
    """Produce the JSON payload stored in `Story.analysis_snapshot_24h`.

    We also keep truncated copies of the three narrative texts so the
    homepage can surface sentence-level "what changed since yesterday"
    deltas in a dedicated به‌روز callout, not just a badge. Cap each
    field at ~2000 chars to keep snapshot JSONB under ~8 KB per row
    (400–500 stories × 8 KB ≈ 4 MB — trivial on Neon).
    """
    _CAP = 2000

    def _trim(s: str | None) -> str | None:
        if not s:
            return None
        return s[:_CAP]

    return {
        "snapshotted_at": datetime.now(timezone.utc).isoformat(),
        "article_count": int(article_count or 0),
        "dispute_score": float(dispute_score) if dispute_score is not None else None,
        "inside_pct": int(inside_pct or 0),
        "outside_pct": int(outside_pct or 0),
        "bias_hash": _bias_hash(bias_explanation_fa),
        "bias_text": _trim(bias_explanation_fa),
        "state_text": _trim(state_summary_fa),
        "diaspora_text": _trim(diaspora_summary_fa),
    }


def compute_update_signal(
    *,
    current_article_count: int,
    current_dispute_score: float | None,
    current_inside_pct: int | None,
    current_outside_pct: int | None,
    current_bias_explanation_fa: str | None,
    snapshot: dict | None,
) -> dict:
    """Compare current live state to the last-nightly snapshot.

    Returns a dict that's JSON-serializable and safe to attach to
    `StoryBrief.update_signal`:

        {
          "has_update": bool,
          "kind": "dispute" | "coverage_shift" | "new_articles" | null,
          "reason_fa": str | null
        }

    When no snapshot exists yet (stories created since the last nightly
    or the first run of the column) we return `has_update=False` so
    first-day behavior is conservative — UI shows no badge until there
    is something meaningful to say.
    """
    if not snapshot or not isinstance(snapshot, dict):
        return {"has_update": False, "kind": None, "reason_fa": None}

    snap_dispute = snapshot.get("dispute_score")
    snap_inside = int(snapshot.get("inside_pct") or 0)
    snap_outside = int(snapshot.get("outside_pct") or 0)
    snap_articles = int(snapshot.get("article_count") or 0)
    snap_bias_hash = snapshot.get("bias_hash")

    # Helpers for Farsi rendering of numbers.
    _FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    def _fa_int(n: int) -> str:
        return str(n).translate(_FA_DIGITS)
    def _fa_one_decimal(x: float) -> str:
        return f"{x:.1f}".translate(_FA_DIGITS)

    # 1) Dispute score shifted materially (narratives became more or
    #    less contested). Phrase the direction for the reader.
    # Arrow direction in RTL: "old ← new" reads naturally right-to-left
    # as "from [old value on right] to [new value on left]".
    if snap_dispute is not None and current_dispute_score is not None:
        delta = current_dispute_score - snap_dispute
        if abs(delta) >= DISPUTE_DELTA_THRESHOLD:
            if delta > 0:
                reason = f"اختلاف روایت‌ها افزایش یافت ({_fa_one_decimal(snap_dispute)} ← {_fa_one_decimal(current_dispute_score)})"
            else:
                reason = f"اختلاف روایت‌ها کاهش یافت ({_fa_one_decimal(snap_dispute)} ← {_fa_one_decimal(current_dispute_score)})"
            return {"has_update": True, "kind": "dispute", "reason_fa": reason}

    # 2) Coverage distribution shifted — a new side started covering or
    #    an old one dropped off. We look at the inside/outside split
    #    because that's what the coverage bar surfaces; sub-subgroup
    #    shifts are noisier.
    #
    # Edge case: when the snapshot was captured at a moment the story
    # was one-sided (snap_inside or snap_outside is 0 or 100), the
    # parenthetical "0٪ ← 46٪" reads like we're asserting the story was
    # previously unknown-to-state coverage, which is often misleading
    # — maybe the snapshot happened to catch a narrow window. Phrase
    # start/stop edges as events ("آغاز شد" / "کمرنگ شد") without the
    # numbers to avoid implying a precise historical baseline.
    cur_inside = int(current_inside_pct or 0)
    cur_outside = int(current_outside_pct or 0)
    inside_delta = abs(cur_inside - snap_inside)
    outside_delta = abs(cur_outside - snap_outside)
    if max(inside_delta, outside_delta) >= COVERAGE_PCT_DELTA_THRESHOLD:
        if cur_inside > snap_inside:
            if snap_inside == 0:
                reason = "پوشش درون‌مرزی آغاز شد"
            else:
                reason = f"پوشش درون‌مرزی تقویت شد ({_fa_int(snap_inside)}٪ ← {_fa_int(cur_inside)}٪)"
        elif cur_outside > snap_outside:
            if snap_outside == 0:
                reason = "پوشش برون‌مرزی آغاز شد"
            else:
                reason = f"پوشش برون‌مرزی تقویت شد ({_fa_int(snap_outside)}٪ ← {_fa_int(cur_outside)}٪)"
        else:
            # One side dropped; phrase as a retreat rather than a swap.
            if cur_inside < snap_inside and cur_inside == 0:
                reason = "پوشش درون‌مرزی کمرنگ شد"
            elif cur_outside < snap_outside and cur_outside == 0:
                reason = "پوشش برون‌مرزی کمرنگ شد"
            else:
                reason = f"توزیع پوشش تغییر کرد ({_fa_int(snap_inside)}٪/{_fa_int(snap_outside)}٪ ← {_fa_int(cur_inside)}٪/{_fa_int(cur_outside)}٪)"
        return {"has_update": True, "kind": "coverage_shift", "reason_fa": reason}

    # 3) Article volume grew and the bias comparison was rewritten —
    #    meaning the new articles actually moved the analytical narrative
    #    rather than piling on repetitive coverage.
    new_articles = current_article_count - snap_articles
    cur_bias_hash = _bias_hash(current_bias_explanation_fa)
    if new_articles >= NEW_ARTICLES_THRESHOLD and cur_bias_hash and cur_bias_hash != snap_bias_hash:
        reason = f"{_fa_int(new_articles)} مقالهٔ جدید و بازنویسی تحلیل سوگیری"
        return {"has_update": True, "kind": "new_articles", "reason_fa": reason}

    return {"has_update": False, "kind": None, "reason_fa": None}


def _parse_analysis_blob(summary_en: str | None) -> dict:
    """Extract the subset of fields we need from the `summary_en` blob."""
    if not summary_en:
        return {}
    try:
        blob = json.loads(summary_en)
    except Exception:
        return {}
    if not isinstance(blob, dict):
        return {}
    return blob


def update_signal_from_story(story: Any) -> dict:
    """Convenience wrapper used by StoryBrief construction.

    Pulls the five live inputs out of the Story ORM object (including the
    `summary_en` JSONB blob), then defers to `compute_update_signal`.
    """
    blob = _parse_analysis_blob(getattr(story, "summary_en", None))
    # StoryBrief-level pct fields are computed elsewhere, but we can pull
    # inside/outside totals from the attached `inside_border_pct` /
    # `outside_border_pct` if the caller already computed them. As a
    # fallback for the ORM path, compute from `narrative_groups` inside
    # the blob (rare — most callers pass these in explicitly via
    # `update_signal_from_fields`).
    inside_pct = getattr(story, "inside_border_pct", 0) or 0
    outside_pct = getattr(story, "outside_border_pct", 0) or 0
    return compute_update_signal(
        current_article_count=getattr(story, "article_count", 0) or 0,
        current_dispute_score=blob.get("dispute_score"),
        current_inside_pct=inside_pct,
        current_outside_pct=outside_pct,
        current_bias_explanation_fa=blob.get("bias_explanation_fa"),
        snapshot=getattr(story, "analysis_snapshot_24h", None),
    )


def _split_sentences(text: str | None) -> list[str]:
    """Split Farsi narrative text into sentences for sentence-level diff.

    Splits on Persian + Latin terminators: «؛» (semicolon — our narrative
    fields use this as the primary bullet separator), «.»، «؟»، «!». Drops
    empty fragments and trims whitespace. Short fragments (< 15 chars) are
    dropped because they tend to be enumerator glue ("یکم،"، "دوم،") that
    isn't useful to highlight as a delta.
    """
    if not text:
        return []
    import re as _re

    parts = _re.split(r"[؛.؟!]\s*", text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 15]


def _normalize_for_compare(s: str) -> str:
    """Reduce a sentence to a compact key for equality testing.

    Strips punctuation, collapses whitespace, removes Farsi kashida. Two
    sentences that differ only in punctuation or spacing should be treated
    as identical so we don't flag them as "new".
    """
    import re as _re

    s = s.replace("\u200c", " ")  # ZWNJ
    s = s.replace("ـ", "")        # kashida
    s = _re.sub(r"[،؛.؟!«»()\[\]\-—–]", "", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def diff_narratives(
    *,
    current_bias: str | None,
    current_state: str | None,
    current_diaspora: str | None,
    snapshot: dict | None,
) -> dict | None:
    """Compute sentence-level diffs between the live narrative fields and
    the snapshot captured ~24h ago. Returns a structure consumable by the
    homepage and story page to render a colored "به‌روز" callout listing
    new sentences per field:

        {"bias_new": [str, ...],
         "state_new": [str, ...],
         "diaspora_new": [str, ...]}

    Empty lists when nothing changed. Whole-field skip (all sentences new)
    for fields where the current text shares almost nothing with the
    snapshot — those look like a full rewrite, and showing the entire new
    text in a "what changed" callout would just duplicate the narrative.
    We set the field to [] and leave the user to read the full text below.
    """
    if not snapshot or not isinstance(snapshot, dict):
        return None

    def _diff_field(current: str | None, previous: str | None) -> list[str]:
        if not current or not previous:
            return []
        current_sents = _split_sentences(current)
        prev_keys = {_normalize_for_compare(s) for s in _split_sentences(previous)}
        new = [s for s in current_sents if _normalize_for_compare(s) not in prev_keys]
        # Guard: if almost everything is "new" it's a full rewrite, not a
        # delta. Don't highlight — let the badge alone carry the signal.
        # Threshold lowered from 0.8 → 0.6 (Δ2): mid-cycle refreshes that
        # touch most sentences are common on big-event stories, and the
        # old threshold suppressed exactly the ones readers most want to
        # see. 0.6 still kills genuine full rewrites where the prior
        # snapshot is unrelated.
        if current_sents and len(new) / len(current_sents) > 0.6:
            return []
        # Cap the callout length so it doesn't dominate the story card.
        return new[:4]

    return {
        "bias_new": _diff_field(current_bias, snapshot.get("bias_text")),
        "state_new": _diff_field(current_state, snapshot.get("state_text")),
        "diaspora_new": _diff_field(current_diaspora, snapshot.get("diaspora_text")),
    }
