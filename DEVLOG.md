# Doornegar Development Log

## 2026-04-12 — Pipeline audit + analyst factors + embedding pre-filter session

### Key outcomes

1. **Maintenance pipeline audit — 8 fixes**: keepalive pings (Neon timeout), `llm_failed_at` retry column, batched metadata refresh (N*4 → 3 queries), memory-safe summarize (10 articles/story), `image_checked_at` 24h skip, NULL title dedup guard, translation model from settings, double-match guard in clustering.
2. **Story.image_url bug fix**: Story model has no `image_url` column. Moved title-overlap picker to `_story_brief_with_extras()` (response-time). Removed from `_EditStoryRequest`.
3. **Deep analyst factors (15 categories)**: `ANALYST_FACTORS_ADDENDUM` prompt for premium-tier (top-16) stories. Factors: risk assessment, potential outcomes, key stakeholders, missing information, credibility signals, timeline, framing gap, what is hidden, historical parallel, economic impact, international implications, factional dynamics, human rights dimension, public sentiment, propaganda watch. Stored in `summary_en` extras JSON under `"analyst"` key, tagged "doornegar-ai".
4. **Premium tier 30 → 16**: only 16 stories visible on homepage, no need to pay premium rates for stories 17-30.
5. **OpenAI embeddings**: switched from sentence-transformers/TF-IDF to `text-embedding-3-small` (384-dim, ~$0.05/month, no PyTorch ~2GB saved).
6. **Two-phase clustering**: embedding cosine pre-filter (threshold 0.30) before LLM confirmation. `Story.centroid_embedding` column (JSONB), `_compute_centroid()`, `step_recompute_centroids`. `POST /admin/re-embed-all` endpoint.
7. **Neon keepalive fix**: `_keepalive(db)` does `SELECT 1` before each LLM call; `pool_recycle` lowered 3600 → 240.
8. **Homepage enhancements**: story dates (first_published + updated_at), priority up/down vote buttons, merge suggestion button, `StoryActions` component, feedback overlay repositioned left.
9. **New issue types**: `priority_higher`, `priority_lower`, `merge_stories` in backend + frontend.
10. **Device context on feedback**: `device_info` field auto-captured, mobile badge on dashboard.
11. **Framing + article dates**: max 3 framing labels per side, publish dates in LLM prompt, 6000-char content for premium.
12. **Last Maintenance card**: derives from DB (`max Article.ingested_at`) to survive Railway deploys.

### Key decisions (see DECISION_LOG for details)
- D019: OpenAI embeddings replacing sentence-transformers
- D020: Two-phase clustering with embedding pre-filter
- D021: Deep analyst factors for premium-tier stories
- D022: Premium tier reduced from 30 to 16
- D023: Neon keepalive pings during long LLM operations
- D024: Story.image_url computed at response time, not stored
- D025: Device context on improvement feedback

### Lessons learned
- **Neon closes idle connections after ~300s.** Long sequential LLM call chains (clustering = 340s) will crash the next DB query. Keepalive pings fix this.
- **Story model had no `image_url` column.** The step_fix_images code was writing to a nonexistent attribute. Always check the model before assuming a column exists.
- **Premium tier was wasteful at 30.** Only 16 stories show on the homepage. Paying premium for invisible stories is waste.
- **Embedding pre-filter threshold must be loose (0.30).** Cross-language cosine similarity is low even for genuinely related content. The LLM makes the final call.
- **Batching metadata refresh matters.** N stories * 4 queries each was O(N*4) round trips. 3 aggregate queries covers all stories.

### Migrations
- `b5e9f3a1c2d8`: `llm_failed_at` on Article + Story, `image_checked_at` on Article
- `c7d4e2f8a1b3`: `device_info` on ImprovementFeedback
- `d8e5f1a2b3c4`: `centroid_embedding` (JSONB) on Story

