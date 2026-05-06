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
                # Freshness/archival + cookie fingerprint (migration s4n5o6p7q8r9).
                # Self-heal applies these so a fresh deploy doesn't have
                # to wait on `alembic upgrade head` to render correctly.
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ",
                "CREATE INDEX IF NOT EXISTS idx_stories_archived_at ON stories(archived_at) WHERE archived_at IS NOT NULL",
                # #6 — summary_anchor (editorial reference for re-runs)
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS summary_anchor JSONB",
                "ALTER TABLE improvement_feedback ADD COLUMN IF NOT EXISTS submitter_cookie VARCHAR(64)",
                "CREATE INDEX IF NOT EXISTS idx_improvement_cookie_target ON improvement_feedback(target_id, submitter_cookie) WHERE submitter_cookie IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_story_events_type_created ON story_events(event_type, created_at DESC)",
                # Orphan-retirement counter — filters out articles that
                # repeatedly fail to cluster, so they don't keep paying
                # the LLM tax on every pipeline run.
                "ALTER TABLE articles ADD COLUMN IF NOT EXISTS cluster_attempts INTEGER NOT NULL DEFAULT 0",
                "CREATE INDEX IF NOT EXISTS idx_articles_unclustered_retry ON articles(ingested_at) WHERE story_id IS NULL AND cluster_attempts < 3",
                # Content-type filter (migration u6p7q8r9s0t1) — rss_category
                # captured at ingest, content_type set by classifier step,
                # Source.content_filters whitelists allowed labels per outlet.
                "ALTER TABLE articles ADD COLUMN IF NOT EXISTS rss_category TEXT",
                "ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_type VARCHAR(20)",
                "ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_type_confidence DOUBLE PRECISION",
                "CREATE INDEX IF NOT EXISTS idx_articles_content_type ON articles(content_type) WHERE content_type IS NOT NULL",
                "ALTER TABLE sources ADD COLUMN IF NOT EXISTS content_filters JSONB",
                "UPDATE sources SET content_filters = '{\"allowed\": [\"news\"]}'::jsonb WHERE content_filters IS NULL",
                "UPDATE articles SET content_type = 'news', content_type_confidence = 1.0 WHERE content_type IS NULL",
                # Maintenance lock — single-row table used by auto_maintenance.try_acquire_lock
                # to serialize runs (replaces the no-longer-deployed Redis lock).
                # Stale rows are reaped by the lock-acquire path itself.
                """CREATE TABLE IF NOT EXISTS maintenance_lock (
                    id BIGINT PRIMARY KEY,
                    label TEXT,
                    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""",
                # Live cross-process maintenance state. Single-row table
                # (id=1). Updated by the running maintenance process on
                # every begin_step / end_step transition (and throttled
                # update_step_progress). Read by the dashboard's
                # /admin/maintenance/status endpoint so progress is
                # visible even when maintenance runs in a separate
                # process or container from the API.
                """CREATE TABLE IF NOT EXISTS maintenance_run_status (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    state JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (id = 1)
                )""",
                # Seed the row so updates can use UPSERT cheaply.
                "INSERT INTO maintenance_run_status (id, state) VALUES (1, '{}'::jsonb) ON CONFLICT (id) DO NOTHING",
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

                # ── Critical missing indexes (Parham 2026-05-03 audit) ──
                # The data-integrity audit identified hot WHERE/ORDER BY
                # columns lacking indexes — sequential scans on stories
                # and articles tables. CREATE INDEX IF NOT EXISTS is
                # idempotent, fast on re-deploy after the first run.
                # Stories: trending API + clustering use these heavily.
                "CREATE INDEX IF NOT EXISTS idx_stories_trending_rank ON stories(priority DESC, trending_score DESC) WHERE archived_at IS NULL",
                "CREATE INDEX IF NOT EXISTS idx_stories_first_published ON stories(first_published_at DESC NULLS LAST)",
                "CREATE INDEX IF NOT EXISTS idx_stories_last_updated ON stories(last_updated_at DESC NULLS LAST)",
                "CREATE INDEX IF NOT EXISTS idx_stories_frozen_at_set ON stories(frozen_at) WHERE frozen_at IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_stories_blindspot ON stories(is_blindspot, archived_at) WHERE is_blindspot = TRUE",
                # Articles: NLP pipeline + dedup query these.
                "CREATE INDEX IF NOT EXISTS idx_articles_processed_null ON articles(ingested_at DESC) WHERE processed_at IS NULL",
                "CREATE INDEX IF NOT EXISTS idx_articles_embedding_null_recent ON articles(ingested_at DESC) WHERE embedding IS NULL",
                "CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_id) WHERE story_id IS NOT NULL",
                # Sources: content_filters JSONB queried on every NLP gate.
                "CREATE INDEX IF NOT EXISTS idx_sources_content_filters ON sources USING GIN (content_filters)",

                # ── server_default backfill (Parham 2026-05-03 audit) ──
                # The data-integrity audit found Python-side defaults
                # without server_default — out-of-band INSERTs (direct
                # SQL, webhook ingestion, manual seeds) get NULL instead
                # of the intended value, causing NoneType crashes
                # downstream. ALTER COLUMN SET DEFAULT is idempotent.
                "ALTER TABLE articles ALTER COLUMN cluster_attempts SET DEFAULT 0",
                "ALTER TABLE stories ALTER COLUMN view_count SET DEFAULT 0",
                "ALTER TABLE stories ALTER COLUMN article_count SET DEFAULT 0",
                "ALTER TABLE stories ALTER COLUMN source_count SET DEFAULT 0",
                "ALTER TABLE stories ALTER COLUMN priority SET DEFAULT 0",
                "ALTER TABLE stories ALTER COLUMN trending_score SET DEFAULT 0",
                # Backfill any historical NULLs so the new defaults take
                # effect retroactively for rows inserted before this DDL
                # ran. Bounded by current row count, fast.
                "UPDATE articles SET cluster_attempts = 0 WHERE cluster_attempts IS NULL",
                "UPDATE stories SET view_count = 0 WHERE view_count IS NULL",
                "UPDATE stories SET article_count = 0 WHERE article_count IS NULL",
                "UPDATE stories SET source_count = 0 WHERE source_count IS NULL",
                "UPDATE stories SET priority = 0 WHERE priority IS NULL",
                "UPDATE stories SET trending_score = 0 WHERE trending_score IS NULL",

                # ── Multi-locale (EN+FR) rollout — Phase 0 (2026-05-06) ──
                # Adds JSONB blobs for per-locale story + article translations,
                # plus the partial indexes used by step_translate_homepage_visible
                # to find untranslated homepage-eligible stories quickly.
                # Shape documented in project_en_fr_rollout.md. Auto-cleared
                # on FA edits via the Re-translate trigger map.
                "ALTER TABLE stories ADD COLUMN IF NOT EXISTS translations JSONB",
                "ALTER TABLE articles ADD COLUMN IF NOT EXISTS title_translations JSONB",
                "CREATE INDEX IF NOT EXISTS idx_stories_en_missing ON stories ((translations->'en'->>'title')) WHERE translations->'en'->>'title' IS NULL",
                "CREATE INDEX IF NOT EXISTS idx_stories_fr_missing ON stories ((translations->'fr'->>'title')) WHERE translations->'fr'->>'title' IS NULL",
                # Phase 0d — source-name glossary. name_fr populated in
                # Phase 1 from the canonical glossary in
                # project_en_fr_rollout.md. Voice prompts fall back to
                # name_en until then.
                "ALTER TABLE sources ADD COLUMN IF NOT EXISTS name_fr VARCHAR(255)",
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
