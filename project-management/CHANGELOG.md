# Doornegar - Changelog

All notable changes to the Doornegar project are documented here, organized by work session date.

---

## April 11, 2026

### LLM Model Strategy — 3-tier system
- **Premium tier** (`gpt-5-mini`): story analysis for top-30 trending stories (homepage-visible content)
- **Baseline tier** (`gpt-4o-mini`): bias scoring + long-tail story analysis + clustering matching
- **Economy tier** (`gpt-4.1-nano`): headline translation (simple short-text task)
- New config fields: `bias_scoring_model`, `story_analysis_model`, `story_analysis_premium_model`, `translation_model`, `clustering_model`, `premium_story_top_n` (default 30)
- All overridable via env vars — no code change needed to tune
- New helper `app/services/llm_helper.py` with `build_openai_params()` that handles gpt-5-family parameter differences (`max_completion_tokens` instead of `max_tokens`, no custom `temperature`)
- Upgraded `clustering_model` default from `gpt-4o-mini` → `gpt-5-mini` (clustering is a reasoning task; ~$0.11/month delta is worth the conservative matching behavior)
- Expected total LLM cost: **~$8-10/month** (was ~$12-15 on uniform gpt-5-mini, ~$5 on uniform gpt-4o-mini)

### Clustering Fixes — prevent 209-article attractor clusters
- **Cluster size ceiling** (`max_cluster_size = 30`): stories stop accepting new matches at 30 articles; forces a new story for the next related article
- **Time window** (`clustering_time_window_days = 7`): stories whose most recent activity is >7 days old are "closed" for matching, preventing weeks-long drift
- **Stricter `MATCHING_PROMPT`**: rewrote with "REJECTION IS THE DEFAULT", concrete accept/reject examples, "Iran-related is NOT enough", "no penalty for nulls"
- **Article content in clustering prompt**: `_build_articles_block` now includes first ~400 chars of `content_text` (or `summary`) per article, not just title + source. The LLM actually understands each article's substance before deciding whether it's the same event
- Prompts still sent via `_call_openai` but now via `build_openai_params` helper so the clustering model can swap between gpt-4o-mini / gpt-5-mini / gpt-5-nano with no code change

