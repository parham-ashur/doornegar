import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.admin import require_admin
from app.config import settings
from app.database import get_db
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


@router.get("", response_model=StoryListResponse)
async def list_stories(
    topic: str | None = None,
    blindspots_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Story)
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
        stories=[StoryBrief.model_validate(s) for s in stories],
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
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.article_count >= min_articles)
        .order_by(Story.priority.desc(), Story.trending_score.desc())
        .limit(limit)
    )
    stories = result.scalars().all()
    return [_story_brief_with_extras(s) for s in stories]


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
    )


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
    )


@router.get("/{story_id}", response_model=StoryDetail)
async def get_story(story_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
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

    story_data = StoryBrief.model_validate(story)
    return StoryDetail(
        **story_data.model_dump(),
        summary_en=story.summary_en,
        summary_fa=story.summary_fa,
        articles=articles_with_bias,
    )


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
        ".svg",  # SVGs are usually logos/icons
    ]
    return any(p in lower for p in bad_patterns)


def _story_brief_with_extras(story: Story) -> StoryBrief:
    """Build StoryBrief with image_url and coverage percentages."""
    from app.config import settings

    brief = StoryBrief.model_validate(story)
    # Pick best image: prefer permanent-storage URLs (R2 or local), skip bad URLs
    all_candidates = [
        a.image_url for a in story.articles
        if a.image_url and not _is_bad_image(a.image_url)
    ]
    # Stable storage URLs (R2 public URL or local /images/) are preferred
    stable = [
        c for c in all_candidates
        if c.startswith("/images/")
        or (settings.r2_public_url and c.startswith(settings.r2_public_url))
    ]
    if stable:
        brief.image_url = stable[0]
    elif all_candidates:
        # Fallback: prefer longer URLs (often higher res)
        all_candidates.sort(key=len, reverse=True)
        brief.image_url = all_candidates[0]
    # Coverage percentages
    total = len(story.articles)
    if total > 0:
        state = 0
        diaspora = 0
        independent = 0
        for a in story.articles:
            if a.source:
                align = a.source.state_alignment
                if align in ("state", "semi_state"):
                    state += 1
                elif align == "diaspora":
                    diaspora += 1
                else:
                    independent += 1
            else:
                independent += 1
        brief.state_pct = round(state * 100 / total)
        brief.diaspora_pct = round(diaspora * 100 / total)
        brief.independent_pct = round(independent * 100 / total)
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