### Files changed (summary)
```
backend/app/models/article.py              # llm_failed_at, image_checked_at columns
backend/app/models/story.py                # llm_failed_at, centroid_embedding columns
backend/app/models/feedback.py             # device_info column
backend/app/database.py                    # pool_recycle 3600 → 240
backend/app/config.py                      # premium_story_top_n 30 → 16
backend/app/services/clustering.py         # embedding pre-filter, keepalive, double-match guard, batched refresh
backend/app/services/story_analysis.py     # analyst factors, include_analyst_factors param, framing cap, article dates
backend/app/services/bias_scoring.py       # keepalive pings
backend/app/services/nlp_pipeline.py       # OpenAI text-embedding-3-small
backend/app/api/v1/admin.py                # re-embed-all endpoint
backend/app/api/v1/stories.py              # image_url from _story_brief_with_extras
backend/app/schemas/story.py               # analyst field, removed image_url from _EditStoryRequest
backend/app/schemas/feedback.py            # device_info, new issue types
backend/auto_maintenance.py                # step_recompute_centroids, keepalive, memory-safe summarize, image_checked_at skip, dedup guard, translation model fix
frontend/src/app/[locale]/page.tsx         # story dates, StoryActions component
frontend/src/app/[locale]/dashboard/page.tsx  # Refresh 16, re-embed button, device badge, new issue labels
frontend/src/components/StoryActions.tsx   # NEW: priority vote + merge buttons
frontend/src/components/StoryFeedbackOverlay.tsx  # left-4 positioning
frontend/src/components/ImprovementModal.tsx  # new issue types, device_info capture
```

---

## 2026-04-11 — LLM strategy + clustering + dashboard session

### Key outcomes

1. **3-tier LLM model strategy** — premium (`gpt-5-mini`) for homepage, baseline (`gpt-4o-mini`) for bias + long-tail, economy (`gpt-4.1-nano`) for translations. ~$8-10/month total.
2. **Clustering hardened** — size ceiling (30), time window (7 days), strict rejection-first prompt, article content in prompt, upgraded to `gpt-5-mini`. Prevents attractor clusters like the 209-article Hormuz bug.
3. **Prompts rewritten** — `BIAS_ANALYSIS_PROMPT` (~2,200 tokens, cache-eligible, Persian glossary, 3 few-shot examples) and `STORY_ANALYSIS_PROMPT` (Persian glossary, narrator rules, bias-explanation rubric with worked example, word-count ceilings).
4. **Maintenance fire-and-forget** — new shared `maintenance_state.py` module, `POST /admin/maintenance/run` returns immediately, per-step live progress tracking, detects backend-restart-mid-run as error.
5. **Dashboard overhaul** — live progress modal, diagnostics panel, recently-resummarized browser, force-refresh buttons (test 5 / refresh 30), Data Repair section (null localhost / unclaim articles), suggest page with spectrum display.
6. **Image fixes** — title-overlap picker for `story.image_url`, fast-path null for localhost URLs, per-run limit raised 100 → 300, two new admin endpoints for cleanup.
7. **Backfill steps** — `step_backfill_farsi_titles` (retries stuck translations) + `step_bias_score` (150 articles/run) added to auto_maintenance pipeline.

### Key decisions (see DECISION_LOG for details)
- D013: 3-tier LLM model strategy
- D014: Clustering — size ceiling + time window + strict prompt + article content
- D015: Rich bias scoring prompt with Persian glossary + few-shot examples
- D016: Fire-and-forget maintenance endpoint with shared state tracker
- D017: Image relevance via title-word overlap heuristic
- D018: Nullify `http://localhost:8000/images/*` URLs (admin endpoint, not auto-migration)

### Lessons learned
- **Do NOT deploy backend code while a long maintenance run is in progress.** Railway redeploys kill background asyncio tasks. (Lost a ~40-min run during this session.)
- **Hooks-order trap in `dashboard/page.tsx`**: any new `useState`/`useEffect`/`useCallback` must go ABOVE the `if (!authed) return` early return. Fixed 3 times in this session, now persisted as a memory note.
- **Clustering was LLM-based all along, not embedding-based.** The "similarity_threshold" config field is unused. Fixing the LLM prompt + adding article content + capping cluster size were the right levers.
- **Gpt-5 family parameter differences**: uses `max_completion_tokens` instead of `max_tokens`, no custom `temperature`. Centralized in `app/services/llm_helper.py`.
- **OpenAI already has 90% prompt caching**, same as Anthropic. Claude isn't uniquely cheaper on cached reads. Output tokens dominate reasoning-model cost anyway.
- **Cluster size ceiling + time window is much more robust than threshold tuning.** Simple safety valves beat complex similarity math.
- **`process_unprocessed_articles` has a trap**: only queries where `processed_at IS NULL`. If translation fails, the row gets `processed_at` set anyway and never gets retried. `step_backfill_farsi_titles` fixes this by querying `title_fa IS NULL` directly.

