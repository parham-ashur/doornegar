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
) -> dict:
    """Produce the JSON payload stored in `Story.analysis_snapshot_24h`.

    Kept small (≈200 bytes) so 500+ stories × JSONB column stays trivial.
    Only the numeric axes and a short hash of the bias text — no full text.
    """
    return {
        "snapshotted_at": datetime.now(timezone.utc).isoformat(),
        "article_count": int(article_count or 0),
        "dispute_score": float(dispute_score) if dispute_score is not None else None,
        "inside_pct": int(inside_pct or 0),
        "outside_pct": int(outside_pct or 0),
        "bias_hash": _bias_hash(bias_explanation_fa),
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

    # 1) Dispute score shifted materially (narratives became more or
    #    less contested). Phrase the direction for the reader.
    if snap_dispute is not None and current_dispute_score is not None:
        delta = current_dispute_score - snap_dispute
        if abs(delta) >= DISPUTE_DELTA_THRESHOLD:
            if delta > 0:
                reason = f"اختلاف روایت‌ها افزایش یافت ({snap_dispute:.1f} → {current_dispute_score:.1f})"
            else:
                reason = f"اختلاف روایت‌ها کاهش یافت ({snap_dispute:.1f} → {current_dispute_score:.1f})"
            return {"has_update": True, "kind": "dispute", "reason_fa": reason}

    # 2) Coverage distribution shifted — a new side started covering or
    #    an old one dropped off. We look at the inside/outside split
    #    because that's what the coverage bar surfaces; sub-subgroup
    #    shifts are noisier.
    cur_inside = int(current_inside_pct or 0)
    cur_outside = int(current_outside_pct or 0)
    inside_delta = abs(cur_inside - snap_inside)
    outside_delta = abs(cur_outside - snap_outside)
    if max(inside_delta, outside_delta) >= COVERAGE_PCT_DELTA_THRESHOLD:
        if cur_inside > snap_inside:
            reason = f"پوشش درون‌مرزی تقویت شد ({snap_inside}٪ → {cur_inside}٪)"
        elif cur_outside > snap_outside:
            reason = f"پوشش برون‌مرزی تقویت شد ({snap_outside}٪ → {cur_outside}٪)"
        else:
            reason = f"توزیع پوشش تغییر کرد ({snap_inside}٪/{snap_outside}٪ → {cur_inside}٪/{cur_outside}٪)"
        return {"has_update": True, "kind": "coverage_shift", "reason_fa": reason}

    # 3) Article volume grew and the bias comparison was rewritten —
    #    meaning the new articles actually moved the analytical narrative
    #    rather than piling on repetitive coverage.
    new_articles = current_article_count - snap_articles
    cur_bias_hash = _bias_hash(current_bias_explanation_fa)
    if new_articles >= NEW_ARTICLES_THRESHOLD and cur_bias_hash and cur_bias_hash != snap_bias_hash:
        reason = f"{new_articles} مقالهٔ جدید و بازنویسی تحلیل سوگیری"
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
