import logging
import time as _time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.admin import require_admin
from app.config import settings
from app.database import get_db
from app.models.analyst import Analyst
from app.models.analyst_take import AnalystTake
from app.models.article import Article
from app.models.bias_score import BiasScore
from app.models.source import Source
from app.models.story import Story
from app.schemas.bias import BiasScoreResponse
from app.schemas.story import (
    StoryAnalysisResponse,
    StoryArticleWithBias,
    StoryBrief,
    StoryDetail,
    StoryListResponse,
)
from app.services.story_analysis import generate_story_analysis
from app.rate_limit import limiter as _limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# ── In-memory response cache for trending/blindspot (saves Neon transfer) ──
_stories_cache: dict[str, dict] = {}
_STORIES_CACHE_TTL = 120  # 2 minutes


@router.get("", response_model=StoryListResponse)
async def list_stories(
    topic: str | None = None,
    blindspots_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Story).options(
        selectinload(Story.articles).selectinload(Article.source),
    )
    count_query = select(func.count(Story.id))

    if blindspots_only:
        query = query.where(Story.is_blindspot.is_(True))
        count_query = count_query.where(Story.is_blindspot.is_(True))

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Story.trending_score.desc(), Story.first_published_at.desc().nullslast())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    stories = result.scalars().all()

    return StoryListResponse(
        stories=[_story_brief_with_extras(s) for s in stories],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/trending", response_model=list[StoryBrief])
@_limiter.limit("120/minute")
async def trending_stories(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    min_articles: int = Query(4, ge=1),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"trending:{limit}:{min_articles}"
    cached = _stories_cache.get(cache_key)
    if cached and _time.time() < cached["expires"]:
        return cached["data"]

    # Fetch more than needed so diversity reranking has room to work
    fetch_limit = min(limit * 3, 100)
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(
            Story.article_count >= min_articles,
            # Exclude stale tiny stories — 2-day half-life decay means
            # 7-day-old 4-article stories score ~0.36. Threshold 0.5
            # keeps large clusters visible while cutting old noise.
            Story.trending_score > 0.5,
            # Blindspots have their own dedicated section on the homepage.
            # Keeping them out of trending prevents small one-sided stories
            # from diluting the multi-sided feed.
            Story.is_blindspot.is_(False),
        )
        .order_by(Story.priority.desc(), Story.trending_score.desc())
        .limit(fetch_limit)
    )
    stories = list(result.scalars().all())

    # ── Diversity reranking ──
    # Penalize stories whose titles overlap heavily with higher-ranked ones.
    # This prevents 6 ceasefire stories from dominating the top — the first
    # one ranks normally, the 2nd gets a small penalty, the 3rd a bigger one.
    seen_words: set[str] = set()
    scored: list[tuple[float, int, Story]] = []
    for i, s in enumerate(stories):
        words = {w for w in (s.title_fa or "").split() if len(w) >= 3}
        if words:
            overlap = len(words & seen_words) / len(words)
        else:
            overlap = 0.0
        # First story of a topic: penalty=1.0 (none). 50% overlap → 0.65x. 80% overlap → 0.44x.
        penalty = max(0.3, 1.0 - overlap * 0.7)
        effective = (s.priority or 0) * 1000 + (s.trending_score or 0) * penalty
        scored.append((effective, -i, s))  # -i for stable sort
        seen_words.update(words)

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [s for _, _, s in scored[:limit]]

    data = [_story_brief_with_extras(s) for s in ranked]
    _stories_cache[cache_key] = {"data": data, "expires": _time.time() + _STORIES_CACHE_TTL}
    return data


@router.get("/blindspots", response_model=list[StoryBrief])
@_limiter.limit("60/minute")
async def blindspot_stories(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    min_articles: int = Query(4, ge=1),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.is_blindspot.is_(True), Story.article_count >= min_articles)
        .order_by(Story.first_published_at.desc().nullslast())
        .limit(limit)
    )
    stories = result.scalars().all()
    return [_story_brief_with_extras(s) for s in stories]