### Files changed (summary)
```
backend/app/config.py                     # 3-tier config fields
backend/app/services/llm_helper.py        # NEW: gpt-5 parameter adapter
backend/app/services/bias_scoring.py      # rich prompt with glossary + examples
backend/app/services/story_analysis.py    # narrator rules + bias rubric + model param
backend/app/services/clustering.py        # size ceiling, time window, content in prompt
backend/app/services/maintenance_state.py # NEW: shared progress state
backend/app/api/v1/admin.py               # 6 new endpoints
backend/auto_maintenance.py               # new steps, tiered step_summarize, uniform progress
backend/scripts/compare_models.py         # NEW: model quality comparison
backend/.env.example                      # rewritten with all vars documented
frontend/src/app/[locale]/dashboard/page.tsx  # progress modal, diagnostics, repair, etc.
frontend/src/app/[locale]/suggest/page.tsx    # tracked sources section
frontend/src/app/[locale]/stories/[id]/page.tsx # dual date display
frontend/src/app/[locale]/dashboard/layout.tsx  # NEW: dir="ltr"
frontend/src/lib/api.ts                   # revalidate 60 → 30 seconds
frontend/src/lib/types.ts                 # updated_at field
frontend/src/components/layout/Footer.tsx # removed suggest link
```

---

## 2026-04-06 — Project Kickoff

### Phase 1: Core Infrastructure (Complete)

**What was built:**

1. **Project structure** — Full monorepo with `backend/` (FastAPI) and `frontend/` (Next.js) directories, Docker Compose for PostgreSQL+pgvector, Redis, backend, Celery worker/beat, and frontend services.

2. **Database models** (7 tables):
   - `sources` — 10 Iranian news outlets with state_alignment, irgc_affiliated, factional_alignment, production_location
   - `articles` — Ingested articles with pgvector embeddings (384-dim), keywords, named entities
   - `stories` — Article clusters with blind spot detection, coverage diversity scores, trending
   - `bias_scores` — LLM-generated per-article bias analysis (political alignment, framing, tone, factuality)
   - `users` — Accounts with rater level and Bayesian reliability scores
   - `community_ratings` — Crowd ratings with blind rating support
   - `ingestion_log` — Feed fetch tracking

3. **RSS ingestion service** — Async fetcher using httpx + feedparser + trafilatura. Supports all 10 MVP sources. Deduplicates by URL. Runs every 15 minutes via Celery beat.

4. **API endpoints** — Sources CRUD, articles listing with pagination, stories with trending/blindspots, admin triggers for pipeline steps.

5. **Seed data** — All 10 sources pre-configured:
   - Diaspora: BBC Persian, Iran International, IranWire, Radio Zamaneh, DW Persian
   - State: Tasnim (IRGC), Press TV, Fars News (IRGC)
   - Semi-state: Mehr News, ISNA

6. **Utilities** — Persian text normalization (Arabic→Persian char mapping), Jalali date conversion, management CLI.

**Files created:** 47

---

### Phase 2: AI/NLP Pipeline (Complete)

**What was built:**

1. **Persian NLP module** (`app/nlp/persian.py`):
   - Text normalization via hazm library (with fallback)
   - Sentence/word tokenization
   - Lemmatization
   - Keyword extraction with Persian stopword filtering
   - Text preparation for embedding generation

