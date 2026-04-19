import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, text, update

from app.api.v1.router import api_router
from app.config import settings
from app.database import async_session
from app.models.source import Source
from app.rate_limit import limiter, get_client_ip

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
            # Self-healing schema: columns declared on models that are
            # created lazily by maintenance steps. If the step hasn't run
            # on a fresh deploy, every Story SELECT fails. Idempotent.
            for ddl in (
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS editorial_context_fa JSONB",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS analysis_snapshot_24h JSONB",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS hourly_update_signal JSONB",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS audit_notes JSONB",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS arc_id UUID",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS arc_order INTEGER",
                """CREATE TABLE IF NOT EXISTS story_arcs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    title_fa TEXT NOT NULL,
                    title_en TEXT,
                    slug VARCHAR(200) NOT NULL UNIQUE,
                    description_fa TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""",
                "CREATE INDEX IF NOT EXISTS idx_stories_arc_id ON stories(arc_id)",
            ):
                try:
                    await db.execute(text(ddl))
                except Exception as e:
                    logger.warning(f"Schema self-heal skipped: {ddl} — {e}")
            await db.commit()

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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ─── Request size limit (prevent memory exhaustion) ──────────
MAX_REQUEST_SIZE = 1 * 1024 * 1024  # 1 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Serve locally saved images
_static_dir = Path(__file__).parent.parent / "static" / "images"
_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(_static_dir)), name="images")


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
