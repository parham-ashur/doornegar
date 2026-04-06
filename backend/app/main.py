import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, update

from app.api.v1.router import api_router
from app.config import settings
from app.database import async_session
from app.models.source import Source

logger = logging.getLogger(__name__)

# Correct RSS URLs — fixes discovered during first deployment
RSS_FIXES = {
    "iran-international": ["https://www.iranintl.com/fa/feed"],
    "dw-persian": ["https://rss.dw.com/xml/rss-fa-all"],
    "radio-zamaneh": ["https://www.radiozamaneh.com/feed/"],
    "press-tv": ["https://www.presstv.ir/RSS"],
    "tasnim": ["https://www.tasnimnews.com/fa/rss/most-visited/"],
    "fars-news": ["https://www.farsnews.ir/rss"],
    "mehr-news": ["https://www.mehrnews.com/rss"],
    "isna": ["https://www.isna.ir/rss"],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks: seed sources and fix RSS URLs."""
    try:
        from app.services.seed import seed_sources
        async with async_session() as db:
            count = await seed_sources(db)
            if count > 0:
                logger.info(f"Seeded {count} news sources on startup")

            # Fix RSS URLs for existing sources
            for slug, urls in RSS_FIXES.items():
                await db.execute(
                    update(Source)
                    .where(Source.slug == slug)
                    .values(rss_urls=urls)
                )
            await db.commit()
            logger.info("RSS URLs updated")
    except Exception as e:
        logger.warning(f"Startup tasks error: {e}")
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
