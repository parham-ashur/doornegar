"""HITL admin endpoints: telegram triage, channel reclassify, narrative
bullets editor, stock-image picker. All gated by require_admin.
"""

import hashlib
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.admin import require_admin
from app.config import settings
from app.database import get_db
from app.models.article import Article
from app.models.social import TelegramChannel, TelegramPost
from app.models.story import Story

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])


# ─── 1. Telegram post triage queue ───────────────────────────

class TriageCandidate(BaseModel):
    story_id: str
    title_fa: str | None
    score: float


class TriagePost(BaseModel):
    post_id: str
    channel_title: str | None
    channel_type: str | None
    channel_username: str | None
    text: str
    posted_at: datetime | None
    current_story_id: str | None
    candidates: list[TriageCandidate]


class TriageResponse(BaseModel):
    items: list[TriagePost]
    total_scanned: int
    # Stats: score-band counts over the sample so the dashboard can show
    # "0 borderline, but scanned N and here's the distribution" instead
    # of a bare empty state that looks like it's broken.
    band_counts: dict[str, int] = Field(default_factory=dict)


def _clean_vec(v) -> list[float] | None:
    if not isinstance(v, list) or len(v) == 0:
        return None
    if any(x is None or not isinstance(x, (int, float)) for x in v):
        return None
    return v


