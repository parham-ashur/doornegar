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
    embeddings = generate_embeddings_batch(post_texts, batch_size=100)

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
