"""Story arc HITL endpoints + public read.

Admin:
  GET    /admin/hitl/arcs/suggestions  -> candidate arcs (centroid clusters)
  GET    /admin/hitl/arcs              -> list existing arcs
  POST   /admin/hitl/arcs              -> create arc from ordered story_ids
  PATCH  /admin/hitl/arcs/{id}         -> update title/desc, add/remove/reorder chapters
  DELETE /admin/hitl/arcs/{id}         -> delete arc (un-assign stories)

Public:
  GET    /arcs/{arc_id}                -> arc + ordered chapters
  (Story detail already includes the arc sibling strip via arc_id lookup.)
"""

import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import require_admin
from app.database import get_db
from app.models.story import Story
from app.models.story_arc import StoryArc

logger = logging.getLogger(__name__)

admin_router = APIRouter(dependencies=[Depends(require_admin)])
public_router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────


class ArcChapter(BaseModel):
    story_id: str
    title_fa: str | None
    image_url: str | None = None
    first_published_at: datetime | None
    article_count: int
    order: int


class ArcResponse(BaseModel):
    id: str
    title_fa: str
    title_en: str | None
    slug: str
    description_fa: str | None
    chapters: list[ArcChapter]


class ArcSuggestion(BaseModel):
    """Candidate arc — a connected component of similar stories, chronologically ordered.

    Rendered in the suggester UI. Curator clicks "Create" to promote it
    to a real StoryArc. `already_in_arc_ids` flags chapters that are
    already part of an existing arc (creating a new one would reassign).
    """

    chapters: list[ArcChapter]
    already_in_arc_ids: list[str] = Field(default_factory=list)
    suggested_title_fa: str | None


class ArcCreate(BaseModel):
    title_fa: str
    title_en: str | None = None
    description_fa: str | None = None
    story_ids: list[str]  # in intended chronological order


class ArcUpdate(BaseModel):
    title_fa: str | None = None
    title_en: str | None = None
    description_fa: str | None = None
    story_ids: list[str] | None = None  # full replacement when provided


# ─── Helpers ─────────────────────────────────────────────


def _slugify(title: str) -> str:
    # Persian-safe slug: keep letters (Latin + Persian), digits, dashes.
    s = re.sub(r"[^0-9A-Za-z\u0600-\u06FF\u200c]+", "-", title.strip()).strip("-")
    s = re.sub(r"-+", "-", s).lower()
    return s[:180] or f"arc-{uuid.uuid4().hex[:8]}"


async def _fetch_story_image(db: AsyncSession, story_id: uuid.UUID) -> str | None:
    """Use the same cover-image logic the public endpoint uses: first
    article image, else None. Kept minimal since we only need it for
    the chapter thumbnail.
    """
    from app.models.article import Article

    row = await db.execute(
        select(Article.image_url)
        .where(Article.story_id == story_id, Article.image_url.isnot(None))
        .order_by(Article.published_at.desc().nullslast())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _chapters_for_arc(db: AsyncSession, arc_id: uuid.UUID) -> list[ArcChapter]:
    q = await db.execute(
        select(
            Story.id,
            Story.title_fa,
            Story.first_published_at,
            Story.article_count,
            Story.arc_order,
        )
        .where(Story.arc_id == arc_id)
        .order_by(Story.arc_order.asc().nullslast(), Story.first_published_at.asc().nullslast())
    )
    rows = q.all()
    chapters: list[ArcChapter] = []
    for i, r in enumerate(rows):
        image_url = await _fetch_story_image(db, r.id)
        chapters.append(
            ArcChapter(
                story_id=str(r.id),
                title_fa=r.title_fa,
                image_url=image_url,
                first_published_at=r.first_published_at,
                article_count=r.article_count or 0,
                order=r.arc_order if r.arc_order is not None else i,
            )
        )
    return chapters


async def _arc_to_response(db: AsyncSession, arc: StoryArc) -> ArcResponse:
    return ArcResponse(
        id=str(arc.id),
        title_fa=arc.title_fa,
        title_en=arc.title_en,
        slug=arc.slug,
        description_fa=arc.description_fa,
        chapters=await _chapters_for_arc(db, arc.id),
    )


# ─── Admin: suggestions ──────────────────────────────────


@admin_router.get("/suggestions", response_model=list[ArcSuggestion])
async def suggest_arcs(
    min_similarity: float = 0.55,
    max_stories: int = 120,
    min_chapters: int = 3,
    db: AsyncSession = Depends(get_db),
) -> list[ArcSuggestion]:
    """Compute candidate arcs from visible stories via centroid cosine.

    Connected components on the similarity graph with
    cosine >= min_similarity and component size >= min_chapters are
    proposed. Each candidate's chapters are ordered by first_published_at.

    Pure cosine math — no LLM. O(n²) over at most `max_stories` visible
    stories, which is ~150–200 on this dataset. Runs in ~1–2s.
    """
    from app.nlp.embeddings import cosine_similarity as _cs

    q = await db.execute(
        select(
            Story.id,
            Story.title_fa,
            Story.first_published_at,
            Story.article_count,
            Story.centroid_embedding,
            Story.arc_id,
        )
        .where(
            Story.article_count >= 3,
            Story.trending_score > -10,  # skip hidden/merged remnants
            Story.centroid_embedding.isnot(None),
        )
        .order_by(Story.first_published_at.desc().nullslast())
        .limit(max_stories)
    )
    rows = [r for r in q.all() if isinstance(r.centroid_embedding, list) and r.centroid_embedding]
    n = len(rows)
    if n < min_chapters:
        return []

    # Union-find on similarity graph.
    parent: dict[int, int] = {i: i for i in range(n)}

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x: int, y: int) -> None:
        rx, ry = _find(x), _find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            try:
                sim = _cs(rows[i].centroid_embedding, rows[j].centroid_embedding)
            except Exception:
                continue
            if sim >= min_similarity:
                _union(i, j)

    components: dict[int, list[int]] = {}
    for i in range(n):
        components.setdefault(_find(i), []).append(i)

    suggestions: list[ArcSuggestion] = []
    for members in components.values():
        if len(members) < min_chapters:
            continue
        # Order chapters by first_published_at (earliest first).
        members_sorted = sorted(
            members,
            key=lambda idx: rows[idx].first_published_at or datetime.min,
        )
        chapters: list[ArcChapter] = []
        already_in_arc: list[str] = []
        for order_idx, idx in enumerate(members_sorted):
            r = rows[idx]
            image_url = await _fetch_story_image(db, r.id)
            chapters.append(
                ArcChapter(
                    story_id=str(r.id),
                    title_fa=r.title_fa,
                    image_url=image_url,
                    first_published_at=r.first_published_at,
                    article_count=r.article_count or 0,
                    order=order_idx,
                )
            )
            if r.arc_id is not None:
                already_in_arc.append(str(r.id))
        # Use the largest chapter's title as the suggested arc title —
        # curator can rename. Falls back to shortest title if sizes tie.
        biggest = max(members_sorted, key=lambda idx: rows[idx].article_count or 0)
        suggested_title = rows[biggest].title_fa
        suggestions.append(
            ArcSuggestion(
                chapters=chapters,
                already_in_arc_ids=already_in_arc,
                suggested_title_fa=suggested_title,
            )
        )

    # Biggest candidates first so curator sees the most material arcs on top.
    suggestions.sort(key=lambda s: len(s.chapters), reverse=True)
    return suggestions


