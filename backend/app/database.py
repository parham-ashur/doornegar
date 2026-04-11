from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    pool_size=20,
    max_overflow=20,
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