2. **Embedding service** (`app/nlp/embeddings.py`):
   - Uses `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
   - Cross-lingual: Persian and English articles produce comparable embeddings
   - Batch processing with lazy model loading
   - Cosine similarity utilities for clustering

3. **Story clustering** (`app/services/clustering.py`):
   - Connected-component clustering on cosine similarity graph (threshold: 0.7)
   - Merges new articles into existing stories (threshold: 0.75)
   - Computes coverage flags: covered_by_state, covered_by_diaspora
   - Blind spot detection: stories only covered by one side
   - Coverage diversity scoring (0-1)
   - Trending score with 72-hour time decay

4. **LLM bias scoring** (`app/services/bias_scoring.py`):
   - Structured prompt with Iranian-context guidelines
   - Scores: political_alignment (-1 to +1), framing labels (15 Iranian-specific frames), tone, emotional language, factuality, source citations
   - Supports both Anthropic (Claude) and OpenAI (GPT) backends
   - JSON parsing with validation and clamping
   - Confidence estimation
   - Bilingual reasoning (EN + FA) for transparency

5. **Translation service** (`app/services/translation.py`):
   - Self-hosted Helsinki-NLP opus-mt models (free)
   - FA→EN and EN→FA title translation
   - Batch translation support
   - Graceful fallback if models not installed

6. **NLP orchestration** (`app/services/nlp_pipeline.py`):
   - Full pipeline: normalize → content extract → keywords → embed → translate
   - Processes articles in batches of 50
   - Marks articles as processed to avoid re-processing

7. **Celery tasks + beat schedule**:
   - `ingest_all_feeds_task` — every 15 min
   - `process_nlp_batch_task` — every 15 min
   - `cluster_stories_task` — every 30 min
   - `score_bias_batch_task` — every 60 min

8. **Admin API** (`app/api/v1/admin.py`):
   - Manual triggers for each pipeline step
   - `/admin/pipeline/run-all` — runs everything in sequence
   - Ingestion log viewer

**Files created/modified:** 10

---

### In Progress: Social Media Integration + Phase 3

- Adding Telegram public channel tracking
- Linking social posts to news stories
- Sentiment analysis on social discussion
- Narrative spread tracking

---

## Architecture Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Embedding model | multilingual-MiniLM (384d) | Cross-lingual clustering, smaller than ParsBERT |
| Clustering | Cosine similarity + connected components | Simple, tunable, good for small scale |
| LLM for bias | Claude Haiku / GPT-4o-mini | Cost-effective (~$75-100/mo) |
| Translation | Helsinki-NLP opus-mt (self-hosted) | Free, decent quality for titles |
| Task queue | Celery + Redis | Battle-tested, periodic scheduling |
| Database | PostgreSQL + pgvector | Single DB for relational + vector search |
| Auth | JWT + bcrypt | Simple, stateless |

## Cost Estimate (Monthly)

| Item | Cost |
|------|------|
| Hetzner VPS (CX31) | $15 |
| LLM bias scoring | $75-100 |
| Translation models | $0 (self-hosted) |
| Domain + Cloudflare | ~$1 |
| **Total** | **~$90-120** |

---

## 2026-04-06 — Social Media Integration

### Telegram Integration (Complete)

**What was built:**

1. **Data models** (`app/models/social.py`, 3 tables):
   - `telegram_channels` — Tracked public channels with political_leaning, channel_type, subscriber count
   - `telegram_posts` — Individual posts with text, views, forwards, reply counts, extracted URLs, sentiment, keywords
   - `social_sentiment_snapshots` — Periodic aggregate sentiment per story (total posts, views, avg sentiment, framing distribution, narrative divergence)

2. **Telegram service** (`app/services/telegram_service.py`):
   - Uses Telethon library (Telegram API client)
   - Fetches posts from public channels
   - Extracts URLs and matches them to known news articles → links posts to stories
   - URL normalization for reliable matching
   - `link_unlinked_posts()` — retro-links posts when new articles arrive
   - `compute_story_social_sentiment()` — aggregates sentiment snapshots

3. **API endpoints** (`app/api/v1/social.py`):
   - `GET /social/channels` — list tracked channels
   - `POST /social/channels` — add a channel
   - `GET /social/stories/{id}/social` — get Telegram posts + sentiment for a story
   - `GET /social/stories/{id}/sentiment/history` — sentiment timeline

4. **Celery tasks** (`app/workers/social_task.py`):
   - `ingest_telegram_task` — every 30 min
   - `link_posts_task` — every 30 min
   - `compute_sentiment_task` — every 60 min

5. **Seed data** — 6 initial Telegram channels (BBC Persian, Iran International, Tasnim, Fars, IranWire, Radio Zamaneh)

6. **Management CLI** — `python manage.py telegram`, `python manage.py status`

**How it works:**
```
Telegram Channels → Fetch posts → Extract URLs → Match to articles → Link to stories
                                                                          ↓
                                                              Sentiment snapshots
                                                              (positive/negative/neutral)
                                                              Framing distribution
                                                              Narrative divergence