@router.get("/telegram-triage", response_model=TriageResponse)
async def telegram_triage(
    limit: int = Query(default=30, le=100),
    min_score: float = Query(
        default=0.25,
        description="Lower bound of the band to surface. Default 0.25 catches weak-match posts that might have gone to the wrong story.",
    ),
    max_score: float = Query(
        default=0.45,
        description="Upper bound of the band. Default 0.45 catches posts the linker was moderately confident about but worth double-checking.",
    ),
    days: int = Query(default=21, le=60),
    scan: int = Query(default=150, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Show orphan/borderline posts with their top-3 candidate stories.

    Scans the `scan` most recent posts (default 150) from the last `days`
    days (default 21), scores each against every story, and returns posts
    whose best match falls inside [min_score, max_score] — the band where
    the automatic linker had to guess. Defaults 0.25-0.45 deliberately
    wider than the link threshold (0.35) so you can both audit close
    decisions and rescue posts that scored too weak to link at all.
    """
    from app.nlp.embeddings import generate_embeddings_batch, cosine_similarity

    # Pull recent posts (orphan OR with text, limited window)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(TelegramPost)
        .options(selectinload(TelegramPost.channel))
        .where(
            TelegramPost.text.isnot(None),
            TelegramPost.text != "",
            TelegramPost.date >= cutoff,
        )
        .order_by(desc(TelegramPost.date))
        .limit(scan)
    )
    posts = list(result.scalars().all())
    if not posts:
        return TriageResponse(items=[], total_scanned=0)

    # Load eligible stories + their article embeddings (same approach
    # link_posts_by_embedding uses — max of centroid / per-article).
    story_result = await db.execute(
        select(Story).where(
            Story.centroid_embedding.isnot(None), Story.article_count >= 3
        )
    )
    stories = list(story_result.scalars().all())
    story_titles = {str(s.id): s.title_fa for s in stories}
    story_centroids: dict[str, list[float]] = {}
    for s in stories:
        c = _clean_vec(s.centroid_embedding)
        if c is not None:
            story_centroids[str(s.id)] = c

    art_result = await db.execute(
        select(Article.story_id, Article.embedding).where(
            Article.story_id.in_(list(story_centroids.keys())),
            Article.embedding.isnot(None),
        )
    )
    story_article_embs: dict[str, list[list[float]]] = {}
    for sid, emb in art_result.all():
        cleaned = _clean_vec(emb)
        if cleaned is None:
            continue
        story_article_embs.setdefault(str(sid), []).append(cleaned)

    post_texts = [(p.text or "")[:500] for p in posts]
    import asyncio as _asyncio
    embeddings = await _asyncio.to_thread(
        generate_embeddings_batch, post_texts, 100
    )

    items: list[TriagePost] = []
    band_counts = {
        "<0.25": 0, "0.25-0.30": 0, "0.30-0.35": 0,
        "0.35-0.40": 0, "0.40-0.45": 0, "0.45-0.50": 0, ">=0.50": 0,
    }
    for post, emb in zip(posts, embeddings):
        if not emb:
            continue
        scored: list[tuple[str, float]] = []
        for sid, centroid in story_centroids.items():
            try:
                cs = cosine_similarity(emb, centroid)
            except Exception:
                cs = 0.0
            ab = 0.0
            for ae in story_article_embs.get(sid, []):
                try:
                    s = cosine_similarity(emb, ae)
                except Exception:
                    continue
                if s > ab:
                    ab = s
            scored.append((sid, max(cs, ab)))
        scored.sort(key=lambda x: -x[1])
        top = scored[:3]
        if not top:
            continue
        best_score = top[0][1]

        # Tally the whole sample for the distribution display
        if best_score < 0.25: band_counts["<0.25"] += 1
        elif best_score < 0.30: band_counts["0.25-0.30"] += 1
        elif best_score < 0.35: band_counts["0.30-0.35"] += 1
        elif best_score < 0.40: band_counts["0.35-0.40"] += 1
        elif best_score < 0.45: band_counts["0.40-0.45"] += 1
        elif best_score < 0.50: band_counts["0.45-0.50"] += 1
        else: band_counts[">=0.50"] += 1

        is_orphan = post.story_id is None
        in_band = min_score <= best_score <= max_score
        if not (in_band or (is_orphan and best_score < max_score)):
            continue
        items.append(
            TriagePost(
                post_id=str(post.id),
                channel_title=post.channel.title if post.channel else None,
                channel_type=post.channel.channel_type if post.channel else None,
                channel_username=post.channel.username if post.channel else None,
                text=post.text,
                posted_at=post.date,
                current_story_id=str(post.story_id) if post.story_id else None,
                candidates=[
                    TriageCandidate(
                        story_id=sid,
                        title_fa=story_titles.get(sid),
                        score=round(score, 4),
                    )
                    for sid, score in top
                ],
            )
        )
        if len(items) >= limit:
            break

    return TriageResponse(
        items=items, total_scanned=len(posts), band_counts=band_counts
    )


class TriageAction(BaseModel):
    action: Literal["link", "unlink"]
    story_id: str | None = None


@router.post("/telegram-triage/{post_id}")
async def telegram_triage_action(
    post_id: uuid.UUID,
    body: TriageAction,
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(TelegramPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if body.action == "link":
        if not body.story_id:
            raise HTTPException(status_code=400, detail="story_id required for link")
        old_story = post.story_id
        post.story_id = uuid.UUID(body.story_id)
        # Invalidate both affected stories' cached analysis so next read
        # regenerates with the corrected post set.
        affected = {uuid.UUID(body.story_id)}
        if old_story:
            affected.add(old_story)
        await db.execute(
            update(Story).where(Story.id.in_(affected)).values(telegram_analysis=None)
        )
    elif body.action == "unlink":
        old_story = post.story_id
        post.story_id = None
        if old_story:
            await db.execute(
                update(Story).where(Story.id == old_story).values(telegram_analysis=None)
            )
    await db.commit()
    return {"status": "ok", "post_id": str(post_id), "action": body.action}


class StorySearchItem(BaseModel):
    id: str
    title_fa: str | None
    article_count: int
    trending_score: float


@router.get("/story-search")
async def story_search(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(default=15, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Free-text story picker used by the triage UI when the "right"
    story for a post is outside the top-3 similarity candidates.
    Matches Farsi title with ILIKE — cheap, good-enough for the
    hundreds of visible stories we have at any time.
    """
    stmt = (
        select(Story.id, Story.title_fa, Story.article_count, Story.trending_score)
        .where(
            Story.article_count >= 2,
            Story.title_fa.ilike(f"%{q}%"),
        )
        .order_by(desc(Story.trending_score))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "results": [
            StorySearchItem(
                id=str(r.id),
                title_fa=r.title_fa,
                article_count=r.article_count or 0,
                trending_score=r.trending_score or 0.0,
            )
            for r in rows
        ]
    }


# ─── 2. Channel reclassification ─────────────────────────────

class ChannelListItem(BaseModel):
    id: str
    username: str | None
    title: str | None
    channel_type: str | None
    political_leaning: str | None
    is_active: bool
    post_count: int
    sample_posts: list[str]


@router.get("/channels")
async def list_channels(
    limit: int = Query(default=100, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all telegram channels with sample recent posts so admin
    can judge whether channel_type is correct.
    """
    channels_res = await db.execute(
        select(TelegramChannel).order_by(TelegramChannel.title).limit(limit)
    )
    channels = list(channels_res.scalars().all())

    # For each channel, fetch 3 most-recent post texts + total count
    items: list[ChannelListItem] = []
    for ch in channels:
        sample_res = await db.execute(
            select(TelegramPost.text)
            .where(TelegramPost.channel_id == ch.id, TelegramPost.text.isnot(None))
            .order_by(desc(TelegramPost.date))
            .limit(3)
        )
        samples = [t[0][:400] for t in sample_res.all() if t[0]]
        count_res = await db.execute(
            select(func.count(TelegramPost.id)).where(
                TelegramPost.channel_id == ch.id
            )
        )
        count = count_res.scalar() or 0
        items.append(
            ChannelListItem(
                id=str(ch.id),
                username=ch.username,
                title=ch.title,
                channel_type=ch.channel_type,
                political_leaning=ch.political_leaning,
                is_active=bool(ch.is_active),
                post_count=count,
                sample_posts=samples,
            )
        )
    return {"items": items}


class ChannelUpdate(BaseModel):
    channel_type: Literal[
        "news", "commentary", "aggregator", "activist", "political_party", "citizen"
    ] | None = None
    political_leaning: str | None = None
    is_active: bool | None = None


@router.patch("/channels/{channel_id}")
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
):
    ch = await db.get(TelegramChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    if body.channel_type is not None:
        ch.channel_type = body.channel_type
    if body.political_leaning is not None:
        ch.political_leaning = body.political_leaning
    if body.is_active is not None:
        ch.is_active = body.is_active
    await db.commit()
    return {"status": "ok"}


# ─── 3. Narrative 4-subgroup bullets editor ──────────────────

class NarrativeBullets(BaseModel):
    story_id: str
    title_fa: str | None
    bias_explanation_fa: str | None
    principlist: list[str] = Field(default_factory=list)
    reformist: list[str] = Field(default_factory=list)
    moderate_diaspora: list[str] = Field(default_factory=list)
    radical_diaspora: list[str] = Field(default_factory=list)


@router.get("/stories/{story_id}/narrative", response_model=NarrativeBullets)
async def get_story_narrative(story_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    import json as _json

    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    try:
        blob = _json.loads(story.summary_en) if story.summary_en else {}
    except Exception:
        blob = {}
    narr = blob.get("narrative") or {}
    inside = narr.get("inside") or {}
    outside = narr.get("outside") or {}
    return NarrativeBullets(
        story_id=str(story.id),
        title_fa=story.title_fa,
        bias_explanation_fa=blob.get("bias_explanation_fa"),
        principlist=list(inside.get("principlist") or []),
        reformist=list(inside.get("reformist") or []),
        moderate_diaspora=list(outside.get("moderate") or []),
        radical_diaspora=list(outside.get("radical") or []),
    )


class NarrativeUpdate(BaseModel):
    bias_explanation_fa: str | None = None
    principlist: list[str] | None = None
    reformist: list[str] | None = None
    moderate_diaspora: list[str] | None = None
    radical_diaspora: list[str] | None = None


@router.patch("/stories/{story_id}/narrative")
async def update_story_narrative(
    story_id: uuid.UUID,
    body: NarrativeUpdate,
    db: AsyncSession = Depends(get_db),
):
    import json as _json

    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    try:
        blob = _json.loads(story.summary_en) if story.summary_en else {}
    except Exception:
        blob = {}

    if body.bias_explanation_fa is not None:
        blob["bias_explanation_fa"] = body.bias_explanation_fa

    narrative = blob.get("narrative") or {}
    inside = narrative.get("inside") or {}
    outside = narrative.get("outside") or {}
    if body.principlist is not None:
        inside["principlist"] = body.principlist
    if body.reformist is not None:
        inside["reformist"] = body.reformist
    if body.moderate_diaspora is not None:
        outside["moderate"] = body.moderate_diaspora
    if body.radical_diaspora is not None:
        outside["radical"] = body.radical_diaspora
    narrative["inside"] = inside
    narrative["outside"] = outside
    blob["narrative"] = narrative

    # Sync legacy side-level summaries so the old fallback UI still works
    inside_bullets = (inside.get("principlist") or []) + (inside.get("reformist") or [])
    outside_bullets = (outside.get("moderate") or []) + (outside.get("radical") or [])
    if inside_bullets:
        blob["state_summary_fa"] = "؛ ".join(inside_bullets)
    if outside_bullets:
        blob["diaspora_summary_fa"] = "؛ ".join(outside_bullets)

    story.summary_en = _json.dumps(blob, ensure_ascii=False)
    if hasattr(story, "is_edited"):
        story.is_edited = True
    await db.commit()
    return {"status": "ok"}


# ─── 4. Stock-image picker (Unsplash) ────────────────────────


@router.get("/stories-without-image")
async def stories_without_image(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return visible stories that don't have a usable cover image.

    "Usable" = at least one article with a non-logo, non-icon image_url,
    OR a manual_image_url override stored in summary_en. A story
    surfaces here when every article's image is missing/bad AND no
    manual override has been pinned — the homepage card would fall
    back to a source logo, which looks broken.

    Ordered by trending_score DESC so the most-visible gaps rise to
    the top of the HITL queue.
    """
    import json as _json

    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles))
        .where(Story.article_count >= 5)
        .order_by(Story.trending_score.desc(), Story.first_published_at.desc().nullslast())
        .limit(500)
    )
    stories = result.scalars().all()

    def _is_bad(url: str | None) -> bool:
        if not url:
            return True
        u = url.lower()
        return (
            "favicon" in u
            or "/icon" in u
            or "logo" in u
            or "sprite" in u
            or u.endswith(".svg")
            or "1x1" in u
            or "placeholder" in u
        )

    def _has_manual(story: Story) -> bool:
        if not story.is_edited or not story.summary_en:
            return False
        try:
            blob = _json.loads(story.summary_en)
        except Exception:
            return False
        candidate = blob.get("manual_image_url")
        return bool(candidate and not _is_bad(candidate))

    def _has_article_image(story: Story) -> bool:
        return any(
            a.image_url and not _is_bad(a.image_url)
            for a in (story.articles or [])
        )

    gaps = []
    for s in stories:
        if _has_manual(s) or _has_article_image(s):
            continue
        gaps.append({
            "id": str(s.id),
            "slug": s.slug,
            "title_fa": s.title_fa,
            "article_count": s.article_count,
            "source_count": s.source_count,
            "first_published_at": s.first_published_at.isoformat() if s.first_published_at else None,
            "trending_score": s.trending_score,
        })
        if len(gaps) >= limit:
            break

    return {"stories": gaps, "count": len(gaps)}


@router.get("/unsplash-search")
async def unsplash_search(
    q: str = Query(..., min_length=2, max_length=200),
    per_page: int = Query(default=6, le=12),
):
    """Search Unsplash for candidate cover images. Requires
    UNSPLASH_ACCESS_KEY env var (free dev tier: 50 req/hour).
    """
    access_key = getattr(settings, "unsplash_access_key", "") or ""
    if not access_key:
        raise HTTPException(
            status_code=503,
            detail="UNSPLASH_ACCESS_KEY not configured. Set the env var on Railway.",
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q, "per_page": per_page, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {access_key}"},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Unsplash error: {e}")

    # Return a trim shape the frontend can render directly
    results = []
    for item in data.get("results", []):
        results.append(
            {
                "id": item.get("id"),
                "thumb_url": (item.get("urls") or {}).get("thumb"),
                "regular_url": (item.get("urls") or {}).get("regular"),
                "full_url": (item.get("urls") or {}).get("full"),
                "raw_url": (item.get("urls") or {}).get("raw"),
                "alt": item.get("alt_description") or item.get("description"),
                "author_name": ((item.get("user") or {}).get("name")),
                "author_url": ((item.get("user") or {}).get("links") or {}).get("html"),
                "unsplash_url": (item.get("links") or {}).get("html"),
                "width": item.get("width"),
                "height": item.get("height"),
            }
        )
    return {"results": results}


class PinImagePayload(BaseModel):
    image_url: str
    author_name: str | None = None
    author_url: str | None = None


@router.post("/stories/{story_id}/pin-image")
async def pin_image_to_story(
    story_id: uuid.UUID,
    body: PinImagePayload,
    db: AsyncSession = Depends(get_db),
):
    """Download chosen image, resize to max 1600px wide, upload to R2,
    pin as manual_image_url. Attribution stored alongside so the
    frontend can render a credit line.
    """
    import json as _json

    if not settings.r2_public_url or not settings.r2_access_key_id:
        raise HTTPException(status_code=503, detail="R2 is not configured")

    # Fetch
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(body.image_url)
            r.raise_for_status()
            data = r.content
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Image fetch failed: {e}")

    # Resize
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w > 1600:
            ratio = 1600 / w
            img = img.resize((1600, int(h * ratio)), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85, optimize=True)
        data = buf.getvalue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image processing failed: {e}")

    # Upload to R2
    try:
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        filename = hashlib.sha256(data).hexdigest()[:32] + ".jpg"
        s3.put_object(
            Bucket=settings.r2_bucket_name,
            Key=filename,
            Body=data,
            ContentType="image/jpeg",
        )
        r2_url = f"{settings.r2_public_url.rstrip('/')}/{filename}"
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"R2 upload failed: {e}")

    # Pin
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    try:
        blob = _json.loads(story.summary_en) if story.summary_en else {}
    except Exception:
        blob = {}
    blob["manual_image_url"] = r2_url
    if body.author_name or body.author_url:
        blob["manual_image_credit"] = {
            "author_name": body.author_name,
            "author_url": body.author_url,
        }
    story.summary_en = _json.dumps(blob, ensure_ascii=False)
    if hasattr(story, "is_edited"):
        story.is_edited = True
    await db.commit()
    return {"status": "ok", "r2_url": r2_url}


