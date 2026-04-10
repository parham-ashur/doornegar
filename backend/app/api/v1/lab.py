import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.admin import require_admin
from app.database import get_db
from app.rate_limit import limiter as _limiter
from app.models.article import Article
from app.models.source import Source
from app.models.topic import Topic, TopicArticle
from app.schemas.topic import (
    AnalystPerspective,
    TopicAnalysis,
    TopicArticleInfo,
    TopicBrief,
    TopicCreate,
    TopicDetail,
    TopicListResponse,
    TopicUpdate,
)
from app.services.topic_service import (
    create_topic,
    generate_analyst_perspectives,
    generate_topic_analysis,
    match_articles_to_topic,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _topic_to_brief(topic: Topic) -> TopicBrief:
    """Convert Topic ORM to TopicBrief with computed fields."""
    # Resolve image from first matched article if not set manually
    image_url = topic.image_url
    if not image_url and hasattr(topic, "topic_articles"):
        for ta in topic.topic_articles:
            if hasattr(ta, "article") and ta.article and ta.article.image_url:
                image_url = ta.article.image_url
                break

    return TopicBrief(
        id=topic.id,
        title_fa=topic.title_fa,
        title_en=topic.title_en,
        slug=topic.slug,
        mode=topic.mode,
        is_auto=topic.is_auto,
        article_count=topic.article_count,
        is_active=topic.is_active,
        image_url=image_url,
        has_articles=topic.article_count > 0 and topic.analysis_json is not None,
        has_analysts=topic.analyst_json is not None and len(topic.analyst_json) > 0,
        analysis_fa=topic.analysis_fa,
        analyzed_at=topic.analyzed_at,
        created_at=topic.created_at,
    )


@router.get("/topics", response_model=TopicListResponse)
async def list_topics(
    mode: str | None = None,
    is_auto: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Topic)
        .options(selectinload(Topic.topic_articles).selectinload(TopicArticle.article))
        .where(Topic.is_active.is_(True))
    )
    count_query = select(func.count(Topic.id)).where(Topic.is_active.is_(True))

    if mode:
        query = query.where(Topic.mode == mode)
        count_query = count_query.where(Topic.mode == mode)
    if is_auto is not None:
        query = query.where(Topic.is_auto == is_auto)
        count_query = count_query.where(Topic.is_auto == is_auto)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Topic.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    topics = result.scalars().all()

    return TopicListResponse(
        topics=[_topic_to_brief(t) for t in topics],
        total=total,
    )


@router.post("/topics", response_model=TopicBrief, dependencies=[Depends(require_admin)])
async def create_topic_endpoint(
    body: TopicCreate,
    db: AsyncSession = Depends(get_db),
):
    if body.mode not in ("news", "debate"):
        raise HTTPException(status_code=400, detail="mode must be 'news' or 'debate'")

    topic = await create_topic(
        title_fa=body.title_fa,
        db=db,
        mode=body.mode,
        title_en=body.title_en,
        description_fa=body.description_fa,
    )
    await db.commit()
    await db.refresh(topic)
    return _topic_to_brief(topic)


@router.get("/topics/{topic_id}", response_model=TopicDetail)
async def get_topic(topic_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Topic)
        .options(
            selectinload(Topic.topic_articles)
            .selectinload(TopicArticle.article)
            .selectinload(Article.source)
        )
        .where(Topic.id == topic_id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Build article info list
    articles = []
    for ta in topic.topic_articles:
        art = ta.article
        articles.append(TopicArticleInfo(
            id=art.id,
            title_fa=art.title_fa,
            title_en=art.title_en,
            url=art.url,
            source_name_fa=art.source.name_fa if art.source else None,
            source_state_alignment=art.source.state_alignment if art.source else None,
            match_confidence=ta.match_confidence,
            match_method=ta.match_method,
            published_at=art.published_at,
        ))

    # Parse analysis JSON
    analysis = None
    if topic.analysis_json:
        try:
            analysis = TopicAnalysis(**topic.analysis_json)
        except Exception:
            analysis = None

    # Parse analyst perspectives
    analysts = []
    if topic.analyst_json:
        try:
            analysts = [AnalystPerspective(**a) for a in topic.analyst_json]
        except Exception:
            analysts = []

    brief = _topic_to_brief(topic)
    return TopicDetail(
        **brief.model_dump(),
        description_fa=topic.description_fa,
        analysis=analysis,
        analysts=analysts,
        articles=articles,
    )


@router.put("/topics/{topic_id}", response_model=TopicBrief, dependencies=[Depends(require_admin)])
async def update_topic(
    topic_id: uuid.UUID,
    body: TopicUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    allowed = {"title_fa", "title_en", "description_fa", "mode", "is_active", "image_url"}
    for field, value in body.model_dump(exclude_unset=True).items():
        if field in allowed:
            setattr(topic, field, value)

    await db.commit()
    await db.refresh(topic)
    return _topic_to_brief(topic)


@router.delete("/topics/{topic_id}", dependencies=[Depends(require_admin)])
async def deactivate_topic(topic_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    topic.is_active = False
    await db.commit()
    return {"status": "deactivated"}


@router.post("/topics/{topic_id}/match", dependencies=[Depends(require_admin)])
async def trigger_match(
    topic_id: uuid.UUID,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    linked = await match_articles_to_topic(topic, db, days=days)
    await db.commit()
    return {"matched": linked, "total_articles": topic.article_count}


@router.post("/topics/{topic_id}/analyze", response_model=TopicDetail, dependencies=[Depends(require_admin)])
@_limiter.limit("10/hour")
async def trigger_analysis(request: Request, topic_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Topic)
        .options(
            selectinload(Topic.topic_articles)
            .selectinload(TopicArticle.article)
            .selectinload(Article.source)
        )
        .where(Topic.id == topic_id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    if not topic.topic_articles:
        raise HTTPException(status_code=400, detail="No articles matched. Run /match first.")

    articles_info = []
    for ta in topic.topic_articles:
        art = ta.article
        articles_info.append({
            "title": art.title_original or art.title_fa or art.title_en or "",
            "content": (art.content_text or art.summary or "")[:1500],
            "source_name_fa": art.source.name_fa if art.source else "نامشخص",
            "state_alignment": art.source.state_alignment if art.source else "",
        })

    try:
        analysis = await generate_topic_analysis(topic, articles_info)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    from datetime import datetime, timezone
    topic.analysis_json = analysis
    topic.analysis_fa = analysis.get("summary_fa") or analysis.get("topic_summary_fa")
    topic.analyzed_at = datetime.now(timezone.utc)

    # Auto-resolve image from articles
    if not topic.image_url:
        for ta in topic.topic_articles:
            if ta.article and ta.article.image_url:
                topic.image_url = ta.article.image_url
                break

    await db.commit()
    return await get_topic(topic_id, db)


@router.post("/topics/{topic_id}/generate-analysts", dependencies=[Depends(require_admin)])
@_limiter.limit("10/hour")
async def generate_analysts(request: Request, topic_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    summary = topic.analysis_fa or topic.title_fa
    try:
        analysts = await generate_analyst_perspectives(topic, summary)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    topic.analyst_json = analysts
    await db.commit()

    return {"generated": len(analysts), "analysts": analysts}
