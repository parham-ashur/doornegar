import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks: seed sources if database is empty."""
    try:
        from app.services.seed import seed_sources
        async with async_session() as db:
            count = await seed_sources(db)
            if count > 0:
                logger.info(f"Seeded {count} news sources on startup")
    except Exception as e:
        logger.warning(f"Seed on startup skipped: {e}")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Iranian Media Transparency Platform — دورنگر",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