@router.get("/{story_id}/analysis", response_model=StoryAnalysisResponse)
@_limiter.limit("120/minute")
async def get_story_analysis(request: Request, story_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return the saved analysis instantly. Full JSON is stored in summary_en."""
    import json as _json
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Full analysis is stored as JSON in summary_en
    extra = {}
    if story.summary_en:
        try:
            extra = _json.loads(story.summary_en)
        except Exception:
            pass

    return StoryAnalysisResponse(
        story_id=story.id,
        summary_fa=story.summary_fa,
        state_summary_fa=extra.get("state_summary_fa"),
        diaspora_summary_fa=extra.get("diaspora_summary_fa"),
        independent_summary_fa=extra.get("independent_summary_fa"),
        bias_explanation_fa=extra.get("bias_explanation_fa"),
        scores=extra.get("scores"),
        source_neutrality=extra.get("source_neutrality"),
        dispute_score=extra.get("dispute_score"),
        loaded_words=extra.get("loaded_words"),
        narrative_arc=extra.get("narrative_arc"),
        delta=extra.get("delta"),
        analyst=extra.get("analyst"),
        silence_analysis=extra.get("silence_analysis"),
        coordinated_messaging=extra.get("coordinated_messaging"),
    )


@router.get("/analyses")
@_limiter.limit("60/minute")
async def get_story_analyses_batch(
    request: Request,
    ids: str,
    db: AsyncSession = Depends(get_db),
):
    """Batch-fetch story analyses in a single round trip.

    Accepts ?ids=uuid,uuid,uuid (comma-separated). Returns a dict keyed by
    story_id string with the same shape as GET /stories/{id}/analysis for
    each story found. Missing stories are simply absent from the response.

    The homepage needs analyses for ~30 stories to render narratives, bias
    explanations, and dispute scores. Doing that as N parallel
    /stories/{id}/analysis calls from Next.js to Railway (US) costs 30
    round trips per cache miss — this endpoint cuts that to one.
    """
    import json as _json

    # Parse + dedupe IDs, ignore junk
    id_list: list[uuid.UUID] = []
    for raw in ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            id_list.append(uuid.UUID(raw))
        except (ValueError, AttributeError):
            continue
    if not id_list:
        return {}

    # Cap to something reasonable so a crafted URL can't DoS the endpoint.
    id_list = id_list[:60]

    result = await db.execute(select(Story).where(Story.id.in_(id_list)))
    stories = result.scalars().all()

    out: dict[str, dict] = {}
    for story in stories:
        extra: dict = {}
        if story.summary_en:
            try:
                extra = _json.loads(story.summary_en)
            except Exception:
                extra = {}
        out[str(story.id)] = {
            "story_id": str(story.id),
            "summary_fa": story.summary_fa,
            "state_summary_fa": extra.get("state_summary_fa"),
            "diaspora_summary_fa": extra.get("diaspora_summary_fa"),
            "independent_summary_fa": extra.get("independent_summary_fa"),
            "bias_explanation_fa": extra.get("bias_explanation_fa"),
            "scores": extra.get("scores"),
            "source_neutrality": extra.get("source_neutrality"),
            "dispute_score": extra.get("dispute_score"),
            "loaded_words": extra.get("loaded_words"),
            "narrative_arc": extra.get("narrative_arc"),
            "delta": extra.get("delta"),
            "analyst": extra.get("analyst"),
            "silence_analysis": extra.get("silence_analysis"),
            "coordinated_messaging": extra.get("coordinated_messaging"),
        }
    return out


@router.get("/weekly-digest")
@_limiter.limit("30/minute")
async def weekly_digest(request: Request, db: AsyncSession = Depends(get_db)):
    """Return the latest weekly digest."""
    from app.models.maintenance_log import MaintenanceLog

    # Check DB first (stored by niloofar_weekly.py or maintenance)
    result = await db.execute(
        select(MaintenanceLog)
        .where(MaintenanceLog.status == "weekly_digest")
        .order_by(MaintenanceLog.run_at.desc())
        .limit(1)
    )
    log = result.scalar_one_or_none()
    if log and log.results:
        return {"status": "ok", "content": log.results, "generated_at": log.run_at.isoformat() if log.run_at else None}

    # Fallback: check local file
    from pathlib import Path
    data_dir = Path(__file__).parent.parent.parent.parent / "data" / "weekly_reports"
    if data_dir.exists():
        reports = sorted(data_dir.glob("weekly_*.md"), reverse=True)
        if reports:
            return {"status": "ok", "content": reports[0].read_text(encoding="utf-8")}

    return {"status": "no_data", "content": None}


@router.get("/insights/loaded-words")
@_limiter.limit("60/minute")
async def loaded_words_insights(request: Request, db: AsyncSession = Depends(get_db)):
    """Aggregate loaded_words across top trending stories."""
    import json as _json
    from collections import Counter

    result = await db.execute(
        select(Story)
        .where(Story.article_count >= 5)
        .order_by(Story.trending_score.desc())
        .limit(20)
    )
    stories = result.scalars().all()

    conservative_counter: Counter = Counter()
    opposition_counter: Counter = Counter()

    # Source 1: loaded_words from story analysis
    for story in stories:
        if not story.summary_en:
            continue
        try:
            data = _json.loads(story.summary_en)
        except Exception:
            continue
        loaded = data.get("loaded_words")
        if not loaded or not isinstance(loaded, dict):
            continue
        for word in loaded.get("conservative", []):
            if isinstance(word, str) and word.strip():
                conservative_counter[word.strip()] += 1
        for word in loaded.get("opposition", []):
            if isinstance(word, str) and word.strip():
                opposition_counter[word.strip()] += 1

    return {
        "conservative": [
            {"word": w, "count": c}
            for w, c in conservative_counter.most_common(5)
        ],
        "opposition": [
            {"word": w, "count": c}
            for w, c in opposition_counter.most_common(5)
        ],
    }


@router.post(
    "/{story_id}/summarize",
    response_model=StoryAnalysisResponse,
    dependencies=[Depends(require_admin)],
)
@_limiter.limit("10/hour")
async def summarize_story(request: Request, story_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Force-generate a new summary using OpenAI. Admin-only to prevent cost abuse."""
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if not story.articles:
        raise HTTPException(status_code=400, detail="No articles")
    # Respect hand-edits: if an admin has manually edited this story, don't
    # overwrite their work with fresh LLM output.
    if story.is_edited:
        raise HTTPException(
            status_code=409,
            detail="Story is hand-edited (is_edited=true). Clear the flag first if you want to regenerate.",
        )

    articles_info = [
        {
            "title": a.title_original or a.title_fa or a.title_en or "",
            "content": (a.content_text or a.summary or "")[:1500],
            "source_name_fa": a.source.name_fa if a.source else "نامشخص",
            "state_alignment": a.source.state_alignment if a.source else "",
        }
        for a in story.articles
    ]
    try:
        analysis = await generate_story_analysis(story, articles_info)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    import json as _json
    story.summary_fa = analysis.get("summary_fa")
    # Store full analysis as JSON in summary_en
    story.summary_en = _json.dumps({
        "state_summary_fa": analysis.get("state_summary_fa"),
        "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
        "independent_summary_fa": analysis.get("independent_summary_fa"),
        "bias_explanation_fa": analysis.get("bias_explanation_fa"),
        "scores": analysis.get("scores"),
    }, ensure_ascii=False)
    await db.commit()
    return StoryAnalysisResponse(
        story_id=story.id,
        summary_fa=analysis.get("summary_fa"),
        state_summary_fa=analysis.get("state_summary_fa"),
        diaspora_summary_fa=analysis.get("diaspora_summary_fa"),
        independent_summary_fa=analysis.get("independent_summary_fa"),
        bias_explanation_fa=analysis.get("bias_explanation_fa"),
        scores=analysis.get("scores"),
        analyst=analysis.get("analyst"),
    )


@router.get("/{story_id}/analyst-takes")
@_limiter.limit("60/minute")
async def get_analyst_takes(
    request: Request,
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return analyst takes for a story, joined with analyst info."""
    result = await db.execute(
        select(AnalystTake)
        .options(selectinload(AnalystTake.analyst))
        .where(AnalystTake.story_id == story_id)
        .order_by(AnalystTake.published_at.desc().nullslast())
    )
    takes = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "analyst_id": str(t.analyst_id) if t.analyst_id else None,
            "analyst_name_fa": t.analyst.name_fa if t.analyst else None,
            "analyst_name_en": t.analyst.name_en if t.analyst else None,
            "analyst_slug": t.analyst.slug if t.analyst else None,
            "analyst_photo_url": t.analyst.photo_url if t.analyst else None,
            "analyst_political_leaning": t.analyst.political_leaning if t.analyst else None,
            "summary_fa": t.summary_fa,
            "key_claim": t.key_claim,
            "take_type": t.take_type,
            "confidence_direction": t.confidence_direction,
            "verified_later": t.verified_later,
            "verification_note": t.verification_note,
            "published_at": t.published_at.isoformat() if t.published_at else None,
        }
        for t in takes
    ]


@router.get("/{story_id}/article-positions")
@_limiter.limit("60/minute")
async def article_positions(
    request: Request,
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return 2D-projected article embeddings for the narrative map visualization."""
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Collect articles that have embeddings
    articles_with_emb = [
        a for a in story.articles
        if a.embedding and isinstance(a.embedding, list) and len(a.embedding) > 0
    ]

    if not articles_with_emb:
        return JSONResponse(content=[])

    # Alignment position fallback: spread articles by source alignment
    ALIGNMENT_X = {
        "state": 15, "semi_state": 35, "independent": 50, "diaspora": 80,
    }

    if len(articles_with_emb) < 3:
        # Not enough for PCA — position by source alignment with slight jitter
        positions = []
        align_counts: dict[str, int] = {}
        for a in articles_with_emb:
            align = a.source.state_alignment if a.source else "independent"
            idx = align_counts.get(align, 0)
            align_counts[align] = idx + 1
            positions.append({
                "article_id": str(a.id),
                "title_fa": a.title_fa or a.title_original or "",
                "source_slug": a.source.slug if a.source else None,
                "source_name_fa": a.source.name_fa if a.source else None,
                "source_logo_url": a.source.logo_url if a.source else None,
                "article_url": a.url,
                "source_alignment": align,
                "x": ALIGNMENT_X.get(align, 50) + idx * 5,
                "y": 50 + idx * 10,
            })
        return JSONResponse(content=positions)

    # Hybrid positioning: X = source alignment (meaningful), Y = PCA content variation
    import numpy as np

    # X: based on source alignment with jitter to avoid overlap
    align_jitter: dict[str, int] = {}
    ALIGNMENT_X_BASE = {
        "state": 80, "semi_state": 65, "independent": 50, "diaspora": 20,
    }

    # Y: PCA first component for content variation within the story
    embeddings = [a.embedding for a in articles_with_emb]
    matrix = np.array(embeddings, dtype=np.float64)
    mean = matrix.mean(axis=0)
    centered = matrix - mean

    # Get first principal component for Y spread
    try:
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        pc1 = eigenvectors[:, -1]  # top eigenvector
        y_projected = centered @ pc1
        # Normalize to 15-85 range
        mn, mx = y_projected.min(), y_projected.max()
        if mx > mn:
            y_normalized = 15 + (y_projected - mn) / (mx - mn) * 70
        else:
            y_normalized = np.full(len(y_projected), 50.0)
    except Exception:
        y_normalized = np.linspace(20, 80, len(articles_with_emb))

    positions = []
    for i, a in enumerate(articles_with_emb):
        align = a.source.state_alignment if a.source else "independent"
        jitter_idx = align_jitter.get(align, 0)
        align_jitter[align] = jitter_idx + 1
        # X: alignment base + small jitter to separate same-source articles
        x = ALIGNMENT_X_BASE.get(align, 50) + (jitter_idx % 3 - 1) * 5

        positions.append({
            "article_id": str(a.id),
            "title_fa": a.title_fa or a.title_original or "",
            "source_slug": a.source.slug if a.source else None,
            "source_name_fa": a.source.name_fa if a.source else None,
            "source_logo_url": a.source.logo_url if a.source else None,
            "article_url": a.url,
            "source_alignment": align,
            "x": round(max(5, min(95, x)), 2),
            "y": round(float(y_normalized[i]), 2),
        })

    return JSONResponse(content=positions)


@router.get("/{story_id}", response_model=StoryDetail)
async def get_story(
    story_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Story)
        .options(
            selectinload(Story.articles)
            .selectinload(Article.source),
            selectinload(Story.articles)
            .selectinload(Article.bias_scores),
        )
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Build the response BEFORE committing — we want to touch every attribute
    # on `story` while the session is still clean, so Pydantic's validation
    # doesn't trigger any async refresh after a commit (which was the source
    # of a MissingGreenlet error when view_count was bumped inline).
    articles_with_bias = []
    for article in story.articles:
        article_data = StoryArticleWithBias(
            **{k: v for k, v in ArticleBriefDict(article).items()},
            source_name_en=article.source.name_en if article.source else None,
            source_name_fa=article.source.name_fa if article.source else None,
            source_slug=article.source.slug if article.source else None,
            source_state_alignment=article.source.state_alignment if article.source else None,
            bias_scores=[BiasScoreResponse.model_validate(bs) for bs in article.bias_scores],
        )
        articles_with_bias.append(article_data)

    # Use the same helper as the other endpoints — it returns a populated
    # StoryBrief with image_url / state_pct / diaspora_pct / independent_pct,
    # fields that aren't on the ORM model.
    brief = _story_brief_with_extras(story)

    response = StoryDetail(
        **brief.model_dump(),
        summary_en=story.summary_en,
        summary_fa=story.summary_fa,
        articles=articles_with_bias,
    )

    # Bump view_count AFTER the response is built, in a background task so
    # the commit can't interfere with response serialization.
    story_uuid = story.id
    background_tasks.add_task(_bump_view_count, story_uuid)

    return response


async def _bump_view_count(story_id: uuid.UUID) -> None:
    """Increment a story's view_count in a separate session after response."""
    from app.database import async_session

    try:
        async with async_session() as session:
            await session.execute(
                Story.__table__.update()
                .where(Story.id == story_id)
                .values(view_count=Story.view_count + 1)
            )
            await session.commit()
    except Exception as e:
        logger.warning("view_count increment failed for story %s: %s", story_id, e)


def _is_bad_image(url: str) -> bool:
    """Filter out obviously bad image URLs (tracking pixels, placeholders, tiny icons)."""
    if not url or len(url) < 10:
        return True
    lower = url.lower()
    # Common bad patterns
    bad_patterns = [
        "pixel", "1x1", "blank.", "spacer.", "transparent.",
        "placeholder", "default.jpg", "default.png", "no-image",
        "logo-", "/logo.", "/icon.", "favicon",
        "apple-touch-icon",  # Source logos, not story images
        "google.com/s2/favicons",  # Tiny favicons (16-128px), often 404 for geo-blocked sites
        ".svg",  # SVGs are usually logos/icons
        ".ico",  # Favicon files
        "telesco.pe",  # Telegram CDN auth tokens expire — unreliable public URLs
        "cdn.telegram",  # Same story for the older Telegram CDN host
    ]
    return any(p in lower for p in bad_patterns)


_LATIN_TO_FARSI = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_farsi_digits(text: str | None) -> str | None:
    """Convert Latin digits to Farsi digits in a string."""
    if not text:
        return text
    return text.translate(_LATIN_TO_FARSI)


def _story_brief_with_extras(story: Story) -> StoryBrief:
    """Build StoryBrief with image_url and coverage percentages.

    Image selection:
    1. Collect articles with live, non-bad image_url values
    2. Score each by title-word overlap with the story title (≥3 char words)
    3. Prefer R2 / stable-storage URLs, break ties by highest overlap,
       then by longest URL (often higher-resolution on Telegram CDN)
    """
    import json as _json

    from app.config import settings

    brief = StoryBrief.model_validate(story)

    # Normalize Latin digits → Farsi in titles served to the frontend
    brief.title_fa = _to_farsi_digits(brief.title_fa)

    # Manual override: Story ORM has no image_url column, so the curator's
    # override is stored inside the summary_en JSON blob as
    # "manual_image_url" (written by journalist_audit.apply_fix and by the
    # dashboard editor). When the story is is_edited and the blob has a
    # manual_image_url, trust it and skip the title-overlap scorer.
    manual_image = None
    if getattr(story, "is_edited", False) and story.summary_en:
        try:
            _blob = _json.loads(story.summary_en)
            candidate = _blob.get("manual_image_url")
            if candidate and not _is_bad_image(candidate):
                manual_image = candidate
        except Exception:
            manual_image = None

    if manual_image:
        brief.image_url = manual_image
        _skip_scorer = True
    else:
        _skip_scorer = False

    def _title_words(s: str | None) -> set:
        if not s:
            return set()
        return {w for w in s.split() if len(w) >= 3}

    story_words = _title_words(story.title_fa or story.title_en)

    # Collect candidate articles with a usable image
    candidates = [
        a for a in story.articles
        if a.image_url and not _is_bad_image(a.image_url)
    ]
    if candidates and not _skip_scorer:
        def _score(a) -> tuple:
            art_words = _title_words(a.title_fa or a.title_original or a.title_en)
            overlap = len(story_words & art_words)
            is_stable = a.image_url.startswith("/images/") or (
                settings.r2_public_url
                and a.image_url.startswith(settings.r2_public_url)
            )
            # Tuple is sorted in priority order:
            # (stable URL > higher overlap > longer URL)
            return (1 if is_stable else 0, overlap, len(a.image_url))

        best = max(candidates, key=_score)
        brief.image_url = best.image_url

    # Last-resort fallback: if no article image AND no manual override,
    # use the primary active source's logo so the homepage card isn't blank.
    # Skip bad logos (tiny favicons, geo-blocked Google Favicons) and prefer
    # active sources over deactivated ones.
    if not brief.image_url:
        source_counts: dict = {}
        for a in story.articles:
            if (
                a.source
                and a.source.logo_url
                and not _is_bad_image(a.source.logo_url)
                and getattr(a.source, "is_active", True)
            ):
                source_counts[a.source.slug] = source_counts.get(a.source.slug, 0) + 1
        if source_counts:
            top_slug = max(source_counts, key=source_counts.get)  # type: ignore[arg-type]
            for a in story.articles:
                if a.source and a.source.slug == top_slug and a.source.logo_url:
                    brief.image_url = a.source.logo_url
                    break

    # Coverage percentages — legacy 3-bucket + new 4-subgroup taxonomy
    total = len(story.articles)
    if total > 0:
        from app.schemas.story import NarrativeGroupPercentages
        from app.services.narrative_groups import (
            NARRATIVE_GROUPS_ORDER,
            counts_to_percentages,
            narrative_group,
        )

        state = 0
        diaspora = 0
        independent = 0
        group_counts = {g: 0 for g in NARRATIVE_GROUPS_ORDER}
        for a in story.articles:
            if a.source:
                align = a.source.state_alignment
                if align in ("state", "semi_state"):
                    state += 1
                elif align == "diaspora":
                    diaspora += 1
                else:
                    independent += 1
                group_counts[narrative_group(a.source)] += 1
            else:
                independent += 1
                # Articles without a source fall into moderate_diaspora by
                # default — same bucket independent-outside sources land in.
                group_counts["moderate_diaspora"] += 1
        brief.state_pct = round(state * 100 / total)
        brief.diaspora_pct = round(diaspora * 100 / total)
        brief.independent_pct = round(independent * 100 / total)

        pct = counts_to_percentages(group_counts)
        brief.narrative_groups = NarrativeGroupPercentages(**pct)
        brief.inside_border_pct = pct["principlist"] + pct["reformist"]
        brief.outside_border_pct = pct["moderate_diaspora"] + pct["radical_diaspora"]
    return brief


def ArticleBriefDict(article: Article) -> dict:
    """Helper to convert Article ORM to dict for ArticleBrief fields."""
    return {
        "id": article.id,
        "source_id": article.source_id,
        "story_id": article.story_id,
        "title_original": article.title_original,
        "title_en": article.title_en,
        "title_fa": article.title_fa,
        "url": article.url,
        "summary": article.summary,
        "image_url": article.image_url,
        "author": article.author,
        "language": article.language,
        "published_at": article.published_at,
        "ingested_at": article.ingested_at,
    }