def _is_bad_image_url(url: str | None) -> bool:
    if not url:
        return True
    u = url.lower()
    return (
        "favicon" in u
        or "/icon" in u
        or "logo" in u
        or "sprite" in u
        or u.endswith(".svg")
        or "1x1" in u
        or "placeholder" in u
    )


@router.get("/stories/{story_id}/article-images")
async def story_article_images(
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Existing usable images from the story's own articles. First place
    the curator should look — if a clustered article already has a clean
    photo, the cover should match what readers see in the article list
    rather than a generic stock photo."""
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    seen: set[str] = set()
    results = []
    for a in (story.articles or []):
        if _is_bad_image_url(a.image_url):
            continue
        if a.image_url in seen:
            continue
        seen.add(a.image_url)
        src = a.source
        results.append(
            {
                "id": str(a.id),
                "thumb_url": a.image_url,
                "regular_url": a.image_url,
                "raw_url": a.image_url,
                "alt": a.title_fa or a.title_en or "",
                "author_name": (src.name_en or src.name_fa) if src else None,
                "author_url": a.url,
                "article_title_fa": a.title_fa,
                "article_url": a.url,
                "source_name_fa": (src.name_fa if src else None),
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
        )
    return {"results": results, "count": len(results)}


@router.get("/wikimedia-search")
async def wikimedia_search(
    q: str = Query(..., min_length=2, max_length=200),
    per_page: int = Query(default=12, ge=1, le=24),
):
    """Search Wikimedia Commons for candidate images. No API key needed —
    Commons only hosts free-to-use media. Best option for named public
    figures (politicians, officials) where Unsplash returns generic
    stock photos that don't match the subject."""
    import re as _re

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{q} filetype:bitmap",
                    "gsrnamespace": 6,
                    "gsrlimit": per_page,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata|size|user",
                    "iiurlwidth": 800,
                    "format": "json",
                    "formatversion": 2,
                    "origin": "*",
                },
                headers={"User-Agent": "Doornegar/1.0 (https://doornegar.org)"},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Wikimedia error: {e}")

    pages = (data.get("query") or {}).get("pages", []) or []
    # Commons returns pages in arbitrary order; sort by search index when present
    pages.sort(key=lambda p: (p.get("index") or 9999))

    results = []
    for page in pages:
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        meta = info.get("extmetadata") or {}
        artist_html = (meta.get("Artist") or {}).get("value") or ""
        author_name = _re.sub(r"<[^>]+>", "", artist_html).strip() or info.get("user") or None
        license_short = (meta.get("LicenseShortName") or {}).get("value") or None
        title = page.get("title") or ""
        alt = title.replace("File:", "").rsplit(".", 1)[0]
        results.append(
            {
                "id": str(page.get("pageid")),
                "thumb_url": info.get("thumburl") or info.get("url"),
                "regular_url": info.get("thumburl") or info.get("url"),
                "raw_url": info.get("url"),
                "alt": alt,
                "author_name": author_name,
                "author_url": info.get("descriptionurl"),
                "wikimedia_url": info.get("descriptionurl"),
                "license": license_short,
                "width": info.get("width"),
                "height": info.get("height"),
            }
        )
    return {"results": results}


