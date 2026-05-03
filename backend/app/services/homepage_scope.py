"""Single source of truth: which stories are on the homepage right now.

Parham's rule (2026-05-03): every penny of LLM spend goes to stories
visitors actually see on the homepage. No spend on demoted (-50)
umbrellas, frozen chapters, archived rows, low-trending stragglers,
or off-homepage blindspot overflow.

Every per-story LLM step in `auto_maintenance.py` (and elsewhere) MUST
filter `Story.id.in_(await homepage_story_ids(db))` before opening
its wallet. The gate mirrors the trending + blindspot APIs in
`api/v1/stories.py` exactly so what gets analyzed is what gets shown.

If the trending/blindspot API filters change, change them HERE too.
A drift between this gate and the API breaks the budget guarantee.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story import Story


# Mirrors api/v1/stories.py:trending_stories — keep in lockstep.
TRENDING_MIN_ARTICLES = 4
TRENDING_MIN_SCORE = 0.5

# Mirrors api/v1/stories.py:blindspot_stories.
BLINDSPOT_MIN_ARTICLES = 4
BLINDSPOT_LAST_UPDATED_DAYS = 14  # soft window; covers strict 7d too


async def homepage_story_ids(
    db: AsyncSession,
    *,
    trending_top_n: int = 20,
    blindspot_top_n: int = 20,
) -> set:
    """Return the set of story IDs currently visible on the homepage.

    `trending_top_n` is generous (20 vs the 10-12 the homepage actually
    renders) so a story that's about to climb into view still gets
    pre-warmed; without that, fresh stories enter the homepage with no
    summary or bias panel and visitors see "تحلیل در حال آماده‌سازی است".

    Always returns a set — empty set is a valid answer (means: do not
    spend on any story this run).
    """
    trending_q = (
        select(Story.id)
        .where(
            Story.article_count >= TRENDING_MIN_ARTICLES,
            Story.trending_score > TRENDING_MIN_SCORE,
            Story.is_blindspot.is_(False),
            Story.archived_at.is_(None),
            Story.frozen_at.is_(None),
        )
        .order_by(Story.priority.desc(), Story.trending_score.desc())
        .limit(trending_top_n)
    )
    ids = {row[0] for row in (await db.execute(trending_q)).all()}

    cutoff = datetime.now(timezone.utc) - timedelta(days=BLINDSPOT_LAST_UPDATED_DAYS)
    blindspot_q = (
        select(Story.id)
        .where(
            Story.is_blindspot.is_(True),
            Story.article_count >= BLINDSPOT_MIN_ARTICLES,
            Story.archived_at.is_(None),
            Story.frozen_at.is_(None),
            Story.last_updated_at >= cutoff,
        )
        .order_by(Story.first_published_at.desc().nullslast())
        .limit(blindspot_top_n)
    )
    ids |= {row[0] for row in (await db.execute(blindspot_q)).all()}
    return ids


def homepage_eligible_filters():
    """SQL predicates that any candidate for the homepage must satisfy.

    Looser than `homepage_story_ids` — this is the *necessary* set, not
    the *sufficient* set (a story that passes these filters is *eligible*
    for the homepage but may not currently rank into the top-N). Use
    this when you need a SQL-side filter and the per-call cost of
    materializing the top-N set isn't worth it.

    Always combine with an order-by `priority DESC, trending_score DESC`
    and a hard limit so you don't accidentally fan out to the whole
    eligible pool.
    """
    return (
        Story.archived_at.is_(None),
        Story.frozen_at.is_(None),
        Story.priority > -10,  # excludes -50 demoted + -100 hidden
    )