```

**Key insight:** By linking Telegram posts to news stories, users can see not just how outlets cover a story, but how the public reacts — which frames get amplified, whether social media sentiment aligns with or diverges from media framing.

### Also created:
- **CLAUDE.md** — Project guide for Claude with conventions, setup, API reference
- **DEVLOG.md** — This file, tracking all development progress

---

## 2026-04-06 — Phase 3 Frontend + Deployment

### Frontend (Complete)

**30 files created for Next.js 14 bilingual frontend:**

Pages (7):
- Homepage with hero, trending stories, blind spot alerts
- Story feed with pagination and coverage bars
- Story detail — the core page: side-by-side article comparison, framing matrix, bias analysis, Telegram reactions
- Source directory with state↔diaspora spectrum visualization
- Source profile with metadata, IRGC badges, classification
- Blind spots page — state-only vs diaspora-only stories
- Full bilingual layout (Persian RTL + English LTR)

Components (7):
- BiasSpectrum — gradient bar with position marker
- CoverageBar — stacked colored segments per source type
- SourceBadge — colored pills with alignment label + IRGC shield
- StoryCard — card with coverage bar and blind spot badge
- StoryComparison — side-by-side articles with bias scores
- FramingTable — sources × framing labels matrix
- SocialPanel — Telegram reaction panel with sentiment bar

Design system:
- Fonts: Vazirmatn (Persian), IBM Plex Sans (English)
- Colors: red (state), amber (semi-state), emerald (independent), blue (diaspora)
- Dark mode support
- 70+ translated strings in fa.json and en.json

### Deployment

**Frontend deployed to Vercel:**
- URL: https://frontend-tau-six-36.vercel.app
- Auto-deploys from GitHub on push
- Build fixes: date-fns-jalali version, TypeScript types, next-intl setRequestLocale

**Backend deployment to Railway (in progress):**
- Fixed: pyproject.toml build-backend, Dockerfile using requirements.txt
- Fixed: Image too large (5.8GB) — removed PyTorch/sentence-transformers
- Switched embeddings to TF-IDF fallback (lightweight, sufficient for MVP)
- Cloud services configured: Neon (PostgreSQL), Upstash (Redis)

### Skills/Commands Created (15 total)

Operations: /status, /pipeline, /setup, /deploy
Content: /add-source, /add-channel, /test-feed
Analysis: /bias-check, /export, /research
Development: /design, /test-app, /nlp-debug, /devlog, /explain

### Other

- Created CLAUDE.md project guide
- Initialized git repo, pushed to github.com/parham-ashur/doornegar
- Installed GitHub CLI (gh) for authentication

---

## 2026-04-06 — Backend Deployment & First Data

### Railway Backend — Live After 8 Deployment Fixes

The backend deployment required 8 iterations to resolve:

1. **pyproject.toml** — `setuptools.backends._legacy` didn't exist in Python 3.11 on Railway → fixed to `setuptools.build_meta`
2. **Dockerfile** — was doing `pip install -e ".[dev]"` before copying source → switched to `requirements.txt`
3. **Image too large** (5.8 GB) — PyTorch + sentence-transformers exceeded Railway's 4GB free tier limit → removed, switched to TF-IDF fallback for embeddings
4. **PYTHONPATH** — Alembic couldn't find `app` module → added `ENV PYTHONPATH=/app`
5. **No migration files** — `alembic upgrade head` had nothing to run → created manual `001_initial.py` migration
6. **TelegramPost.embedding** — SQLAlchemy required type annotation for `mapped_column` → removed field (not needed for MVP)
7. **nixpacks.toml override** — Railway was using nixpacks config instead of Dockerfile CMD → deleted nixpacks.toml
8. **Startup hang** — `manage.py seed` hung during container startup → moved seeding to FastAPI lifespan event

**Result:** Backend live at `doornegar-production.up.railway.app`

### First Data Pipeline Run

Successfully ran the pipeline:
- **Ingestion:** 130 articles found, 80 new from 3 working sources
- **NLP Processing:** 80 articles processed (keywords, TF-IDF embeddings)
- **Clustering:** 12 stories created, 10 articles merged into existing stories
- **Bias Scoring:** Failed — API key issue (see below)

### Source Status

| Source | Status | Articles |
|--------|--------|----------|
| BBC Persian | Working | 30 |
| Iran International | Working (URL fixed to /fa/feed) | 50 |
| IranWire | Working | 50 |
| DW Persian | Failed (timeout/redirect) | 0 |
| Radio Zamaneh | Failed (timeout/redirect) | 0 |
| Press TV | Geo-blocked | 0 |
| Tasnim, Fars, ISNA, Mehr | Geo-blocked | 0 |

### Issues Found & Fixed

- **pgvector** — Neon free tier didn't have pgvector extension ready → replaced `Vector(384)` column with `JSONB` for embedding storage
- **Iran International RSS** — Discovered they DO have RSS at `/fa/feed` (was configured with empty `rss_urls`)
- **User-Agent blocking** — Some feeds blocked custom User-Agent → changed to browser-like UA
- **Anthropic API key** — Invalid (401 error). User switching to OpenAI GPT-4o-mini instead
- **Railway outage** — Railway had a global outage (April 6, 15:17 UTC), pausing deploys

---

## 2026-04-06 — Major Frontend Redesign + Features

### NYTimes-Style Homepage
- Replaced generic hero with editorial newspaper layout
- Large hero story (2/3 width) with dark overlay and bold headline
- Secondary stories sidebar (1/3 width)
- Masthead with project name and tagline

### New Components (4)
- **SourceSpectrum** — Media logos positioned on left↔right political axis, color-coded by alignment, clickable
- **TopicSpectrumView** — Story detail shows 3 columns: Left (Opposition/Diaspora) | Center (Independent) | Right (Pro-Establishment) with articles grouped by category
- **FactCheckBarometer** — 5-level visual barometer (Misleading → Verified), shows "Not yet assessed" as placeholder
- **Monitoring Dashboard** — Full admin page with feed status table, pipeline trigger buttons, stats cards

### Language Change
- Switched to **Farsi only** for MVP — removed language toggle from header
- English pages still exist at /en/ but hidden from navigation
- RTL-first design approach

### Backend Improvements
- **Scraping fallback** — When RSS fails, automatically tries HTML scraping (DW Persian, Radio Zamaneh, Press TV)
- **Bias scoring** — Now prefers OpenAI (GPT-4o-mini) over Anthropic when both keys present
- **Error handling** — Admin endpoints return error details instead of generic 500
- **Debug endpoint** — `/admin/debug/llm` tests both OpenAI and Anthropic keys separately

### Architecture Diagram
- Created interactive HTML architecture diagram at `docs/architecture.html`
- Shows all components, data flows, and deployment topology

---

## 2026-04-06 — Phase 4: Invite-Only Rating System

### Design Decision
Rating system is **invite-only**, not public crowdsourcing. Only trusted individuals selected by the project owner can rate articles. This prevents manipulation by state actors and prioritizes trust over scale.

### Backend (4 new files)
- **`services/auth.py`** — JWT authentication, bcrypt password hashing, token creation/validation
- **`api/v1/auth.py`** — Login endpoint (POST /auth/login). No public signup.
- **`api/v1/ratings.py`** — Rating CRUD: get next blind article, submit rating, history, public stats
- **`services/rating_aggregation.py`** — Combines AI + human scores (60% human weight, 40% AI weight)
- **Admin rater management** — Create account, list raters, deactivate (added to admin.py)

### Frontend
- **Rating page (`/fa/rate`)** — Full Farsi interface:
  - Login screen for invited raters ("فقط ارزیابان دعوت‌شده")
  - Blind article display (source HIDDEN)
  - 5 rating sliders: political alignment, factuality, tone, emotional language
  - Framing label tags (12 options, multi-select)
  - Optional notes field
  - Submit → success screen → next article flow
  - Tracks time spent per article
- **"ارزیابی" link** added to navigation

### How to Create a Rater
```
curl -X POST "https://doornegar-production.up.railway.app/api/v1/admin/raters/create?username=NAME&email=EMAIL&password=PASS&rater_level=trained"
```

### Rating Flow
```
Admin creates account → Rater logs in → Sees blind article → Rates on 5 dimensions → Submit → Next
```

---

## 2026-04-06 — Legal & Organizational Research

Created local (non-GitHub) legal folder at `/legal/` with 8 documents:
- Nonprofit structure options in France (Association loi 1901 recommended)
- Step-by-step registration (free, 4-8 weeks)
- Grant opportunities (EED, NED, OTF, GNI, RSF, and 10+ more)
- Tax benefits (66% donor deduction, VAT exemption)
- Legal concerns (scraping legality, GDPR, defamation, Iran sanctions)
- Benefits of France base (RSF in Paris, Sciences Po, INALCO, constitutional press freedom)
- Timeline and action plan

---

## Current Status (End of Day — 2026-04-06)

### What's Live
- **Frontend:** https://frontend-tau-six-36.vercel.app (Vercel, auto-deploys)
- **Backend:** https://doornegar-production.up.railway.app (Railway, currently in outage)
- **GitHub:** https://github.com/parham-ashur/doornegar (20 commits)
- **Database:** Neon PostgreSQL with 10 tables, 10 sources seeded, 130 articles, 12 stories

### Project Stats
- **Total files:** ~110 (backend + frontend)
- **Backend:** 55 Python files across models, schemas, API, services, NLP, workers
- **Frontend:** 30+ TypeScript/React files across pages, components, lib
- **Slash commands:** 15 custom commands for project management
- **Git commits:** 20

### What Works
- RSS ingestion (3/10 sources: BBC Persian, Iran International, IranWire)
- NLP processing (keywords, TF-IDF embeddings, Persian normalization)
- Story clustering (cosine similarity + connected components)
- Blind spot detection (state-only vs diaspora-only coverage)
- Monitoring dashboard with pipeline controls
- NYTimes-style homepage with media spectrum
- Invite-only rating system (backend + frontend)

### Security Reminder
- Rotate all cloud service credentials before public launch
- See local security plan for details

---

## 2026-04-06/07 — Pipeline Running, Sources Expanded, Redesign

### Pipeline Now Working End-to-End
- **OpenAI GPT-4o-mini** connected and working for bias scoring
- Full pipeline run: ingest → NLP → LLM clustering → bias scoring
- **Total cost for all API calls: $0.028** (less than 3 cents)
- 46 articles scored for bias with political alignment, framing, tone, factuality

### Sources Expanded to 15 (6 working, 3 via scraping)

| Working | Source |
|---------|--------|
| RSS | BBC Persian, Iran International, IranWire, RFI Farsi, Euronews Persian, Kayhan London |
| Scraping | DW Persian, Radio Zamaneh, Press TV (HTML fallback) |
| Failed | VOA Farsi, Radio Farda (feed URL format issue) |
| Geo-blocked | Tasnim, Fars, ISNA, Mehr (need Telegram or proxy) |

### New Backend Features
- **LLM topic clustering** (`topic_clustering.py`) — GPT-4o-mini extracts topic labels, groups articles by event
- **Cost tracking** (`llm_utils.py`) — every API call logs tokens + USD cost, GET /admin/costs endpoint
- **Scraping fallback** (`scraper.py`) — auto-scrapes HTML when RSS fails (DW, Zamaneh, Press TV)
- **Shared LLM utils** — reusable for clustering + bias scoring, tracks session totals
- **Rater account creation** — fixed bcrypt 72-byte limit, now uses JSON body

### Frontend Redesign
- Homepage completely rewritten: Ground News / NYTimes editorial style
- Hero story with large dark card + coverage pills (red=state, blue=diaspora)
- Media spectrum bar showing all sources on left↔right axis
- Blind spots section with amber warning cards
- All Farsi, language toggle hidden
- Direct API fetch in components (fixed data loading issue)
- SEO: Open Graph + Twitter card meta tags, bilingual keywords

### Legal & Grants (local, not on GitHub)
- EED grant application draft (108K EUR, 12 months) — `legal/09_EED_GRANT_DRAFT.md`
- 8 legal reference documents covering structure, registration, grants, tax, GDPR, sanctions

### Data Stats
- 230+ articles ingested
- 12 topics generated by LLM clustering
- 46 articles with bias scores
- 15 sources configured, 9 producing content
- 11 Telegram channels seeded (not yet fetching — needs Telethon)

---

## Next Steps (Resume Plan)

### Immediate (next session)
1. **Install Docker Desktop on Mac** — user was working on this
2. **Set up Docker Compose locally** — run full stack (PostgreSQL, Redis, backend, Celery) on Mac
3. **Enable Telegram via Telethon locally** — access state media content through their Telegram channels
4. **Fix VOA Farsi + Radio Farda** feed URLs — likely need different API endpoints
5. **Create admin rater account** — bcrypt fix deployed, need to test

### Short-term
6. **Run pipeline locally** — more sources, Telegram, write to Neon DB so public site shows richer data
7. **Improve frontend** — topic detail pages, better story comparison view
8. **Phase 4 testing** — test the blind rating interface with 1-2 trusted raters
9. **Topic summaries** — use LLM to generate per-topic summaries from left/center/right perspectives

### Architecture decision
- **Hybrid approach decided:** Docker locally for development + data collection, Railway+Vercel for public website, both sharing the same Neon database
- **OVH VPS (10€/month)** for later when 24/7 automation is needed