# ─── 6. Story guardrail actions: freeze + split ──────────────

class FreezeResponse(BaseModel):
    story_id: str
    frozen_at: datetime
    article_count: int


@router.post("/stories/{story_id}/freeze", response_model=FreezeResponse)
async def freeze_story(story_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Mark a story as frozen. Matcher + merge steps skip frozen stories,
    so no new articles will be attached. Idempotent: re-freezing leaves
    the original frozen_at untouched.
    """
    from app.services.events import log_event

    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.frozen_at is None:
        story.frozen_at = datetime.now(timezone.utc)
        await log_event(
            db,
            event_type="freeze",
            actor="admin",
            story_id=story.id,
            signals={
                "article_count": story.article_count or 0,
                "review_tier": story.review_tier or 0,
            },
        )
        await db.commit()
    return FreezeResponse(
        story_id=str(story.id),
        frozen_at=story.frozen_at,
        article_count=story.article_count or 0,
    )


class UnfreezeResponse(BaseModel):
    story_id: str
    article_count: int


@router.post("/stories/{story_id}/unfreeze", response_model=UnfreezeResponse)
async def unfreeze_story(story_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Reverse a freeze. Clears review_tier too so the next pipeline run
    re-evaluates it from scratch."""
    from app.services.events import log_event

    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    was_frozen = story.frozen_at
    story.frozen_at = None
    story.review_tier = 0
    if was_frozen is not None:
        await log_event(
            db,
            event_type="unfreeze",
            actor="admin",
            story_id=story.id,
            signals={"previously_frozen_at": was_frozen.isoformat()},
        )
    await db.commit()
    return UnfreezeResponse(
        story_id=str(story.id),
        article_count=story.article_count or 0,
    )


class SplitGroup(BaseModel):
    title_fa: str
    title_en: str | None = None
    article_ids: list[uuid.UUID]


class SplitRequest(BaseModel):
    groups: list[SplitGroup] = Field(..., min_length=1)
    arc_title_fa: str | None = None
    arc_slug: str | None = None
    freeze_source: bool = True


class SplitResponseGroup(BaseModel):
    story_id: str
    title_fa: str
    article_count: int


class SplitResponse(BaseModel):
    source_story_id: str
    arc_id: str | None
    groups: list[SplitResponseGroup]
    remaining_in_source: int


@router.post("/stories/{story_id}/split", response_model=SplitResponse)
async def split_story(
    story_id: uuid.UUID,
    body: SplitRequest,
    db: AsyncSession = Depends(get_db),
):
    """Carve a source story into N child stories. Each group names a set
    of article_ids that get moved to a new Story. Optionally wrap the
    children in a new arc. Source story is frozen by default.
    """
    from app.services.story_ops import (
        SplitGroupInput,
        StoryOpsError,
        split_story_into_groups,
    )

    try:
        result = await split_story_into_groups(
            db,
            source_id=story_id,
            groups=[
                SplitGroupInput(
                    title_fa=g.title_fa,
                    title_en=g.title_en,
                    article_ids=list(g.article_ids),
                )
                for g in body.groups
            ],
            arc_title_fa=body.arc_title_fa,
            arc_slug=body.arc_slug,
            freeze_source=body.freeze_source,
        )
    except StoryOpsError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)

    return SplitResponse(
        source_story_id=str(result.source_story_id),
        arc_id=str(result.arc_id) if result.arc_id else None,
        groups=[
            SplitResponseGroup(
                story_id=str(g.story_id),
                title_fa=g.title_fa,
                article_count=g.article_count,
            )
            for g in result.groups
        ],
        remaining_in_source=result.remaining_in_source,
    )


