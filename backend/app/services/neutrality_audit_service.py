"""Helpers for the Claude-scored neutrality audit.

Two phases, matching scripts/neutrality_audit.py:

  1. `export_for_audit(db, top_n, include_scored)` → returns the same
     shape the script writes to disk: a list of stories each carrying
     their articles + metadata + deterministic loaded-word evidence.
     The admin endpoint returns this list so a Claude conversation can
     read it and produce per-article neutrality scores.

  2. `apply_scores(db, payload)` → writes scores back into each story's
     summary_en blob: `article_neutrality` (raw per-article) + derived
     `source_neutrality` (per-source mean). Same fields the script's
     apply() step writes, so the PoliticalSpectrum figure on
     /stories/{id} renders without any frontend change.

No LLM calls in this module — Claude (the caller in-conversation) does
the scoring. Per the no-silent-fallbacks rule, this module writes ONLY
what the caller explicitly provides; a missing article id simply stays
unscored rather than being defaulted to 0.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article
from app.models.story import Story
from app.services.narrative_groups import narrative_group as _narrative_group
from app.services.story_analysis import _compute_article_evidence

logger = logging.getLogger(__name__)

ARTICLE_CONTENT_CAP = 3000

_SUBGROUP_FA = {
    "principlist": "اصول‌گرا",
    "reformist": "اصلاح‌طلب",
    "moderate_diaspora": "میانه‌رو",
    "radical_diaspora": "رادیکال",
}


async def export_for_audit(
    db: AsyncSession, top_n: int = 30, include_scored: bool = False,
) -> list[dict[str, Any]]:
    """Build the export payload the CLI writes to disk, in memory."""
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.summary_fa.isnot(None))
        .order_by(Story.trending_score.desc())
        .limit(top_n * 3)  # oversample so skips don't starve us
    )
    stories = list(result.scalars().all())

    picked: list[dict] = []
    for s in stories:
        try:
            blob = json.loads(s.summary_en) if s.summary_en else {}
        except Exception:
            blob = {}
        if not include_scored and isinstance(blob, dict) and blob.get("article_neutrality"):
            continue

        arts_out = []
        for a in s.articles:
            if not a.source:
                continue
            art_dict = {
                "title": a.title_original or a.title_fa or a.title_en or "",
                "content": (a.content_text or a.summary or "")[:ARTICLE_CONTENT_CAP],
            }
            evidence = _compute_article_evidence(art_dict)
            group = _narrative_group(a.source)
            arts_out.append({
                "id": str(a.id),
                "source_slug": a.source.slug,
                "source_name_fa": a.source.name_fa,
                "narrative_group": group,
                "subgroup_fa": _SUBGROUP_FA.get(group, "نامشخص"),
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "title": art_dict["title"],
                "content": art_dict["content"],
                "evidence": evidence,
            })
        if not arts_out:
            continue
        picked.append({
            "story_id": str(s.id),
            "title_fa": s.title_fa,
            "article_count": len(arts_out),
            "articles": arts_out,
        })
        if len(picked) >= top_n:
            break
    return picked


async def apply_scores(
    db: AsyncSession, payload: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write scored payload back into DB. Mirrors scripts/neutrality_audit.py::apply.

    Returns {updated, skipped, reasons} for the admin response.
    """
    if not isinstance(payload, list):
        raise ValueError("apply_scores: payload must be a JSON array")

    updated = 0
    skipped = 0
    reasons: list[dict[str, Any]] = []

    for entry in payload:
        sid = entry.get("story_id")
        scores_in = entry.get("article_neutrality") or {}
        if not sid or not isinstance(scores_in, dict) or not scores_in:
            skipped += 1
            reasons.append({"story_id": sid, "reason": "missing story_id or scores"})
            continue

        # Clamp + coerce. Invalid entries silently dropped (no guessed zeros).
        article_scores: dict[str, float] = {}
        for k, v in scores_in.items():
            try:
                article_scores[str(k)] = max(-1.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                continue
        if not article_scores:
            skipped += 1
            reasons.append({"story_id": sid, "reason": "no valid numeric scores"})
            continue

        res = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.id == sid)
        )
        story = res.scalar_one_or_none()
        if not story:
            skipped += 1
            reasons.append({"story_id": sid, "reason": "story not found"})
            continue

        # Per-source mean.
        per_source: dict[str, list[float]] = {}
        for a in story.articles:
            score = article_scores.get(str(a.id))
            if score is None or not a.source:
                continue
            per_source.setdefault(a.source.slug, []).append(score)
        if not per_source:
            skipped += 1
            reasons.append({"story_id": sid, "reason": "no article_id matched story"})
            continue
        source_neutrality = {
            slug: sum(v) / len(v) for slug, v in per_source.items()
        }

        try:
            blob = json.loads(story.summary_en) if story.summary_en else {}
        except Exception:
            blob = {}
        if not isinstance(blob, dict):
            blob = {}

        blob["article_neutrality"] = article_scores
        blob["source_neutrality"] = source_neutrality
        blob["neutrality_source"] = "claude"
        blob["neutrality_scored_at"] = datetime.now(timezone.utc).isoformat()
        story.summary_en = json.dumps(blob, ensure_ascii=False)
        updated += 1

    await db.commit()
    logger.info(f"neutrality_audit apply: updated={updated} skipped={skipped}")
    return {"updated": updated, "skipped": skipped, "reasons": reasons}