### Bias Scoring Prompt Rewrite (for prompt caching + quality)
- Completely restructured `BIAS_ANALYSIS_PROMPT` in `app/services/bias_scoring.py`
- Static prefix is now ~2,200 tokens (well above OpenAI's 1,024-token cache threshold — 90% savings on cached reads)
- Dynamic content (`{title}` + `{text}`) moved to the very end so the entire preamble is a stable cacheable prefix
- Added rich Persian media glossary: state ↔ opposition term pairs (شهید/قربانی, مقاومت/درگیری, فتنه/اعتراض, etc.)
- Three few-shot worked examples with expected JSON output (clearly state-aligned, clearly diaspora, neutral independent)
- More explicit scoring rubric per dimension for consistency across runs
- Bias scoring now actually uses `settings.bias_scoring_model` (previously hardcoded gpt-4o-mini)

### Story Analysis Prompt Rewrite (Option A — light touch)
- Rewrote `STORY_ANALYSIS_PROMPT` in `app/services/story_analysis.py`
- Explicit neutral-narrator role: Doornegar's mission is to show readers HOW sides differ, not to take a side
- Rules: always use formal standard Persian; never copy loaded terms as assertions, always quote them in guillemets «»
- Persian media glossary (same as bias prompt) so both services share vocabulary recognition
- Explicit `bias_explanation_fa` rubric with a worked example
- Word-count ceilings per field (40-60 for overall summary, 25-40 for side summaries, 30-50 for bias explanation)
- Prompt now ~1,092 tokens, just above the 1,024 cache threshold
- `generate_story_analysis` accepts an optional `model` parameter for tiered usage
- `step_summarize` pre-computes top-N trending story IDs and picks premium vs baseline model per story
- Stores `llm_model_used` in the `summary_en` extras JSON (audit trail without a migration)

### Auto-Maintenance Overhaul
- **New shared state module** `app/services/maintenance_state.py` with a module-level `STATE` dict
- `run_maintenance()` now wraps every step with `begin_step`/`end_step` calls for per-step progress tracking
- Pipeline is now a single ordered list with uniform error handling and live status updates
- **Fire-and-forget pattern**: `POST /admin/maintenance/run` returns immediately with `{status: "started"}` and kicks off the actual run as an `asyncio.create_task`. Fixes the Railway 2-minute proxy timeout on 10+ minute runs
- **New endpoint** `GET /admin/maintenance/status` returns live state (idle/running/success/error) + current_step + completed steps[] with per-step timings and stats
- **New step** `step_backfill_farsi_titles`: retries OpenAI translation for stuck articles where `title_fa IS NULL` regardless of `processed_at`, capped at 300/run. Fixes the "process_unprocessed_articles only touches null-processed_at" trap
- **New step** `step_bias_score`: runs `score_unscored_articles` in batches up to 150/run so bias coverage catches up over time (was previously only in Celery, never in maintenance)
- **New step** `step_feedback_health`: tracks improvement + suggestion backlog stats, alerts on stale items >14 days or backlog >50

### Image Fixes
- `step_fix_images` expanded: bumped per-run limit 100 → 300 articles, fast-path null for `http://localhost` URLs (verified not in R2), new Pass 2 picks an **explicit `story.image_url`** per visible story via title-word-overlap heuristic (most relevant article's image wins, falls back to most recent)
- Previously the frontend just used `story.articles[0].image_url` which was arbitrary
- **New admin endpoint** `POST /admin/nullify-localhost-images`: bulk-nulls every row with `image_url LIKE 'http://localhost%'`, returns count
- **New admin endpoint** `POST /admin/stories/{id}/unclaim-articles`: detaches all articles from a story and hides it (`priority = -100`, `article_count = 0`). Used to nuke badly-clustered stories so their articles redistribute on the next run

### Admin Dashboard — major additions
- **Maintenance progress modal**: live elapsed-time counter, per-step live tracker (current step with seconds + scrollable list of completed steps with ✅/❌, elapsed, and top 3 stat key:values), real progress bar showing N of 23 steps + percent, auto-refreshing live counters (Articles / Missing Farsi title / Bias coverage), polls `/maintenance/status` every 3 seconds, detects lost-run case when backend restarts mid-task
- **Diagnostics panel** (`GET /admin/diagnostics`): article breakdown (no_title_fa, no_title_original, translatable_now, unprocessed, clustered, has_content), bias scoring breakdown (eligible, already_scored, remaining, coverage % of eligible), LLM key status (OpenAI/Anthropic set), auto-interpreted "What this means" panel
- **Recently re-summarized stories** (`GET /admin/recently-summarized`): list the N most-recently-updated stories with summary previews and `bias_explanation_fa`. Emerald border on stories touched in last 2h, « » "new prompt" badge auto-detected from guillemet characters. Click-through links to view in context
- **Force re-summarize buttons**: "Test: refresh 5" (~$0.30) and "Refresh 30" (~$1.80) that call `POST /admin/force-resummarize?limit=N&order=trending&mode=immediate`. Always uses the premium model. Matches the exact homepage trending order so regenerated stories are the ones visible to users
- **Data Repair section** (red-bordered, destructive): "Null localhost image URLs" and "Unclaim story articles…" buttons that wrap the admin endpoints with confirm dialogs
- **Suggest page (`/fa/suggest`)**: new collapsible "Currently tracked sources" section fetching `/api/v1/sources` + `/api/v1/social/channels`, grouped by state_alignment with clickable chips so visitors can see the spectrum before suggesting duplicates
- **Dashboard dir="ltr"**: added `dashboard/layout.tsx` forcing LTR across all admin pages since they're English-only
- **Story detail page**: now shows both `first_published_at` («خبر: N days ago») and `updated_at` («تحلیل: M minutes ago») with tooltips clarifying the difference
- Hooks-order bug fixed (three times, now with a persistent memory note): all new `useState`/`useEffect`/`useCallback` in `dashboard/page.tsx` must go **above** the `if (!authed) return` early return

### Homepage / Suggest Page
- Removed `منبعی پیشنهاد دهید` link from Footer (keeping `/fa/suggest` hidden for prelaunch invite-only use)
- Suggest page gained the "Currently tracked sources" collapsible showing real spectrum

### Maintenance Scheduler
- Moved to Railway cron service (`maintenance-cron`), separate from web service, using `python auto_maintenance.py` with `Restart Policy: Never`
- Created `backend/.env.example` documenting every environment variable for easy OVH migration later

### Model Quality Verification
- New `backend/scripts/compare_models.py` runs the exact production prompts (bias scoring + story analysis) against multiple candidate models (gpt-4o-mini / gpt-4.1-nano / gpt-5-nano / gpt-5-mini) on real articles and outputs `model_comparison_results.md` for side-by-side human review
- Handles gpt-5-family parameter differences
- Used to validate the 3-tier strategy (Parham verified gpt-5-mini best for summaries, gpt-4o-mini acceptable for titles)

### Dev experience / infra
- `.gitignore` expanded: `.Rhistory`, `backend/model_comparison_results.md` (local artifacts)
- `backend/.env.example` rewritten to document every variable the app reads, grouped by purpose (core / DB / Redis / LLM / R2 / Telegram / ingestion tunables / social integrations)

---

## April 10, 2026

### Infrastructure
- **Cloudflare R2 integration** for permanent image storage (replaces expiring Telegram CDN URLs)
- Uploaded 765 images to R2 bucket `doornegar-images` with permanent public URLs
- New management commands: `fill-images`, `check-images`, `migrate-images-to-r2`
- Both commands auto-run as steps 7/8 in the full pipeline
- Image downloader (`app/services/image_downloader.py`) now uses S3-compatible API via aioboto3
- API prefers R2 URLs over remote sources in `_story_brief_with_extras`

### Security Hardening
- Added `slowapi` rate limiting: 200/min, 2000/hour per IP default
- Per-endpoint overrides: `/trending` 120/min, `/blindspots` 60/min, `/{id}/analysis` 120/min
- LLM endpoints (`summarize`, lab `analyze`, `generate-analysts`) now admin-only + 10/hour cap
- Lab `POST/PUT/DELETE` endpoints all require admin auth (were previously unprotected)
- 1 MB max request body size middleware
- Real client IP resolution from `CF-Connecting-IP` / `X-Forwarded-For` headers
- `Permissions-Policy` header added (geolocation/microphone/camera disabled)
- `get_story_analysis`, `trending_stories`, `blindspot_stories` now accept `Request` param for rate limiting

### Homepage & UX
- `StoryReveal` animation component (scroll through article titles → reveal story thumbnail)
- `AnalystTicker` in hero box (rotating quotes from lab analysts)
- `PageAtmosphere` ambient effects (parallax, scroll entrance, breathing dividers) — time-of-day tint removed (caused grey cast on images)
- `DoornegarAnimation` footer component (day-seeded geometric figures)
- `WelcomeModal` for first-time visitors with looping SVG animation (article scatter → stack → summary lines)
- Uses `sessionStorage` (resets on tab close) + `?welcome=1` URL override for testing
- Static thumbnail replacing 3 text stories in hero sidebar
- Row 2 redesigned as hero-thumb layout (thumbnail + big image + title)
- Row 4 thumbnails: side percentages on a separate line
- Homepage text sizes increased ~10% across the board
- Header nav hidden (`خانه/خبرها/رسانه‌ها/نقاط کور/آزمایشگاه`) — kept in code, commented out
- Header clock now shows "تهران · [date] · [time]" on the left
- Images smaller than 120×80 filtered as low-quality placeholders

### Story Detail Page
- Interactive `DimensionPlot` with 8 media dimensions, Farsi descriptions, 1→5 scale legends
- Full media names displayed (no more truncation)
- Scrollable article list (height synced with sidebar via ResizeObserver)
- Sticky sidebar
- Back button removed (pointed to removed /stories page)

### Content
- Expanded to 28 news sources (+10) and 16 Telegram channels (+7)
- 8-dimension media scoring: editorial_independence, funding_transparency, operational_constraint, source_diversity, viewpoint_pluralism, factional_capture, audience_accountability, crisis_behavior
- 33 duplicate stories merged (ceasefire, Israel-Lebanon, Arbaeen clusters)
- Fixed 10 broken RSS feeds; state media now via Telegram only
- Clustering FK constraint fix (moves TelegramPost/RaterFeedback before story deletion)

### Error Handling / PWA
- `not-found.tsx` (404) with blindspot metaphor
- `error.tsx` with scattered-lines SVG animation
- `loading.tsx` with drifting-lines skeleton
- `manifest.json` and `robots.txt` added
- Privacy notice in footer

### Deployment Status
- Pushed to GitHub main (commits `b1541a6` + `0e5a272`)
- **Railway backend returning 502 after redeploy** — needs R2 env vars set manually before it can start
- Vercel frontend redeployed but partially showing stale data because Railway is down

---

## April 7, 2026 (Evening Session)

### Features Added
- **Editable story titles**: Raters can click a pencil icon on story titles to edit them inline. Saves via PATCH `/api/v1/admin/stories/{id}`
- **Rater feedback system**: Thumbs up/down on articles, summary rating, source categorization suggestions
- **Telegram integration**: 9 channels, 654 posts, converted to articles for clustering
- **LLM incremental clustering**: New articles match existing stories first, then cluster into new ones
- **OpenAI story analysis**: Per-side summaries (حکومتی/مستقل/برون‌مرزی), bias comparison, based on full article content
- **Pre-generated summaries**: All visible stories have cached summaries (instant load)
- **Local image storage**: Downloaded 522 images locally to prevent expired URLs
- **Rater accounts**: API for creating invite-only rater accounts with bcrypt auth
- **Auto-translation**: English article titles translated to Farsi via OpenAI

### Design
- NYTimes-style homepage: 3-column hero, 4-image row, text-only rows, varied layouts
- No rounded corners, thin borders, clean typography
- System-based dark/light mode
- All text in Farsi, RTL layout
- Summaries with "ادامه ←" on large story boxes
- One-line title truncation with ellipsis on compact sections

### Infrastructure
- Docker (PostgreSQL + Redis) running locally
- Pushed to GitHub, deployed to Railway (backend) + Vercel (frontend)
- Project management folder created with 7 standard documents

### Data
- 1,309 articles from 18 sources
- 168 stories (20+ visible with 5+ articles)
- 654 Telegram posts from 9 channels
- 106 bias scores

---

## April 7, 2026 (Initial Session)

### Project Management

- Created the `project-management/` folder with comprehensive documentation
- Added `PROJECT_STATUS.md` with current data metrics and infrastructure overview
- Added `ARCHITECTURE.md` with system diagrams, data flow, directory structure, and API reference
- Added `MIGRATION_PLAN.md` with step-by-step OVHcloud VPS migration checklist
- Added `BACKLOG.md` with prioritized remaining work (Must Have / Should Have / Nice to Have)
- Added `RUNBOOK.md` with operational procedures for running, deploying, and troubleshooting
- Added `CHANGELOG.md` (this file) for tracking changes across sessions

### System Status Snapshot

Current data in local development database:
- 18 news sources configured
- 1,094 articles ingested
- 132 stories clustered (20 with 5+ articles)
- 132 stories have AI-generated summaries
- 86 articles have bias scores (~8% coverage)
- 15 Telegram channels tracked
- 484 Telegram posts collected

---

## Prior Work (Before This Changelog)

### Phase 1 -- Backend Foundation
- Set up FastAPI backend with async SQLAlchemy
- Created data models: Source, Article, Story, BiasScore, TelegramChannel, TelegramPost
- Built RSS feed ingestion service for Iranian media outlets
- Implemented Persian text normalization (NLP pipeline)
- Set up embedding generation with sentence-transformers
- Created management CLI (`manage.py`) with pipeline commands
- Set up Docker Compose for local development (PostgreSQL + pgvector, Redis)
- Database migrations with Alembic

### Phase 2 -- Analysis Pipeline
- Built story clustering using vector similarity (pgvector)
- Implemented LLM-powered bias scoring (Claude Haiku)
- Built Telegram channel monitoring with Telethon
- Added blind spot detection (stories covered by only one media type)
- Created story summarization with per-perspective analysis
- Added image downloading service
- Seeded 18 news sources and 15 Telegram channels

### Phase 3 -- Frontend
- Built Next.js 14 bilingual frontend (Persian/English)
- Implemented RTL support with tailwindcss-rtl
- Added internationalization with next-intl
- Created story listing and detail pages
- Built bias visualization with Recharts (radar charts, bar charts)
- Implemented Jalali (Persian) date display
- Added source listing and filtering
- Deployed frontend to Vercel
- Deployed backend to Railway
- Connected to Neon PostgreSQL and Upstash Redis
