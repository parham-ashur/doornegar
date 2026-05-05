from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    # Pool sized for typical traffic: doornegar API gets ISR fetches
    # from Vercel every ~5 min plus occasional visitor traffic; cron
    # services run sequential batched queries. Both rarely need more
    # than 2-3 connections concurrently. Prior 20/20 reserved 200-400 MB
    # of asyncpg buffers per service for capacity that was never used
    # — significant on Railway's $0.000231/GB/min memory pricing
    # (Parham 2026-05-05 cost-trim pass). 5 persistent + 10 overflow
    # leaves plenty of headroom for ISR concurrency spikes while
    # cutting baseline RAM ~100-150 MB per service.
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    # Neon closes idle connections after ~5 minutes. Recycle at 4 minutes
    # so pool_pre_ping never sees a stale connection at checkout time.
    # Note: pool_recycle only triggers at checkout, not mid-session.
    # For long-running sessions (e.g. clustering), see _keepalive() in
    # app/services/clustering.py which pings before each LLM call.
    pool_recycle=240,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
