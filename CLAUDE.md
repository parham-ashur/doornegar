# Doornegar (دورنگر) — Iranian Media Transparency Platform

## Project Overview

Doornegar is a free, bilingual (Persian/English) media transparency platform for Iranian news — similar to Ground News but tailored for the Iranian media landscape. It aggregates articles from ~12 outlets (state, diaspora, independent), groups them by story, and reveals bias, framing differences, blind spots, and social media reactions using AI-assisted analysis and community validation.

**Owner**: Parham (non-developer, relies on Claude for all technical implementation)
**Stack**: Python 3.12 / FastAPI / SQLAlchemy 2 / Celery+Redis / PostgreSQL (Neon) / Next.js 14 / Tailwind CSS

Embeddings are stored as JSONB arrays, NOT pgvector. The pgvector extension is not installed on Neon for this project. See `reference_embedding_storage.md`.

## Directory Structure

```
doornegar/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/             # REST API endpoints
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic (ingestion, clustering, bias scoring, social)
│   │   ├── nlp/                # Persian NLP, embeddings, text processing
│   │   ├── workers/            # Celery async tasks
│   │   └── utils/              # Persian text utils, date conversion
│   ├── alembic/                # Database migrations
│   ├── tests/                  # pytest test suite
│   └── manage.py               # CLI management commands
├── frontend/                   # Next.js bilingual frontend (Phase 3)
└── docker-compose.yml          # PostgreSQL, Redis, backend, workers
```

## Key Conventions

- **Async everywhere**: All DB operations use async SQLAlchemy + asyncpg
- **Persian text**: Always normalize with `app.nlp.persian.normalize()` before storage
- **Bilingual fields**: Models use `title_fa` / `title_en`, `description_fa` / `description_en`
- **UUID primary keys**: All models use UUID, not auto-increment integers
- **JSONB for lists**: Keywords, framing labels, entities stored as PostgreSQL JSONB
- **Embeddings**: 384-dim vectors from OpenAI `text-embedding-3-small` (with explicit dimension reduction from 1536 → 384), stored as JSONB. The `embedding_model` config setting points to a sentence-transformers name but it's vestigial — `app/nlp/embeddings.py` hardcodes the OpenAI call.
- **Iranian media axes**: state_alignment (state/semi_state/independent/diaspora), irgc_affiliated, factional_alignment, production_location

## Running the Project

```bash
# Start infrastructure
cd doornegar && docker compose up -d db redis

# Install backend
cd backend && pip install -e ".[dev,nlp,llm]"

# Setup database
alembic revision --autogenerate -m "initial"
alembic upgrade head

# Seed sources
python manage.py seed

# Run the API
uvicorn app.main:app --reload

# Run the full pipeline (ingest → NLP → cluster → score)
python manage.py pipeline

# Or run individual steps
python manage.py ingest
python manage.py process
python manage.py cluster
python manage.py score
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /health | Health check |
| GET | /api/v1/sources | List all news sources |
| GET | /api/v1/sources/{slug} | Source detail |
| GET | /api/v1/articles | List articles (paginated) |
| GET | /api/v1/stories | List stories (paginated) |
| GET | /api/v1/stories/trending | Top trending stories |
| GET | /api/v1/stories/blindspots | Stories with one-sided coverage |
| GET | /api/v1/stories/{id} | Story detail with articles + bias |
| POST | /api/v1/admin/pipeline/run-all | Run full pipeline manually |
| POST | /api/v1/admin/ingest/trigger | Trigger RSS ingestion |
| POST | /api/v1/admin/nlp/trigger | Trigger NLP processing |
| POST | /api/v1/admin/cluster/trigger | Trigger story clustering |
| POST | /api/v1/admin/bias/trigger | Trigger bias scoring |
| GET | /api/v1/social/channels | List tracked Telegram channels |
| POST | /api/v1/social/channels | Add a Telegram channel to track |
| GET | /api/v1/social/stories/{id}/social | Telegram posts linked to a story |
| GET | /api/v1/social/stories/{id}/sentiment/history | Sentiment over time for a story |

## Data Pipeline Flow

```
RSS Feeds → Ingest → NLP (normalize, embed, translate) → Cluster into Stories → LLM Bias Score
                                                                    ↑
                                                    Telegram channels → Social posts linked to stories
```

## LLM Usage

- **Bias scoring**: Claude Haiku or GPT-4o-mini analyzes each article for political alignment, framing, tone, factuality
- **Prompt**: Located in `app/services/bias_scoring.py` — BIAS_ANALYSIS_PROMPT
- **Cost**: ~$75-100/month for 100 articles/day
- Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`

## Important Notes for Claude

