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
                # Guardrail columns — post-cluster pass flags stories crossing
                # size/age tiers; HITL can freeze (matcher + merge steps skip
                # frozen stories). split_from_id breadcrumbs split children.
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS frozen_at TIMESTAMPTZ",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS split_from_id UUID",
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS review_tier SMALLINT NOT NULL DEFAULT 0",
                "CREATE INDEX IF NOT EXISTS idx_stories_unfrozen ON stories(updated_at) WHERE frozen_at IS NULL",
                "CREATE INDEX IF NOT EXISTS idx_stories_review_tier ON stories(review_tier) WHERE review_tier > 0 AND frozen_at IS NULL",
                # Event log — HITL decisions + clustering decisions + field-level edits
                """CREATE TABLE IF NOT EXISTS story_events (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    story_id UUID,
                    article_id UUID,
                    event_type VARCHAR(40) NOT NULL,
                    actor VARCHAR(40) NOT NULL,
                    field VARCHAR(60),
                    old_value TEXT,
                    new_value TEXT,
                    confidence DOUBLE PRECISION,
                    signals JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""",
                "CREATE INDEX IF NOT EXISTS idx_story_events_story ON story_events(story_id, created_at DESC) WHERE story_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_story_events_type ON story_events(event_type, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_story_events_article ON story_events(article_id) WHERE article_id IS NOT NULL",
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
                # Feedback-loop columns: anonymous-vote dedup fingerprint
                # on improvement_feedback, applied-at flag on rater_feedback
                # so summary-correction regeneration is idempotent.
                "ALTER TABLE improvement_feedback ADD COLUMN IF NOT EXISTS submitter_fingerprint VARCHAR(64)",
                "CREATE INDEX IF NOT EXISTS idx_improvement_fp_target ON improvement_feedback(target_id, submitter_fingerprint) WHERE submitter_fingerprint IS NOT NULL",
                "ALTER TABLE rater_feedback ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ",
                # Negative-pair memory: which story an article was orphaned
                # from after a wrong_clustering vote, so the clusterer can
                # refuse to re-attach it. Source trust score scales the
                # cosine threshold per source — high-error sources need
                # stronger cosine evidence to attach.
                "ALTER TABLE improvement_feedback ADD COLUMN IF NOT EXISTS orphaned_from_story_id UUID",
                "CREATE INDEX IF NOT EXISTS idx_improvement_orphan_pair ON improvement_feedback(target_id, orphaned_from_story_id) WHERE orphaned_from_story_id IS NOT NULL",
                "ALTER TABLE sources ADD COLUMN IF NOT EXISTS cluster_quality_score DOUBLE PRECISION NOT NULL DEFAULT 1.0",
                # Orphan-retirement counter — filters out articles that
                # repeatedly fail to cluster, so they don't keep paying
                # the LLM tax on every pipeline run.
                "ALTER TABLE articles ADD COLUMN IF NOT EXISTS cluster_attempts INTEGER NOT NULL DEFAULT 0",
                "CREATE INDEX IF NOT EXISTS idx_articles_unclustered_retry ON articles(ingested_at) WHERE story_id IS NULL AND cluster_attempts < 3",
                # LLM usage / cost ledger — every OpenAI call logged here.
                """CREATE TABLE IF NOT EXISTS llm_usage_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    model VARCHAR(80) NOT NULL,
                    purpose VARCHAR(80) NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    cached_input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    input_cost DOUBLE PRECISION DEFAULT 0,
                    cached_cost DOUBLE PRECISION DEFAULT 0,
                    output_cost DOUBLE PRECISION DEFAULT 0,
                    total_cost DOUBLE PRECISION DEFAULT 0,
                    story_id UUID,
                    article_id UUID,
                    priced BOOLEAN DEFAULT TRUE,
                    meta JSONB
                )""",
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_ts ON llm_usage_logs(timestamp DESC)",
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage_logs(model)",
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_purpose ON llm_usage_logs(purpose)",
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_story ON llm_usage_logs(story_id)",
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_total ON llm_usage_logs(total_cost DESC)",
                # Worldview digests — one row per (bundle, week). Bundle is
                # the 4-subgroup taxonomy; the card describes what OUTLETS
                # in that bundle told their readers over the window. Read
                # by /api/v1/worldviews/*.
                """CREATE TABLE IF NOT EXISTS worldview_digests (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    bundle VARCHAR(24) NOT NULL,
                    window_start DATE NOT NULL,
                    window_end DATE NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'ok',
                    synthesis_fa JSONB,
                    evidence_fa JSONB,
                    article_count INTEGER NOT NULL DEFAULT 0,
                    source_count INTEGER NOT NULL DEFAULT 0,
                    coverage_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
                    model_used VARCHAR(80),
                    token_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
                    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_worldview_bundle_window UNIQUE (bundle, window_start)
                )""",
                "CREATE INDEX IF NOT EXISTS idx_worldview_window ON worldview_digests(window_start DESC, bundle)",
                "CREATE INDEX IF NOT EXISTS idx_worldview_bundle_recent ON worldview_digests(bundle, generated_at DESC)",
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
