import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
from app.schemas.article import ArticleBrief, ArticleDetail, ArticleListResponse

router = APIRouter()


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    source_id: uuid.UUID | None = None,
    story_id: uuid.UUID | None = None,
    language: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Article)
    count_query = select(func.count(Article.id))

    if source_id:
        query = query.where(Article.source_id == source_id)
        count_query = count_query.where(Article.source_id == source_id)
    if story_id:
        query = query.where(Article.story_id == story_id)
        count_query = count_query.where(Article.story_id == story_id)
    if language:
        query = query.where(Article.language == language)
        count_query = count_query.where(Article.language == language)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Article.published_at.desc().nullslast())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    articles = result.scalars().all()

    return ArticleListResponse(
        articles=[ArticleBrief.model_validate(a) for a in articles],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleDetail.model_validate(article)