- Parham is NOT a developer — provide simple instructions, explain what things do
- **Migrations**: commit alembic files to git BEFORE running `alembic upgrade head` against production. Workflow: edit model → `alembic revision --autogenerate` → review → `git add` + `git commit` → push → THEN `alembic upgrade head`. Production also self-heals via DDL in `app/main.py` lifespan, so most schema additions are idempotent on deploy.
- Test RSS feeds before adding: some Iranian state sites geo-block or go offline
- Persian text MUST be normalized before any comparison or storage
- The project uses UTC timestamps; Jalali conversion is frontend/display only

### Pipeline + cron (canonical, do not paraphrase as "daily")

- **Only `FULL_PIPELINE` runs on a cron schedule**: `0 3,9,15 * * *` UTC (3× daily, 6h apart). Configured on Railway service `maintenance-cron`.
- **`HOURLY_PIPELINE` was removed 2026-05-03**. `mode="hourly"` falls back to `INGEST_ONLY_PIPELINE` for safety. Any cron service still firing `mode=hourly` is leftover and must be disabled in the Railway dashboard. Detection: lock-holder names starting `hourly@` in `/admin/maintenance/force-release-lock` responses.
- **`INGEST_ONLY_PIPELINE`** (12 steps) is for the dashboard "Run Now" path only — does NOT run on a cron.
- Every push to `main` triggers Railway redeploy → SIGTERM-kills any in-progress maintenance run. **Never push during a maintenance run**; check `/admin/maintenance/status` first.

### Single-source-of-truth rules

- **Homepage scope**: every per-story LLM step calls `app.services.homepage_scope.homepage_story_ids(db)` BEFORE making LLM calls. Never inline a `homepage_eligible` predicate. The module mirrors trending + blindspot API filters exactly; drift is what caused April-May 2026 cost overruns.
- **Frozen stays on the homepage**: `Story.frozen_at IS NULL` must NOT appear in `/api/v1/stories/trending` or `/api/v1/stories/blindspots` filter clauses. Freeze means "no new articles can join this cluster" — NOT "this story leaves the homepage." Tests in `tests/test_war_audit_fixes.py::TestFrozenStaysOnHomepage` block silent reverts.
- **No silent fallbacks for external APIs**: embedding / LLM / scraping wrappers must return None on failure, never zero vectors / empty arrays / placeholder values. See `feedback_no_silent_fallbacks.md`.
- **Sentinel-column trap**: any "did we already do this?" gate based on a sentinel column (`processed_at`, `analyzed_at`, etc.) MUST also check whether the work succeeded. Retry path: `(sentinel IS NULL) OR (sentinel IS NOT NULL AND output IS NULL AND ingested_at >= NOW() - 14d)`. See `feedback_processed_at_trap.md`.
- **Budget kill-switch (Parham 2026-05-07)**: the cron halts all LLM/egress-heavy steps when month-to-date LLM spend reaches 80% of the $30/mo cap (= $24). Website goes stale before project runs out of budget. Implemented in `app/services/budget_guard.py`; called from `run_maintenance` pre-flight. Operator override via `POST /admin/budget/override?action=lock|clear|reset`. Status: `GET /admin/budget/status`. **NEVER bypass this rule by inlining a force-run** — even for emergency editorial work. Use the `?action=clear` one-shot endpoint, which auto-reverts after one cron pass. See `feedback_budget_kill_switch.md`.
- **3 GB/day Neon egress cap (Parham 2026-05-09)**: hard rule. Neon's free tier allows 100 GB/month outbound; 100 / 30 = 3.33 GB/day; cap at **3.0 GB/day** to leave 10% headroom. When today's egress (estimated from `pg_stat_database.tup_returned` delta against the start-of-day snapshot in `egress_daily_snapshot`) crosses the cap, `should_halt_for_budget` returns `daily_egress_cap_*` and `run_maintenance` halts the **entire pipeline** (same semantics as `manual_lock` — NOT just LLM steps). Resets at UTC midnight via natural day-rollover. Triggered by the 2026-05-09 incident where `HALT_SKIP_STEPS` only blocked LLM-heavy steps and ~41 non-LLM heavy steps (cluster, recompute_centroids, ingest, audit_clusters, etc.) still ran on every cron fire under `manual_lock`, burning ~10 GB/fire × 3 fires/day = 30 GB. Lives in `DAILY_EGRESS_CAP_GB` and `get_daily_egress_estimate()` in `budget_guard.py`. Tripwire `TestDailyEgressCap3GB` blocks any cycle that weakens the constant or removes the early-exit. **Never raise the cap above 3.0 without an explicit acknowledgement from Parham.**
- **manual_lock means stop everything (Parham 2026-05-09)**: when the operator sets `manual_lock`, `run_maintenance` early-exits before the pipeline for-loop. Distinct from auto-halt (`combined_mtd >= 80% of $30`), which keeps the partial behavior of running CHEAP_STEPS so ingest stays fresh. The 2026-05-09 incident was caused by treating these two halt modes the same. See `auto_maintenance.py:7660+` (Phase E.2 anchor).
- **7-day data window (Parham 2026-05-09)**: clustering, recompute_centroids, telegram-link, telegram-sentiment, recluster_orphans all operate on articles + posts ≤ 7 days old. Older content stays in the DB for archive / SEO / permalink rendering but is **invisible to the pipeline**. Specific cutoffs that must remain ≤ 7 days: `clustering.py` cluster_articles `cutoff`, `clustering.py` `AGE_CAP_DAYS` constant in `_match_to_existing_stories`, `auto_maintenance.step_recompute_centroids` article filter, `telegram_analysis.link_posts_by_embedding` story_recency_cutoff + article_recency_cutoff + post_recency_cutoff. The 7-day freeze rule (`step_archive_stale`) closes any story whose `first_published_at` falls outside the window. Together these mean: a story that's 7 days old is closed; a fresh article only joins existing-but-still-fresh clusters; nothing absorbs anything beyond a one-week window. **Tripwire `TestSevenDayDataWindow` blocks regressions.** Triggered by the 2026-05-09 umbrella incident: two stories had absorbed 1464 + 2354 articles over 60-70 days because the cluster window was 30d while the freeze window was 7d.
- **Defer heavy JSONB on `selectinload(Story.articles)`**: `articles.embedding`, `articles.keywords`, `articles.named_entities`, and `articles.content_text` (when not in the access path) MUST be deferred. Each loaded row was costing ~30 KB; 200 stories × 50 articles = 300 MB per cron query. Add `defer(Article.embedding), defer(Article.keywords), defer(Article.named_entities), defer(Article.content_text)` to every selectinload that doesn't read those columns. May 2026 Neon $18 egress was caused by missing defers.