# ─── Arc scaffold: admin outlines A→B→C→D, system fills ──────

class ScaffoldChapter(BaseModel):
    title_fa: str
    title_en: str | None = None
    story_id: uuid.UUID | None = None
    hint_keywords: list[str] | None = None


class ScaffoldRequest(BaseModel):
    arc_title_fa: str
    arc_slug: str | None = None
    chapters: list[ScaffoldChapter] = Field(..., min_length=1)
    create_missing: bool = True


class ScaffoldChapterResponse(BaseModel):
    story_id: str
    title_fa: str
    article_count: int
    resolution: Literal["linked_explicit", "linked_match", "created_placeholder"]
    match_score: float | None = None


class ScaffoldResponse(BaseModel):
    arc_id: str
    arc_title_fa: str
    arc_slug: str
    chapters: list[ScaffoldChapterResponse]


@router.post("/arcs/scaffold", response_model=ScaffoldResponse)
async def scaffold_arc_endpoint(
    body: ScaffoldRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin names an arc and its chapter titles (with optional story_id
    or hint_keywords per chapter); system resolves each to an existing
    story, creating a placeholder if no match and create_missing=True.
    """
    from app.services.story_ops import (
        ChapterInput,
        StoryOpsError,
        scaffold_arc,
    )

    try:
        result = await scaffold_arc(
            db,
            arc_title_fa=body.arc_title_fa,
            arc_slug=body.arc_slug,
            chapters=[
                ChapterInput(
                    title_fa=c.title_fa,
                    title_en=c.title_en,
                    story_id=c.story_id,
                    hint_keywords=c.hint_keywords,
                )
                for c in body.chapters
            ],
            create_missing=body.create_missing,
        )
    except StoryOpsError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)

    return ScaffoldResponse(
        arc_id=str(result.arc_id),
        arc_title_fa=result.arc_title_fa,
        arc_slug=result.arc_slug,
        chapters=[
            ScaffoldChapterResponse(
                story_id=str(c.story_id),
                title_fa=c.title_fa,
                article_count=c.article_count,
                resolution=c.resolution,
                match_score=c.match_score,
            )
            for c in result.chapters
        ],
    )


class ScaffoldPreviewRequest(BaseModel):
    chapters: list[ScaffoldChapter] = Field(..., min_length=1)


class ScaffoldPreviewChapter(BaseModel):
    title_fa: str
    match_story_id: str | None
    match_title_fa: str | None
    match_score: float
    would_create: bool


class ScaffoldPreviewResponse(BaseModel):
    chapters: list[ScaffoldPreviewChapter]


@router.post("/arcs/scaffold-preview", response_model=ScaffoldPreviewResponse)
async def scaffold_arc_preview(
    body: ScaffoldPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Dry-run of scaffold_arc — shows which existing stories would be
    linked vs created. No writes. Intended for the admin UI to render
    a confirmation screen before commit.
    """
    from app.services.story_ops import find_story_for_chapter

    out: list[ScaffoldPreviewChapter] = []
    for c in body.chapters:
        if c.story_id is not None:
            story = await db.get(Story, c.story_id)
            out.append(
                ScaffoldPreviewChapter(
                    title_fa=c.title_fa,
                    match_story_id=str(story.id) if story else None,
                    match_title_fa=story.title_fa if story else None,
                    match_score=1.0 if story else 0.0,
                    would_create=False,
                )
            )
            continue
        match, score = await find_story_for_chapter(
            db,
            title_fa=c.title_fa,
            hint_keywords=c.hint_keywords,
        )
        out.append(
            ScaffoldPreviewChapter(
                title_fa=c.title_fa,
                match_story_id=str(match.id) if match else None,
                match_title_fa=match.title_fa if match else None,
                match_score=round(score, 3),
                would_create=match is None,
            )
        )
    return ScaffoldPreviewResponse(chapters=out)


# ─── 7. Decision queue (review_tier > 0) + event log read ────

class ReviewQueueItem(BaseModel):
    story_id: str
    title_fa: str
    article_count: int
    source_count: int
    review_tier: int
    first_published_at: datetime | None
    last_updated_at: datetime | None
    age_days: float | None
    arc_id: str | None


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    tier_counts: dict[str, int]


@router.get("/review-queue", response_model=ReviewQueueResponse)
async def review_queue(
    min_tier: int = Query(1, ge=1, le=3),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Stories flagged by the guardrail pass as size/age outliers but
    not yet frozen. Tier 3 = propose freeze, tier 2 = strong warn,
    tier 1 = soft warn. Ordered tier desc, then article_count desc.
    """
    from sqlalchemy import text as _sql_text

    rows = await db.execute(
        select(
            Story.id, Story.title_fa, Story.article_count, Story.source_count,
            Story.review_tier, Story.first_published_at, Story.last_updated_at,
            Story.arc_id,
        )
        .where(Story.review_tier >= min_tier, Story.frozen_at.is_(None))
        .order_by(Story.review_tier.desc(), Story.article_count.desc())
        .limit(limit)
    )
    now = datetime.now(timezone.utc)
    items: list[ReviewQueueItem] = []
    for r in rows.all():
        started = r[5] or r[6]
        age = ((now - started).total_seconds() / 86400.0) if started else None
        items.append(
            ReviewQueueItem(
                story_id=str(r[0]),
                title_fa=r[1] or "",
                article_count=r[2] or 0,
                source_count=r[3] or 0,
                review_tier=r[4] or 0,
                first_published_at=r[5],
                last_updated_at=r[6],
                age_days=round(age, 2) if age is not None else None,
                arc_id=str(r[7]) if r[7] else None,
            )
        )

    counts_q = await db.execute(_sql_text(
        "SELECT review_tier, COUNT(*) FROM stories "
        "WHERE review_tier > 0 AND frozen_at IS NULL GROUP BY review_tier"
    ))
    tier_counts = {str(t): c for t, c in counts_q.all()}
    return ReviewQueueResponse(items=items, tier_counts=tier_counts)


class FrozenStoryItem(BaseModel):
    story_id: str
    title_fa: str
    article_count: int
    source_count: int
    frozen_at: datetime
    last_updated_at: datetime | None
    age_days: float | None


class FrozenStoriesResponse(BaseModel):
    items: list[FrozenStoryItem]
    total: int


@router.get("/frozen-stories", response_model=FrozenStoriesResponse)
async def frozen_stories(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List currently frozen stories. Frozen stories skip matcher + merge
    so no new articles attach. Use this view to unfreeze a story or audit
    what's been taken out of rotation.
    """
    from sqlalchemy import text as _sql_text

    rows = await db.execute(
        select(
            Story.id, Story.title_fa, Story.article_count, Story.source_count,
            Story.frozen_at, Story.last_updated_at, Story.first_published_at,
        )
        .where(Story.frozen_at.isnot(None))
        .order_by(Story.frozen_at.desc())
        .limit(limit)
    )
    now = datetime.now(timezone.utc)
    items: list[FrozenStoryItem] = []
    for r in rows.all():
        started = r[6] or r[5]
        age = ((now - started).total_seconds() / 86400.0) if started else None
        items.append(
            FrozenStoryItem(
                story_id=str(r[0]),
                title_fa=r[1] or "",
                article_count=r[2] or 0,
                source_count=r[3] or 0,
                frozen_at=r[4],
                last_updated_at=r[5],
                age_days=round(age, 2) if age is not None else None,
            )
        )
    total_q = await db.execute(_sql_text(
        "SELECT COUNT(*) FROM stories WHERE frozen_at IS NOT NULL"
    ))
    total = total_q.scalar() or 0
    return FrozenStoriesResponse(items=items, total=int(total))


class StoryEventItem(BaseModel):
    id: str
    story_id: str | None
    article_id: str | None
    event_type: str
    actor: str
    field: str | None
    old_value: str | None
    new_value: str | None
    confidence: float | None
    signals: dict | None
    created_at: datetime


class StoryEventsResponse(BaseModel):
    items: list[StoryEventItem]


@router.get("/stories/{story_id}/events", response_model=StoryEventsResponse)
async def get_story_events(
    story_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Timeline of every logged event touching this story — clustering
    decisions, freezes, splits, field edits. Used by the UI to render
    per-story audit history.
    """
    from sqlalchemy import text as _sql_text

    rows = await db.execute(
        _sql_text(
            """
            SELECT id, story_id, article_id, event_type, actor, field,
                   old_value, new_value, confidence, signals, created_at
            FROM story_events
            WHERE story_id = :sid
            ORDER BY created_at DESC
            LIMIT :lim
            """
        ),
        {"sid": story_id, "lim": limit},
    )
    items = [
        StoryEventItem(
            id=str(r[0]),
            story_id=str(r[1]) if r[1] else None,
            article_id=str(r[2]) if r[2] else None,
            event_type=r[3],
            actor=r[4],
            field=r[5],
            old_value=r[6],
            new_value=r[7],
            confidence=r[8],
            signals=r[9],
            created_at=r[10],
        )
        for r in rows.all()
    ]
    return StoryEventsResponse(items=items)
