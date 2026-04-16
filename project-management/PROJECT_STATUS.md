# Doornegar - Project Status

**Last updated**: 2026-04-16 (Niloofar persona + performance 9.9s→3.0s + P1–P7 bug sweep)

## 2026-04-16 highlights

- **Custom domain live: `doornegar.org`** — Cloudflare free tier (CDN, DDoS, bot protection, SSL). Frontend via Cloudflare → Vercel. API via Cloudflare Worker at `api.doornegar.org` → Railway. Domain registered on Namecheap (~€6.50/year).
- **Homepage loads in ~3 seconds** (was ~10s). Parallelized SSR fetch waterfall, moved WeeklyDigest/WordsOfWeek to server-side props (0 client API calls post-hydration), `next/image` with AVIF/WebP + responsive srcset, batch `/stories/analyses?ids=` endpoint replaces ~30 round trips. ISR revalidate bumped to 30min/1hr — most users hit static CDN cache.
- **Niloofar persona fully operational.** Writing style guide (Ashouri-style analytical prose, not literary memoir). Claude-driven workflow: gather JSON → analyze in chat → apply findings file. No OpenAI in the loop. Data-oriented editing principle: don't rewrite for beauty, only fix specific problems.
- **P1–P7 bug fix sweep** completed: hero prefers balanced coverage, centroid validation for telegram analysis, source logo fallback for imageless stories, same-subject validation in number comparisons, subject-tagged key_claims, weekly brief bordered subsections, trending filter excludes stale/blindspot stories.
- **6 story merges** (Islamabad talks hub: 121 articles from 5 duplicate clusters; Strait blockade hub: 18 articles from 3 clusters).
- **Editorial neutrality**: «شهید» → «کشته» in Lebanon casualties title.
- **3 new sources/channels**: HRA-News (RSS, opposition), @ettelaatonline (conservative), @kayhan_online (conservative). 1 new analyst: @Naghal_bashi.
- **`update_image` fixed** — was a silent no-op since Story ORM has no image_url column. Override now stored in summary_en JSON blob.
- **`is_edited` guards** on step_story_quality and step_quality_postprocess prevent nightly pipeline from clobbering hand-edited content.
- **Active sources: 24** (was 23; added HRA-News).

## 2026-04-15 highlights

- **Story editor dashboard** live at `/fa/dashboard/edit-stories` — hand-edit titles, narratives, bias comparison for top trending stories. New `stories.is_edited` column protects edits from nightly regeneration. Alembic migration `e9f7a3d5c8b1`.
- **Maintenance pipeline** recovered from 3 silent bugs: `maintenance_logs.id` null, `telegram_link` NoneType crash, `merge_similar` FK violation. Cron telemetry now actually persists.
- **Telegram ingestion on Railway** — no longer laptop-dependent. `TELEGRAM_SESSION_STRING` env var (StringSession serialization). Verified: 363 new telegram posts fetched in 30 minutes by the Railway container.
- **4 sources deactivated** (is_active=false, preserving existing articles): fars-news, dw-persian, radio-zamaneh, isna. All lost public RSS or gated behind Cloudflare Access. Iran-hosted outlets (khabaronline, tasnimnews, mehrnews, mashreghnews, nournews, iribnews, etemadnewspaper) still geoblocked from Railway US IPs for RSS but work fine via Telegram API.
- **3 RSS URLs updated**: press-tv → `/rss.xml`, ilna → `/rss`, entekhab → `/fa/rss/allnews`.
- **Active sources: 27 → 23.**
- **`GET /stories/{id}` 500 fixed**: view_count bump moved to FastAPI BackgroundTask; was hitting `MissingGreenlet` on post-commit pydantic validation.
- **Suggest-source page** simplified — removed category grouping, just flat media + telegram lists.
- **Mobile stories carousel** (`/fa/stories-beta`) — full 13-step build complete as an exploration. Main `/fa` mobile reverted to the original `MobileHome()` list until Parham wants to cut over.

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

- Cloudflare CDN/WAF not yet in front of Railway backend — remaining ~3s load time is Railway API latency from Europe; Cloudflare would cache backend responses at edge
- UptimeRobot / monitoring not configured
- Custom domain not yet purchased
- OpenAI hard spending limit not yet set
- State media RSS feeds geo-blocked — relying on Telegram as workaround
- ~2,000 articles still have `localhost:8000` image URLs (dev-only leftovers). Fix: click "Null localhost image URLs" on dashboard then Run Maintenance
- Weekly Brief story links need backend change (niloofar_weekly.py → emit story IDs)
- Latin → Farsi digit consistency in some story titles
- Intelligence features (silence, coordination, narrative arc, delta) generate data but only show in StatsPanel on story detail page — no dedicated frontend views yet
- Reconnect GitHub → Vercel auto-deploy hook (currently manual `vercel deploy --prod --yes` after pushes)

### What was fixed this session (2026-04-16)

- ~~Homepage load 10s~~ → 3s (parallelized SSR, batch analyses, next/image, server-rendered WeeklyDigest/WordsOfWeek)
- ~~Image quality bugs~~ → next/image AVIF/WebP + manual override via summary_en blob + source logo fallback + Telegram CDN blacklist
- ~~Analyst database empty~~ → 17 analysts seeded (added @Naghal_bashi)
- ~~update_image silent no-op~~ → stores in summary_en JSON blob, read by _story_brief_with_extras
- ~~Nightly pipeline clobbers hand-edits~~ → is_edited guards on step_story_quality + step_quality_postprocess
- ~~Misleading cross-narrative comparisons~~ → same-subject validation in prompts
- ~~Stale/blindspot stories in trending~~ → score >0.5 + is_blindspot=false filters

## Data Metrics

From local development DB, April 10, 2026:

| Metric | Count |
|--------|-------|
| News sources | 24 active (28 total, 4 deactivated) |
| Articles ingested | ~1,300+ |
| Stories (visible, ≥2 sources) | 294 |
| Stories with AI summaries | 247 |
| Images stored in R2 | 765 |
| Telegram channels tracked | 18 (added @ettelaatonline, @kayhan_online) |
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

- **Frontend (production)**: `https://doornegar.org` (Cloudflare → Vercel; old URL `frontend-tau-six-36.vercel.app` still works)
- **Backend API (production)**: `https://doornegar-production.up.railway.app` (SSR fetches directly; `api.doornegar.org` available via Cloudflare Worker for external access)
- **Domain registrar**: Namecheap (`doornegar.org`, ~€6.50/year, auto-renew)
- **DNS/CDN/WAF**: Cloudflare free tier (nameservers: kai.ns.cloudflare.com, martha.ns.cloudflare.com)
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
