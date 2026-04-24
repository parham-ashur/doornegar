"""Story manipulation primitives shared by HITL endpoints and Niloofar.

All mutating helpers commit on success and raise on validation errors.
Callers should treat them as atomic: if the function returns, the change
is persisted; if it raises, nothing committed.

Three primitives:
- split_story_into_groups — carve a source story into N children, optionally
  wrap them in an arc, optionally freeze the source.
- scaffold_arc — given a chapter outline, resolve each chapter to an
  existing story (by explicit id or title/keyword match) or create a
  placeholder, then link all chapters to a new arc.
- find_story_for_chapter — best-effort story match for a chapter name +
  optional keyword hints. Used by scaffold_arc; exposed for UI preview.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.story import Story
from app.models.story_arc import StoryArc


@dataclass
class SplitGroupInput:
    title_fa: str
    title_en: str | None
    article_ids: list[uuid.UUID]


@dataclass
class SplitGroupResult:
    story_id: uuid.UUID
    title_fa: str
    article_count: int


@dataclass
class SplitResult:
    source_story_id: uuid.UUID
    arc_id: uuid.UUID | None
    groups: list[SplitGroupResult]
    remaining_in_source: int


class StoryOpsError(ValueError):
    """Raised on validation failures (bad UUIDs, cross-group duplicates, etc.)."""


async def split_story_into_groups(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    groups: list[SplitGroupInput],
    arc_title_fa: str | None = None,
    arc_slug: str | None = None,
    freeze_source: bool = True,
) -> SplitResult:
    """Carve a source story into N child stories. Articles named in each
    group move to a new Story; leftovers stay in source. Optionally wrap
    children in a new arc. Source is frozen by default.
    """
    src = await db.get(Story, source_id)
    if src is None:
        raise StoryOpsError(f"Story {source_id} not found")
    if not groups:
        raise StoryOpsError("At least one group required")

    all_ids: set[uuid.UUID] = set()
    for g in groups:
        for aid in g.article_ids:
            if aid in all_ids:
                raise StoryOpsError(f"Article {aid} listed in more than one group")
            all_ids.add(aid)

    if all_ids:
        valid_q = await db.execute(
            select(Article.id).where(
                Article.id.in_(all_ids),
                Article.story_id == source_id,
            )
        )
        valid_ids = {row[0] for row in valid_q.all()}
        missing = all_ids - valid_ids
        if missing:
            raise StoryOpsError(
                f"{len(missing)} article_id(s) don't belong to the source story"
            )

    arc_id: uuid.UUID | None = None
    if arc_title_fa:
        arc = StoryArc(
            id=uuid.uuid4(),
            title_fa=arc_title_fa,
            slug=arc_slug or f"arc-{uuid.uuid4().hex[:8]}",
        )
        db.add(arc)
        await db.flush()
        arc_id = arc.id

    created: list[SplitGroupResult] = []
    for idx, g in enumerate(groups):
        child = Story(
            id=uuid.uuid4(),
            title_fa=g.title_fa,
            title_en=g.title_en or g.title_fa,
            slug=f"{src.slug}-p{idx+1}-{uuid.uuid4().hex[:6]}",
            article_count=0,
            source_count=0,
            split_from_id=src.id,
            arc_id=arc_id,
            arc_order=idx if arc_id else None,
        )
        db.add(child)
        await db.flush()

        if g.article_ids:
            await db.execute(
                update(Article)
                .where(Article.id.in_(g.article_ids))
                .values(story_id=child.id)
            )
        count = (await db.execute(
            select(func.count(Article.id)).where(Article.story_id == child.id)
        )).scalar() or 0
        src_count = (await db.execute(
            select(func.count(func.distinct(Article.source_id))).where(
                Article.story_id == child.id
            )
        )).scalar() or 0
        child.article_count = count
        child.source_count = src_count
        created.append(
            SplitGroupResult(
                story_id=child.id,
                title_fa=child.title_fa,
                article_count=count,
            )
        )

    remaining = (await db.execute(
        select(func.count(Article.id)).where(Article.story_id == src.id)
    )).scalar() or 0
    src.article_count = remaining
    if freeze_source:
        src.frozen_at = datetime.now(timezone.utc)

    await db.commit()
    return SplitResult(
        source_story_id=src.id,
        arc_id=arc_id,
        groups=created,
        remaining_in_source=remaining,
    )


@dataclass
class ChapterInput:
    title_fa: str
    title_en: str | None = None
    story_id: uuid.UUID | None = None
    hint_keywords: list[str] | None = None


@dataclass
class ChapterResult:
    story_id: uuid.UUID
    title_fa: str
    article_count: int
    resolution: str  # "linked_explicit" | "linked_match" | "created_placeholder"
    match_score: float | None


@dataclass
class ScaffoldResult:
    arc_id: uuid.UUID
    arc_title_fa: str
    arc_slug: str
    chapters: list[ChapterResult]


async def find_story_for_chapter(
    db: AsyncSession,
    *,
    title_fa: str,
    hint_keywords: list[str] | None = None,
    min_score: float = 0.35,
) -> tuple[Story | None, float]:
    """Look up an existing story that best matches a chapter name.

    Score = (token overlap between chapter title and story title) +
    keyword-hit bonus. Not embedding-based on purpose: arc scaffolding
    is a deliberate admin action where keyword intent is usually clearer
    than semantic centroids, and centroids are often stale for placeholder
    or newly-split stories.
    """
    tokens = {t for t in title_fa.split() if len(t) >= 3}
    hints = [k.strip() for k in (hint_keywords or []) if k.strip()]

    if not tokens and not hints:
        return None, 0.0

    filters = []
    for tok in tokens:
        filters.append(Story.title_fa.ilike(f"%{tok}%"))
    for h in hints:
        filters.append(Story.title_fa.ilike(f"%{h}%"))
        filters.append(Story.summary_fa.ilike(f"%{h}%"))

    q = select(Story).where(
        Story.frozen_at.is_(None),
        Story.article_count >= 3,
        or_(*filters),
    ).limit(20)
    candidates = (await db.execute(q)).scalars().all()

    best_story: Story | None = None
    best_score = 0.0
    for cand in candidates:
        c_tokens = {t for t in (cand.title_fa or "").split() if len(t) >= 3}
        overlap = len(tokens & c_tokens) / max(len(tokens), 1) if tokens else 0.0
        hit_bonus = 0.0
        for h in hints:
            if cand.title_fa and h in cand.title_fa:
                hit_bonus += 0.25
            elif cand.summary_fa and h in cand.summary_fa:
                hit_bonus += 0.10
        score = overlap + min(hit_bonus, 0.5)
        if score > best_score:
            best_score = score
            best_story = cand

    if best_score < min_score:
        return None, best_score
    return best_story, best_score


async def scaffold_arc(
    db: AsyncSession,
    *,
    arc_title_fa: str,
    chapters: list[ChapterInput],
    arc_slug: str | None = None,
    create_missing: bool = True,
) -> ScaffoldResult:
    """Build an arc from a chapter outline. Each chapter resolves to:
    - the story at `story_id` if provided
    - the best-match existing story for `title_fa` + hints
    - a placeholder Story (if create_missing=True) when nothing matches

    All chapters end up linked to a new StoryArc with sequential arc_order.
    Chapters that already belong to a different arc get re-pointed to this
    arc — admin-driven scaffolds are authoritative.
    """
    if not chapters:
        raise StoryOpsError("At least one chapter required")

    slug = arc_slug or f"arc-{uuid.uuid4().hex[:8]}"
    arc = StoryArc(id=uuid.uuid4(), title_fa=arc_title_fa, slug=slug)
    db.add(arc)
    await db.flush()

    resolved: list[ChapterResult] = []
    for idx, ch in enumerate(chapters):
        story: Story | None = None
        resolution: str = ""
        score: float | None = None

        if ch.story_id is not None:
            story = await db.get(Story, ch.story_id)
            if story is None:
                raise StoryOpsError(f"Chapter {idx}: story {ch.story_id} not found")
            resolution = "linked_explicit"
        else:
            match, score = await find_story_for_chapter(
                db,
                title_fa=ch.title_fa,
                hint_keywords=ch.hint_keywords,
            )
            if match is not None:
                story = match
                resolution = "linked_match"
            elif create_missing:
                story = Story(
                    id=uuid.uuid4(),
                    title_fa=ch.title_fa,
                    title_en=ch.title_en or ch.title_fa,
                    slug=f"{slug}-ch{idx+1}-{uuid.uuid4().hex[:6]}",
                    article_count=0,
                    source_count=0,
                )
                db.add(story)
                await db.flush()
                resolution = "created_placeholder"
            else:
                raise StoryOpsError(
                    f"Chapter {idx} ({ch.title_fa!r}): no match and create_missing=False"
                )

        story.arc_id = arc.id
        story.arc_order = idx
        resolved.append(
            ChapterResult(
                story_id=story.id,
                title_fa=story.title_fa,
                article_count=story.article_count or 0,
                resolution=resolution,
                match_score=score,
            )
        )

    await db.commit()
    return ScaffoldResult(
        arc_id=arc.id,
        arc_title_fa=arc.title_fa,
        arc_slug=arc.slug,
        chapters=resolved,
    )
