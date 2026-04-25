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
        article_neutrality=extra.get("article_neutrality"),
        article_evidence=extra.get("article_evidence"),
        analysis_locked_at=extra.get("analysis_locked_at"),
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
            # 4-subgroup narrative bullets (principlist/reformist/moderate/radical).
            # Shape: {"inside": {"principlist": [...], "reformist": [...]},
            #         "outside": {"moderate": [...], "radical": [...]}}
            # Surfaced here so the homepage hero card can render the colored
            # sub-columns without a second fetch per story.
            "narrative": extra.get("narrative"),
            "scores": extra.get("scores"),
            "source_neutrality": extra.get("source_neutrality"),
            "article_neutrality": extra.get("article_neutrality"),
            "article_evidence": extra.get("article_evidence"),
            "analysis_locked_at": extra.get("analysis_locked_at"),
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


@router.get("/{story_id}/related")
@_limiter.limit("120/minute")
async def get_related_stories(
    request: Request,
    story_id: uuid.UUID,
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return stories related to `story_id`, arc-siblings first, then
    cosine-similar neighbors by centroid embedding.

    Used by the bottom-of-page «خبرهای مرتبط» slider on story pages.
    Excludes the source story, hidden stories (article_count<5), and
    de-duplicates when an arc sibling is also a close cosine match.
    """
    from app.nlp.embeddings import cosine_similarity

    source = (await db.execute(select(Story).where(Story.id == story_id))).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Story not found")

    picked_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = {story_id}

    # ── Arc siblings first (curated grouping) ──
    if source.arc_id:
        arc_result = await db.execute(
            select(Story)
            .where(
                Story.arc_id == source.arc_id,
                Story.id != story_id,
                Story.article_count >= 5,
            )
            .order_by(Story.arc_order.asc().nullslast(), Story.first_published_at.desc().nullslast())
            .limit(limit)
        )
        for s in arc_result.scalars().all():
            if s.id not in seen:
                picked_ids.append(s.id)
                seen.add(s.id)

    # ── Cosine-similar fill if we still need more ──
    need = limit - len(picked_ids)
    if need > 0 and isinstance(source.centroid_embedding, list) and source.centroid_embedding:
        # Pull candidates with centroids. 500 is plenty — visible stories
        # rarely exceed that and the loop is O(N) cosine.
        cand_result = await db.execute(
            select(Story)
            .where(
                Story.id != story_id,
                Story.article_count >= 5,
                Story.centroid_embedding.isnot(None),
            )
            .order_by(Story.first_published_at.desc().nullslast())
            .limit(500)
        )
        src_vec = source.centroid_embedding
        scored: list[tuple[float, Story]] = []
        for s in cand_result.scalars().all():
            if s.id in seen:
                continue
            c = s.centroid_embedding
            if not isinstance(c, list) or not c or any(v is None for v in c):
                continue
            try:
                sim = cosine_similarity(src_vec, c)
            except (TypeError, ValueError):
                continue
            if sim >= 0.62:
                scored.append((sim, s))
        scored.sort(key=lambda t: -t[0])
        for _, s in scored[:need]:
            picked_ids.append(s.id)
            seen.add(s.id)

    if not picked_ids:
        return {"stories": []}

    # Fetch the picked stories with articles eagerly loaded so we can
    # pick a representative image per card without extra round trips.
    detail_result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.id.in_(picked_ids))
    )
    by_id = {s.id: s for s in detail_result.scalars().all()}

    def _is_bad_img(url: str | None) -> bool:
        if not url:
            return True
        u = url.lower()
        return (
            "favicon" in u or "icon" in u or "logo" in u or "sprite" in u
            or u.endswith(".svg") or "1x1" in u or "placeholder" in u
        )

    def _pick_real_image(s: Story) -> str | None:
        # Only real article images or R2-stable covers — NO logo fallback.
        # Related-stories filters out logo-only cards to avoid showing
        # placeholder-y tiles at the bottom of story pages. Stories without
        # a real image flow to the /admin/hitl/stories-without-image queue.
        r2_prefix = settings.r2_public_url or ""
        for a in s.articles or []:
            if a.image_url and not _is_bad_img(a.image_url):
                if r2_prefix and a.image_url.startswith(r2_prefix):
                    return a.image_url
        for a in s.articles or []:
            if a.image_url and not _is_bad_img(a.image_url):
                return a.image_url
        return None

    out = []
    for sid in picked_ids:
        s = by_id.get(sid)
        if not s:
            continue
        img = _pick_real_image(s)
        if img is None:
            continue
        out.append({
            "id": str(s.id),
            "slug": s.slug,
            "title_fa": s.title_fa,
            "title_en": s.title_en,
            "article_count": s.article_count,
            "source_count": s.source_count,
            "first_published_at": s.first_published_at.isoformat() if s.first_published_at else None,
            "arc_id": str(s.arc_id) if s.arc_id else None,
            "image_url": img,
        })
    return {"stories": out, "count": len(out)}


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

    # Pull arc sibling strip when this story belongs to one. Single
    # extra query — no-op when arc_id is None (most stories).
    arc_brief = None
    if getattr(story, "arc_id", None) is not None:
        from app.models.story_arc import StoryArc
        from app.schemas.story import ArcChapterBrief, StoryArcBrief

        arc = await db.get(StoryArc, story.arc_id)
        if arc is not None:
            chapters_q = await db.execute(
                select(Story.id, Story.title_fa, Story.arc_order)
                .where(Story.arc_id == arc.id)
                .order_by(Story.arc_order.asc().nullslast(), Story.first_published_at.asc().nullslast())
            )
            chapters = [
                ArcChapterBrief(
                    story_id=str(r.id),
                    title_fa=r.title_fa,
                    order=r.arc_order if r.arc_order is not None else i,
                )
                for i, r in enumerate(chapters_q.all())
            ]
            arc_brief = StoryArcBrief(
                id=str(arc.id),
                title_fa=arc.title_fa,
                slug=arc.slug,
                chapters=chapters,
            )

    response = StoryDetail(
        **brief.model_dump(),
        summary_en=story.summary_en,
        summary_fa=story.summary_fa,
        editorial_context_fa=story.editorial_context_fa,
        articles=articles_with_bias,
        arc=arc_brief,
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
        # Icon/PWA patterns captured from broken RSS <media:content> tags
        "ico-192x192", "ico-512x512", "webapp/ico-", "manifest-icon",
    ]
    if any(p in lower for p in bad_patterns):
        return True
    # Iran International's Sanity CDN returns 400 on bare hash paths —
    # a valid URL must end with a -WxH.ext transform (e.g. -800x531.jpg).
    # The ingester sometimes captures the bare form from article HTML.
    if "i.iranintl.com/" in lower:
        import re as _re
        if not _re.search(r"-\d+x\d+\.(jpg|jpeg|png|webp)(\?|$)", lower):
            return True
    return False


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
        brief.has_real_image = True
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
        brief.has_real_image = True

    # Last-resort fallback: if no article image AND no manual override,
    # use the primary active source's logo so the homepage card isn't blank.
    # has_real_image stays False on this path so homepage/related filters
    # can hide cards that would otherwise show with only a logo.
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

    # Coverage percentages — legacy 3-bucket + new 4-subgroup taxonomy.
    # Per-source dedup: one vote per unique outlet, not per article.
    # An outlet that publishes 20 pieces on the same topic shouldn't
    # dominate a percentage over an outlet that publishes one cover
    # piece — this is a TRANSPARENCY platform measuring which outlets
    # cover what, not raw article volume. Blindspot / trending logic
    # still uses article_count, so the volume signal isn't lost.
    sources_seen: dict[str, object] = {}
    for a in story.articles:
        if a.source and a.source.slug not in sources_seen:
            sources_seen[a.source.slug] = a.source
    total_sources = len(sources_seen)
    if total_sources > 0:
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
        for src in sources_seen.values():
            align = getattr(src, "state_alignment", None)
            if align in ("state", "semi_state"):
                state += 1
            elif align == "diaspora":
                diaspora += 1
            else:
                independent += 1
            group_counts[narrative_group(src)] += 1

        brief.state_pct = round(state * 100 / total_sources)
        brief.diaspora_pct = round(diaspora * 100 / total_sources)
        brief.independent_pct = round(independent * 100 / total_sources)

        pct = counts_to_percentages(group_counts)
        brief.narrative_groups = NarrativeGroupPercentages(**pct)
        brief.inside_border_pct = pct["principlist"] + pct["reformist"]
        brief.outside_border_pct = pct["moderate_diaspora"] + pct["radical_diaspora"]

    # Update signal: two layers.
    # 1) Hourly layer — written by step_detect_hourly_updates when a story
    #    gains articles in the last hour AND a trigger fires. Fresher but
    #    narrower in what it catches (side flip, coverage ≥15pp, ≥5-article
    #    burst). We prefer it when its detected_at is within the last 4h.
    # 2) 24h snapshot layer — compares live analysis state to the nightly
    #    snapshot. Catches slower signals (dispute_score shifted, bias
    #    rewrite) that hourly can't see.
    brief.update_signal = None
    try:
        hourly = getattr(story, "hourly_update_signal", None)
        use_hourly = False
        if hourly and isinstance(hourly, dict) and hourly.get("has_update"):
            detected_at = hourly.get("detected_at")
            if detected_at:
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    dt = _dt.fromisoformat(detected_at.replace("Z", "+00:00"))
                    age_s = (_dt.now(_tz.utc) - dt).total_seconds()
                    if 0 <= age_s <= 4 * 3600:
                        use_hourly = True
                except Exception:
                    pass
        if use_hourly:
            brief.update_signal = hourly
        else:
            from app.services.story_freshness import compute_update_signal, diff_narratives

            blob_for_signal = {}
            if story.summary_en:
                try:
                    blob_for_signal = _json.loads(story.summary_en)
                except Exception:
                    blob_for_signal = {}
            brief.update_signal = compute_update_signal(
                current_article_count=story.article_count or 0,
                current_dispute_score=blob_for_signal.get("dispute_score"),
                current_inside_pct=brief.inside_border_pct,
                current_outside_pct=brief.outside_border_pct,
                current_bias_explanation_fa=blob_for_signal.get("bias_explanation_fa"),
                snapshot=getattr(story, "analysis_snapshot_24h", None),
            )
            # Attach sentence-level delta when the signal is live, so the
            # UI can render a colored به‌روز callout showing exactly which
            # bits of the bias comparison or side narratives are new
            # since last night's snapshot. Cheap — pure string compare.
            if brief.update_signal and brief.update_signal.get("has_update"):
                try:
                    brief.update_signal["delta"] = diff_narratives(
                        current_bias=blob_for_signal.get("bias_explanation_fa"),
                        # state_summary_fa / diaspora_summary_fa live in
                        # the summary_en JSONB blob, not Story columns.
                        current_state=blob_for_signal.get("state_summary_fa"),
                        current_diaspora=blob_for_signal.get("diaspora_summary_fa"),
                        snapshot=getattr(story, "analysis_snapshot_24h", None),
                    )
                except Exception:
                    pass
    except Exception:
        brief.update_signal = None

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