### Tests

- Run: `cd backend && pytest tests/ -q` (full suite, ~1s, 107 tests as of 2026-05-03).
- Critical regression suite is `backend/tests/test_war_audit_fixes.py` — 22 tests mapping 1:1 to the war-mode fixes. Each tripwires a specific bug class; if you add a new spend-gate or drift-fix, add a test here.

### Monitoring

- `/admin/health/overview` — single-stop "is anything broken?" with 20+ canaries. Cached 60s.
- 3 cloud routines on claude.ai/code/routines auto-recover ghost locks + report regressions + send morning briefing.
- `force-release-lock` endpoint clears both `maintenance_lock` AND `maintenance_run_status` so the dashboard reflects reality.

## Mobile Stories Experience

### Goal
Mobile-first stories interface (Instagram Stories / TikTok style) for the existing platform. 4 layout types in a 6-slot looping horizontal carousel. Bilingual: Farsi (RTL) + English (LTR).

### Pre-Build Audit
Before writing ANY code, audit the existing project:
1. List framework, router, folder structure
2. Identify CSS/styling approach
3. Find existing component patterns and naming conventions
4. Find existing TypeScript types for stories, telegram data, sources
5. Check if Farsi fonts (Vazirmatn, IRANSans, Shabnam) are loaded
6. Check for existing RTL/LTR handling
7. Check for swipe/gesture libraries in package.json
Adapt ALL new code to match existing conventions.

### Build Order
Sequential. Each step testable before moving on.
 1. Carousel shell         → 6 empty slots, swipe, loop. TEST: swipe all 6, wraps.
 2. StoryBackground        → video autoplay + image fallback. TEST: both paths.
 3. StoryLayout State A    → fixed bg + hero title. TEST: renders mock story.
 4. StickyTitle transition  → scroll-driven A→B. TEST: title shrinks on scroll.
 5. Content panel          → sections beneath sticky title. TEST: full page scrolls.
 6. SplitScreen base       → reusable two-half component. TEST: mock data renders.
 7. BlindspotLayout        → SplitScreen + two stories. TEST: both halves correct.
 8. MaxDisagreementLayout  → SplitScreen + one story + "در مقابل". TEST: renders.
 9. TelegramLayout         → dark bg, two sections, badges. TEST: predictions + claims.
10. StoryDetail + drilldown → tap from 2/3/4 → State B, swipe nav. TEST: full flow.
11. RTL/LTR pass           → all layouts both directions. Fix issues.
12. OnboardingHints        → overlay, localStorage. TEST: shows once, gone forever.
13. Polish                 → transitions, blur, video loading, typography, viewports.

### iOS Safari Gotchas
- Video: `playsinline` REQUIRED for autoplay. Without it → fullscreen player.
- Video: iOS reclaims memory off-screen. Consider clearing `src` when not visible.
- `position: fixed`: may need `will-change: transform` or separate fixed div.
- `backdrop-filter`: needs `-webkit-backdrop-filter` prefix.
- `100vh` wrong on iOS. Use `100dvh`.
- `animation-timeline: scroll()`: limited support. Fallback to JS + rAF.
