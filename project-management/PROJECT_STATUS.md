# Doornegar - Project Status

**Last updated**: 2026-04-13 (post intelligence layer + cost optimization mega-session)

## What is Doornegar?

Doornegar (دورنگر) is a free, bilingual (Persian/English) media transparency platform for Iranian news. Think of it like Ground News, but specifically designed for the Iranian media landscape. It:

- Aggregates articles from 28 Iranian news outlets (state, diaspora, independent)
- Groups related articles into "stories" so you can see how different outlets cover the same event
- Uses AI to score each article for political bias, framing, and tone
- Tracks 16 Telegram channels (including state media that geo-block RSS)
- Scores each source on 8 media dimensions (editorial independence, factional capture, etc.)
- Shows "blind spots" — stories that only one type of outlet is covering
- Has a "lab" feature for topic-based analysis with news and debate modes

## Current State

### What works

- RSS feed ingestion from 28 news sources
- Telegram ingestion from 16 channels (covers state media that geo-block RSS)
- NLP pipeline (text normalization, embedding generation, keyword extraction)
- **Story clustering via LLM** with **two-phase matching**: embedding cosine pre-filter (threshold 0.30) → LLM confirmation. Article-content-aware (6000 chars for premium, 400 for baseline), size ceiling (30), time window (7 days), strict rejection-first prompt, double-match guard, model: `gpt-5-mini`
- **Story centroid embeddings**: each story stores a centroid (mean of article embeddings, L2-normalized) in JSONB; recomputed after clustering via `step_recompute_centroids`
- **3-tier LLM strategy**:
  - Premium (`gpt-5-mini`): story analysis + **deep analyst factors** for top-16 trending (homepage)
  - Baseline (`gpt-4o-mini`): bias scoring + long-tail story analysis
  - Economy (`gpt-4.1-nano`): headline translation
  - Full per-task overrides via env vars
- **LLM-powered bias scoring** (new ~2200-token rich prompt with Persian media glossary, 3 few-shot examples, prompt-cache-eligible)
- AI-generated per-perspective summaries (state vs diaspora vs independent) with refined narrator rules and length ceilings
- 8-dimension media scoring system per source
- **Cloudflare R2 image storage** + title-overlap image picker computed at response time in `_story_brief_with_extras()` (not stored on Story model); `image_checked_at` column for 24h skip optimization
- **Auto-maintenance** runs daily via Railway cron; fire-and-forget endpoint with per-step live progress tracking via shared `maintenance_state` module
- Bilingual Next.js frontend with RTL support, Jalali dates
- **Homepage redesign (BBC-style)**: featured story prominence, weekly briefing (خلاصه هفتگی), most disputed (بیشترین اختلاف), battle of numbers (نبرد اعداد), narrative map (نقشه روایت‌ها), words of the week (واژه‌های هفته)
- **Story detail page redesign**: tabbed analysis interface, political spectrum visualization, stats panel
- **Updated Persian labels**: محافظه‌کار (was حکومتی), اپوزیسیون (was برون‌مرزی), نگاه یک‌طرفه (was نقاط کور)
- **Quality audit system**: daily 5-check cycle with Neon optimization
- **Auto-merge similar stories** and **title auto-update from LLM**
- **Trending diversity reranking** with exponential decay
- **Source logos** for all 18 outlets + **source neutrality scoring**
- **Telegram embed image fallback**
- **PATCH admin endpoints** for stories, articles, and sources
- Lab feature (topic-based analysis, news/debate modes, analyst perspectives)
- Error/loading/404 pages with themed SVG animations
- Admin token auth on all mutation endpoints
- Rate limiting (slowapi): 200/min default, 10/hour on LLM endpoints
- Request size limits (1 MB), security headers, CORS restrictions
- Rater feedback system (`/fa/rate`, `/fa/suggest`, `/fa/dashboard/improvements`) with undo, history, onboarding, dedup hint
- **Deep analyst factors** on premium-tier stories: 15 analytical categories (risk, outcomes, stakeholders, hidden info, propaganda watch, etc.) stored in `summary_en` extras JSON, exposed via `StoryAnalysisResponse.analyst`
- **OpenAI embeddings** (`text-embedding-3-small`, 384-dim) — replaced sentence-transformers/TF-IDF, no PyTorch needed (~2GB saved), ~$0.05/month
- **Neon keepalive**: `_keepalive(db)` pings before each LLM call; `pool_recycle` lowered to 240s
- **LLM retry with backoff**: `llm_failed_at` column on Article + Story, 24h retry window
- **Admin dashboard** at `/fa/dashboard` (LTR) with live maintenance progress modal, diagnostics panel, recently re-summarized stories browser, force-resummarize buttons (test 5 / refresh 16), data repair section (null localhost images / unclaim story articles), re-embed-all button, priority vote + merge suggestion buttons, device context badges, pipeline controls, and PATCH editing for stories/articles/sources
- **Two-pass analysis**: Pass 1 uses `gpt-4.1-nano` for structured fact extraction (~$0.001/story), Pass 2 uses premium model for deep framing analysis with pre-extracted facts as input
- **Cross-story memory**: related stories (centroid cosine > 0.5) injected as context during analysis — prevents analytical amnesia across connected narratives
- **Source track records**: historical reliability patterns per source injected into LLM analysis prompts
- **Intelligence features** (5):
  - **Silence detection** (`step_detect_silences`): finds one-sided coverage (3+ articles from one side, 0 from other); LLM-generated hypotheses for top 5
  - **Coordinated messaging** (`step_detect_coordination`): flags 3+ articles from different sources in same group with cosine > 0.85 within 6h
  - **Narrative arc tracking**: story evolution tracked in `narrative_arc` field
  - **What-changed delta**: captures only new information since last analysis (avoids repetition)
  - **Prediction verification** (`step_verify_predictions`): checks past analyst predictions against current events