# ─── Admin: CRUD ─────────────────────────────────────────


@admin_router.get("", response_model=list[ArcResponse])
async def list_arcs(db: AsyncSession = Depends(get_db)) -> list[ArcResponse]:
    q = await db.execute(select(StoryArc).order_by(StoryArc.created_at.desc()))
    arcs = q.scalars().all()
    return [await _arc_to_response(db, a) for a in arcs]


@admin_router.post("", response_model=ArcResponse)
async def create_arc(payload: ArcCreate, db: AsyncSession = Depends(get_db)) -> ArcResponse:
    if len(payload.story_ids) < 2:
        raise HTTPException(status_code=400, detail="An arc needs at least 2 chapters")
    arc = StoryArc(
        title_fa=payload.title_fa.strip(),
        title_en=(payload.title_en or "").strip() or None,
        description_fa=(payload.description_fa or "").strip() or None,
        slug=_slugify(payload.title_fa),
    )
    db.add(arc)
    await db.flush()
    # Assign stories with order. Replace any prior arc membership.
    for order, sid in enumerate(payload.story_ids):
        try:
            sid_uuid = uuid.UUID(sid)
        except ValueError:
            continue
        await db.execute(
            update(Story)
            .where(Story.id == sid_uuid)
            .values(arc_id=arc.id, arc_order=order)
        )
    await db.commit()
    await db.refresh(arc)
    return await _arc_to_response(db, arc)


@admin_router.patch("/{arc_id}", response_model=ArcResponse)
async def update_arc(
    arc_id: uuid.UUID, payload: ArcUpdate, db: AsyncSession = Depends(get_db)
) -> ArcResponse:
    arc = await db.get(StoryArc, arc_id)
    if not arc:
        raise HTTPException(status_code=404, detail="Arc not found")
    if payload.title_fa is not None:
        arc.title_fa = payload.title_fa.strip()
        arc.slug = _slugify(payload.title_fa)
    if payload.title_en is not None:
        arc.title_en = payload.title_en.strip() or None
    if payload.description_fa is not None:
        arc.description_fa = payload.description_fa.strip() or None
    if payload.story_ids is not None:
        if len(payload.story_ids) < 2:
            raise HTTPException(status_code=400, detail="An arc needs at least 2 chapters")
        # Clear current chapters first
        await db.execute(
            update(Story).where(Story.arc_id == arc.id).values(arc_id=None, arc_order=None)
        )
        for order, sid in enumerate(payload.story_ids):
            try:
                sid_uuid = uuid.UUID(sid)
            except ValueError:
                continue
            await db.execute(
                update(Story)
                .where(Story.id == sid_uuid)
                .values(arc_id=arc.id, arc_order=order)
            )
    await db.commit()
    await db.refresh(arc)
    return await _arc_to_response(db, arc)


@admin_router.delete("/{arc_id}")
async def delete_arc(arc_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    arc = await db.get(StoryArc, arc_id)
    if not arc:
        raise HTTPException(status_code=404, detail="Arc not found")
    await db.execute(
        update(Story).where(Story.arc_id == arc.id).values(arc_id=None, arc_order=None)
    )
    await db.delete(arc)
    await db.commit()
    return {"status": "ok"}


# ─── Public read ─────────────────────────────────────────


@public_router.get("/{arc_id}", response_model=ArcResponse)
async def get_arc(arc_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ArcResponse:
    arc = await db.get(StoryArc, arc_id)
    if not arc:
        raise HTTPException(status_code=404, detail="Arc not found")
    return await _arc_to_response(db, arc)
