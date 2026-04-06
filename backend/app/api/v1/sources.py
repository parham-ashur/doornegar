import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.source import Source
from app.schemas.source import SourceListResponse, SourceResponse

router = APIRouter()


@router.get("", response_model=SourceListResponse)
async def list_sources(
    state_alignment: str | None = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
):
    query = select(Source).where(Source.is_active == is_active)
    if state_alignment:
        query = query.where(Source.state_alignment == state_alignment)
    query = query.order_by(Source.name_en)

    result = await db.execute(query)
    sources = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Source.id)).where(Source.is_active == is_active)
    )
    total = count_result.scalar() or 0

    return SourceListResponse(
        sources=[SourceResponse.model_validate(s) for s in sources],
        total=total,
    )


@router.get("/{slug}", response_model=SourceResponse)
async def get_source(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.slug == slug))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceResponse.model_validate(source)