- **Cost optimizations**: 3-layer dedup (title + URL + embedding cosine > 0.92), priority scoring (top 15 only per run), smart article selection (one per source, balanced alignments), visible-only bias scoring (100/run cap), summary throttle
- **Quality post-processing** (`step_quality_postprocess`): final LLM review of top 15 stories after all other pipeline steps
- **Analyst model** + **AnalystTake model**: track Iranian political commentators and extract structured insights (predictions, reasoning, insider signals, fact checks) from their Telegram posts
- **Aggregator link extraction**: `extract_articles_from_aggregators()` pulls URLs from aggregator Telegram channels
- **New API endpoints**: `GET /insights/loaded-words` (aggregate loaded vocabulary), `GET /stories/{id}/article-positions` (PCA 2D coordinates), `POST /admin/create-tables`, `POST /admin/cleanup-unrelated`
- **NarrativeMap** component: PCA scatter plot showing article positions colored by alignment — API-driven from `/article-positions`
- **WordsOfWeek** component: now fetches from `/insights/loaded-words` API (was hardcoded); fallback to static data if API unavailable
- **Battle of Numbers**: now uses dynamic data from story analysis
- **Pipeline expanded to 31 steps** (was ~26): added silence detection, coordinated messaging, analyst take extraction, prediction verification, quality post-processing, 3-layer dedup

### What needs work

- Cloudflare CDN/WAF not yet in front of Railway backend (biggest security win remaining)
- UptimeRobot / monitoring not configured
- Custom domain not yet purchased
- OpenAI hard spending limit not yet set
- Image quality threshold might need tuning (currently 120×80)
- State media RSS feeds geo-blocked — relying on Telegram as workaround
- Existing oversized clusters (pre-size-ceiling) may still exist — need manual cleanup via "Unclaim story articles" dashboard button when spotted
- ~2,000 articles still have `localhost:8000` image URLs (dev-only leftovers). Fix: click "Null localhost image URLs" on dashboard then Run Maintenance a few times to let `step_fix_images` re-fetch from source URLs
- Bias scoring catching up — priority scoring now focuses on visible stories (100/run cap)
- Analyst database not yet seeded — need to add Iranian political commentators for AnalystTake extraction
- Intelligence features (silence, coordination, narrative arc, delta) generate data but no frontend display yet
- Prediction verification needs analyst takes seeded first to have data to verify

## Data Metrics

From local development DB, April 10, 2026:

| Metric | Count |
|--------|-------|
| News sources | 28 |
| Articles ingested | ~1,300+ |
| Stories (visible, ≥2 sources) | 294 |
| Stories with AI summaries | 247 |
| Images stored in R2 | 765 |
| Telegram channels tracked | 16 |
| Media dimension scores | 28 sources × 8 dimensions |

## Infrastructure

| Service | Provider | Purpose | Status |
|---------|----------|---------|--------|
| Backend API | Railway | FastAPI server | Deployed (502 as of 2026-04-10 — needs env vars + restart) |
| PostgreSQL | Neon | Primary database with pgvector | Connected |
| Redis | Upstash | Celery task queue | Connected |
| Frontend | Vercel | Next.js web app | Deployed |
| Image storage | **Cloudflare R2** | S3-compatible object storage for article images | **Live — 765 images uploaded** |
| LLM bias scoring | OpenAI (gpt-4o-mini) | Article bias analysis | Working (baseline tier) |
| LLM story analysis (top-16) | OpenAI (gpt-5-mini) | Homepage story summaries + analyst factors | Working (premium tier) |
| Embeddings | OpenAI (text-embedding-3-small) | Article + story centroid embeddings | Working (~$0.05/month) |
| LLM story analysis (long-tail) | OpenAI (gpt-4o-mini) | Non-trending story summaries | Working (baseline tier) |
| LLM title translation | OpenAI (gpt-4.1-nano) | English headline → Persian | Working (economy tier) |
| LLM fact extraction | OpenAI (gpt-4.1-nano) | Pass 1: structured fact extraction | Working (economy tier, ~$0.001/story) |
| LLM clustering | OpenAI (gpt-5-mini) | Match articles to stories | Working (reasoning task, content-aware) |
| LLM intelligence | OpenAI (gpt-4.1-nano) | Silence hypotheses, coordination detection | Working (economy tier) |
| Maintenance scheduler | Railway Cron | Daily `auto_maintenance.py` | Running |
| Telegram API | Telethon | 16 channels monitored | Configured |

### URLs

- **Frontend (production)**: `https://frontend-tau-six-36.vercel.app`
- **Backend API (production)**: `https://doornegar-production.up.railway.app`
- **R2 public URL**: `https://pub-65f981ecf095486aaea3482ec613d9b1.r2.dev`
- **Local frontend**: http://localhost:3000
- **Local backend**: http://localhost:8000
- **API docs**: http://localhost:8000/docs

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg, slowapi, aioboto3
- **Database**: PostgreSQL 16 with pgvector extension
- **Cache/Queue**: Redis 7
- **Frontend**: Next.js 14, React 18, Tailwind CSS, next-intl
- **Embeddings**: OpenAI `text-embedding-3-small` (384-dim, ~$0.05/month)
- **AI**: OpenAI 3-tier (gpt-5-mini / gpt-4o-mini / gpt-4.1-nano); Anthropic available as fallback but not actively used
- **Object storage**: Cloudflare R2 (S3-compatible)
- **Dates**: date-fns-jalali

## Security Posture

| Layer | Protection |
|-------|-----------|
| Secrets | `.env` gitignored, all credentials via env vars |
| Admin endpoints | Token-based auth (`ADMIN_TOKEN`) |
| LLM cost abuse | Admin-only + 10/hour rate limit + `max_tokens=4096` per call |
| Request flood | slowapi: 200/min, 2000/hour default (per IP via CF-Connecting-IP) |
| Memory exhaustion | 1 MB max request body |
| CORS | Restricted to specific frontend origins |
| Headers | X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| DDoS (edge) | **Not yet — needs Cloudflare proxy in front of Railway** |
| Bot protection | **Not yet — needs Cloudflare Bot Fight Mode** |
| WAF | **Not yet — needs Cloudflare managed ruleset** |
| Uptime monitoring | **Not yet — needs UptimeRobot** |
| OpenAI hard cap | **Not yet — needs to be set in OpenAI dashboard** |

## Project Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Backend: models, ingestion, NLP pipeline | Done |
| Phase 2 | Backend: clustering, bias scoring, Telegram | Done |
| Phase 3 | Frontend: Next.js bilingual UI | Done |
| Phase 4 | Private rating system (invite-only) | Code deployed, no raters yet |
| Phase 5 | R2 image storage + security hardening | **Done (2026-04-10)** |
| Phase 5.5 | Intelligence layer: two-pass analysis, silence/coordination detection, analyst tracking, cost optimization | **Done (2026-04-13)** |
| Phase 6 | Cloudflare CDN/WAF + UptimeRobot + OpenAI caps | **Next** |
| Phase 7 | OVHcloud VPS migration | Not started |
