# Doornegar - Changelog

All notable changes to the Doornegar project are documented here, organized by work session date.

---

## April 15-16, 2026

### Niloofar Persona
- Writing style guide created from Farsi writing samples analysis. Iterated through three versions: literary-memoir → analytical-essayist → data-oriented copy-editor.
- Style guide stored in `~/.claude/output-styles/farsi-niloofar.md`, `.claude/agents/niloofar.md`, and embedded in `journalist_audit.py` prompt.
- `journalist_audit.py` restructured into 3 modes: `--gather` (default, JSON dump, no LLM), `--apply-from FILE` (findings file), `--llm` (legacy OpenAI). Default workflow is Claude-driven.
- `apply_fix` extended with `update_narratives` (writes bias_explanation_fa + state_summary_fa + diaspora_summary_fa to summary_en JSON blob), `is_edited=true` flip on all fix types.
- Editing principles added: "don't rewrite for beauty", "stay data-oriented", "smallest change that fixes the specific problem".

### Homepage Performance (9.9s → 3.0s)
- `SafeImage` migrated to `next/image` fill mode: AVIF/WebP, responsive srcset, `priority` on hero images.
- New `GET /api/v1/stories/analyses?ids=a,b,c` batch endpoint — replaces ~30 parallel `/stories/{id}/analysis` calls with 1 round trip.
- SSR fetch waterfall parallelized: stages 2-4 (analyses + telegram) now run in single `Promise.all`.
- WeeklyDigest + WordsOfWeek moved from client-side fetch to server-rendered props (0 post-hydration API calls).
- Revalidate TTLs: trending 30→300s, analyses 60/120→600s, telegram 300→600s.

### Mobile Layout
- Mobile homepage restructured: hero → telegram → blindspot → most visited → last days → today's words.
- Hero now shows both-side bias comparison + telegram predictions/claims (matching desktop).
- Mobile story detail: narratives → telegram → narrative development → stats → articles. Desktop sidebar hidden on mobile, StatsPanel rendered inline with `containerId` prop to avoid duplicate DOM IDs.

### Bug Fixes (P1–P7)
- **P1**: Hero selection prefers balanced coverage (state_pct ≥5% AND diaspora_pct ≥5%). Centroid validation in `_get_cross_story_context` (was crashing with float*None). Telegram analysis regenerated for hero story.
- **P2**: Source logo fallback in `_story_brief_with_extras` when no article has an image.
- **P4**: Story analysis + telegram analysis prompts now require same-subject validation before number comparisons.
- **P5**: key_claims in telegram analysis now require "موضوع: [subject]" prefix for same-topic pairing.
- **P6**: Weekly Brief subsections wrapped in bordered containers with header dividers.
- **P7**: Trending endpoint filters out stale stories (score <0.5) and blindspots. Press TV meta-story hidden. 6 story merges (Islamabad: 5→1, Strait: 3→1). «شهید» → «کشته» for neutrality.

### Image System Fixes
- `update_image` was a silent no-op (Story ORM has no image_url column). Override now stored as `manual_image_url` in summary_en JSON blob, read by `_story_brief_with_extras` when is_edited=true.
- Telegram CDN URLs (`telesco.pe`, `cdn.telegram`) added to bad-image blacklist (auth tokens expire → 404).
- Ceasefire hero image upgraded from 240×134 thumbnail to 1000×563 full-res via manual_image_url override.

### Maintenance Pipeline Guards
- `step_story_quality` and `step_quality_postprocess` now skip `is_edited=true` stories (was a latent bug — nightly pipeline could clobber hand-edited titles/narratives).
- `apply_fix` merge handler: re-points TelegramPost.story_id to target (FK fix), preserves summary_fa/telegram_analysis on is_edited targets.

### New Sources & Analysts
- **HRA-News** (خبرگزاری فعالان حقوق بشر) added as RSS source. state_alignment=diaspora, RSS at `/feed/`.
- **@ettelaatonline** (روزنامه اطلاعات) added as Telegram channel. political_leaning=pro_regime.
- **@kayhan_online** (کیهان آنلاین) added as Telegram channel. political_leaning=pro_regime.
- **@Naghal_bashi** (نقال‌باشی) added as Analyst. political_leaning=independent.

### Tooling
- `frontend/verify_homepage.mjs` — Playwright script for browser verification (mobile viewport, image dimensions, section ordering).
- `frontend/qa_stories.mjs` — E2E quality check: clicks through every story on the homepage and verifies title, coverage bar, bias tabs, narrative tabs, telegram section, stats, articles, and placeholder images. Exit code 1 on failures.

### Domain & Infrastructure (April 16-17)
- **`doornegar.org`** purchased from Namecheap (~€6.50/year). Domain Privacy enabled (free). Registered under Parham Ashur until IID is incorporated.
- **Cloudflare free tier** configured: DNS hosting (nameservers: kai/martha.ns.cloudflare.com), CDN with proxied CNAME records, DDoS protection, Bot Fight Mode, SSL Full mode.
- **Cloudflare Worker `api-proxy`**: routes `api.doornegar.org/*` → `doornegar-production.up.railway.app` with host header rewrite. Workaround for Railway free plan custom domain limit.
- **Vercel custom domains**: `doornegar.org` + `www.doornegar.org` added and verified.
- **CORS**: Railway `CORS_ORIGINS` updated to include `doornegar.org` and `www.doornegar.org`.
- **SSR data fetching**: kept direct to Railway for reliability (Worker adds latency). `NEXT_PUBLIC_API_URL` = `https://doornegar-production.up.railway.app`.
- **ISR revalidate bumped**: trending 5min→30min, analyses/telegram 10min→1hr, story detail 5min→1hr, sources 10min→1hr. Most page views now served as static HTML from Vercel CDN.

### Bug Fixes (additional)
- **silence_analysis crash** (React error #31): `StatsPanel.tsx` rendered a `silence_analysis` object directly as JSX text. When the field was a structured object `{silent_side, loud_side, ...}` instead of a string, React threw. Fixed with type check + human-readable fallback rendering. This was the root cause of story `603d8621` ("تحلیل پیروزی ایران") crashing entirely.
- **Image fallback chain hardened**: added `google.com/s2/favicons`, `apple-touch-icon`, `.ico` to bad-image blacklist. Source-logo fallback now validates URLs via `_is_bad_image` and prefers active sources over deactivated ones. Fixed the gatherings story (`8b61745c`) placeholder by setting a permanent R2-hosted manual image override.

---

## April 14-15, 2026

### Story editor dashboard (new)
- New `stories.is_edited` column (alembic `e9f7a3d5c8b1`). Flipped to `true` whenever an admin hand-edits title or narrative. Clustering and force-summarize skip these stories so manual edits survive nightly regeneration.
- `PATCH /api/v1/admin/stories/{id}` accepts `title_fa`, `title_en`, `state_summary_fa`, `diaspora_summary_fa`, `bias_explanation_fa`. Narrative fields are merged into the JSON blob in `stories.summary_en`.
- `POST /api/v1/stories/{id}/summarize` returns 409 Conflict when `is_edited=true` to prevent accidental overwrites.
- Removed a duplicate dead PATCH `/stories/{id}` handler that was shadowed by the earlier registration.
- New dashboard page `/fa/dashboard/edit-stories`: search, configurable fetch limit (15/30/50/100/200), expandable row per story with 5 textareas, one-click save, inline status, amber "ویرایش دستی" badge. Persian-insensitive search normalizes ی/ي, ک/ك, zero-width joiners.
- Linked from the main dashboard via a new "Open Editor" card.

### Maintenance pipeline fixes
- `maintenance_logs` INSERT now supplies an explicit `uuid.uuid4()` for the `id` column. Previously only 1 row had ever persisted because the INSERT omitted id and the column has no DB default. Both success + error code paths fixed in `auto_maintenance.py`.
- `step_telegram_link_posts` crash fixed. Was raising `unsupported operand type(s) for *: 'float' and 'NoneType'` whenever a story's `centroid_embedding` contained null values or was stored in the wrong shape. Now validates vectors before use and catches any remaining shape mismatches in `cosine_similarity`.
- `merge_similar_visible_stories` FK violation fixed. `db.delete(victim)` was failing because `telegram_posts.story_id` still referenced the victim. Now re-points `TelegramPost.story_id` to the keeper before delete.
- `GET /api/v1/stories/{story_id}` 500 fixed. Was throwing `MissingGreenlet: greenlet_spawn has not been called` during `StoryBrief.model_validate(story)` after the inline `view_count` commit. Moved the view-count bump into a FastAPI `BackgroundTasks` handler that runs in a fresh session after the response is built. Also switched to `_story_brief_with_extras()` so the detail response now includes `image_url` / `state_pct` / `diaspora_pct` (they were missing before).

### Telegram ingestion on Railway (Phase 6 partial)
- `requirements.txt` now includes `telethon>=1.36` — it was previously only in `[project.optional-dependencies].social` so the Docker build never installed it. Before this fix, Railway maintenance cron was always returning `telegram_new: 0`.
- New config setting `telegram_session_string`. When set, `telegram_service.py`, `social_posting.py`, and `auto_maintenance.py` use `StringSession(settings.telegram_session_string)` instead of the file-based `doornegar_session.session`. Survives Railway container rebuilds.
- New helper script `backend/scripts/export_telegram_session.py` — converts a local file session to a `StringSession` blob for pasting into Railway.
- Session string set on both `doornegar` and `maintenance-cron` services.
- Verified end-to-end: manual maintenance run fetched 363 new telegram posts from the Railway container in 30 minutes. Top channels: @radiofarda (50), @Asriran_press (50), @Tasnimnews (48), @masaf (45), @mehrnews (44), @khabaronline_ir (41). Previous last-fetch was 2026-04-13 07:08 UTC.

### RSS source cleanup
- Updated 3 URLs in production DB:
  - `press-tv`: `/RSS` → `/rss.xml`
  - `ilna`: `/fa/rss` → `/rss`
  - `entekhab`: `/fa/rss` → `/fa/rss/allnews`
- Deactivated 4 sources (`is_active=false` — soft-delete, preserves articles + relationships):
  - `fars-news`: removed their public RSS feed (every URL returns SPA HTML)
  - `dw-persian`: DW discontinued their Farsi RSS feed ("Error: no feed by that name")
  - `radio-zamaneh`: feed now requires Cloudflare Access authentication
  - `isna`: Cloudflare challenge blocks all non-browser clients
- Iran-hosted feeds still failing from Railway US IP (geoblocked): khabaronline, tasnimnews, mehrnews, mashreghnews, nournews, iribnews, etemadnewspaper. These work fine via the Telegram API so their coverage isn't lost.
- Active source count: **27 → 23**.

### Suggest-source page simplified
- Removed the category grouping (محافظه‌کار / نیمه‌محافظه‌کار / مستقل / اپوزیسیون) from `/fa/suggest`. Now a single flat list under "رسانه‌ها" and "کانال‌های تلگرام". Shortened the intro sentence.

### Mobile stories carousel exploration (parked)
- Full 13-step build of an Instagram-style 6-slot (later 7) looping carousel for mobile. 4 layout types (Story, Telegram, Blindspot, MaxDisagreement) plus a DesktopPreview iframe slot. Drilldown via tap/swipe, StoryDetailOverlay with swipe-back, OnboardingHints, StringSession-style title animations, mix-blend-difference for auto-contrast, violet borders for MaxD, animated swipe-up arrow.
- Lives at `/fa/stories-beta` — **NOT** the production mobile homepage. `/fa` mobile was reverted to the original `MobileHome()` scrolling list while Parham iterates on the carousel separately.
- New files: `frontend/src/components/stories/*`, `frontend/src/lib/stories-data.ts`, `frontend/src/app/[locale]/stories-beta/page.tsx`, `frontend/src/components/layout/ChromeGate.tsx`.

### Deploy pipeline
- Discovered GitHub → Vercel auto-deploy hook is disconnected (14 h stale). Been triggering production deploys manually via `cd frontend && vercel deploy --prod --yes`. Open item: reconnect in Vercel project settings.
- Recovered production DB from a phantom `da6408183397` alembic revision (stamped by a previous session's uncommitted migration file). Schema was unchanged; rewrote `alembic_version` directly to `d8e5f1a2b3c4` before applying the new migration. Added a permanent rule to `CLAUDE.md` and persistent memory: commit alembic files to git BEFORE running `upgrade head` on production.

---

## April 12, 2026

### Maintenance Pipeline Audit — 8 fixes
- **Keepalive pings** added to `step_summarize` and `step_bias_score` (prevents Neon connection timeout during long LLM calls)
- **`llm_failed_at` column** on Article + Story models with 24h retry backoff (Alembic migration `b5e9f3a1c2d8`)
- **Batched `_refresh_stories_metadata`** in `clustering.py` (N×4 queries → 3 aggregate queries)
- **`step_summarize` loads only 10 most-recent articles per story** (memory-safe on 512MB Railway)
- **`image_checked_at` column** on Article + 24h skip in `step_fix_images` (migration `b5e9f3a1c2d8`)
- **`step_deduplicate_articles`**: NULL/whitespace title guard (length >= 10)
- **`step_fix_issues`** uses `settings.translation_model` instead of hardcoded `gpt-4o-mini`
- **Double-match guard** in clustering `_match_to_existing_stories`

### Story.image_url bug fix
- `step_fix_images` was crashing with `"'Story' object has no attribute 'image_url'"` — Story model has no `image_url` column
- Moved the title-overlap image picker to `_story_brief_with_extras()` (response-time computation)
- Removed `image_url` from `_EditStoryRequest`

### Deep Analyst Factors (15 categories)
- `ANALYST_FACTORS_ADDENDUM` prompt block appended for premium-tier stories
- 15 analytical factors in Persian: `risk_assessment`, `potential_outcomes`, `key_stakeholders`, `missing_information`, `credibility_signals`, `timeline`, `framing_gap`, `what_is_hidden`, `historical_parallel`, `economic_impact`, `international_implications`, `factional_dynamics`, `human_rights_dimension`, `public_sentiment`, `propaganda_watch`
- Tagged as "doornegar-ai" LLM analyst (future human analysts from Telegram sit alongside)
- `generate_story_analysis` accepts `include_analyst_factors` param
- Stored in `summary_en` extras JSON under `"analyst"` key
- Exposed via `StoryAnalysisResponse.analyst` field
- Only for premium-tier (top-16) stories

### Premium tier: 30 → 16
- `premium_story_top_n` changed from 30 to 16 (only 16 stories visible on homepage)
- Dashboard button "Refresh 30" → "Refresh 16"

### Homepage enhancements
- Story dates in Meta component: `first_published_at` + `updated_at` (shows "به‌روز: X پیش" if >1h different)
- Priority up/down vote buttons (ArrowUp/ArrowDown) on ALL story cards in feedback mode
- Merge suggestion button (GitMerge icon) on all story cards
- `StoryActions` reusable component
- `StoryFeedbackOverlay` moved from `right-4` to `left-4` (was covering RTL title)

### New issue types
- `priority_higher`, `priority_lower`, `merge_stories` added to `IssueType`
- Backend schema + frontend `ImprovementModal` + admin dashboard labels updated

### Device context on feedback
- `device_info` field added to `ImprovementFeedback` model (migration `c7d4e2f8a1b3`)
- Frontend auto-captures: `"mobile 375×812 Mozilla/5.0..."` or `"desktop 1440×900..."`
- Admin dashboard shows purple "mobile" badge on mobile-submitted items

### OpenAI Embeddings
- Switched from sentence-transformers/TF-IDF to **OpenAI `text-embedding-3-small`**
- 384 dimensions (compatible with existing stored embeddings)
- Cost: ~$0.02/M tokens (~$0.05/month)
- No PyTorch dependency needed (~2GB saved)

### Embedding Pre-filter for Clustering
- **Two-phase clustering**: embedding cosine similarity pre-filter → LLM confirmation
- `Story.centroid_embedding` column added (JSONB, migration `d8e5f1a2b3c4`)
- `_compute_centroid()` helper: mean of article embeddings, L2-normalized
- `step_recompute_centroids` added to maintenance pipeline after clustering
- Threshold 0.30 (loose — lets LLM reject false positives)
- `POST /admin/re-embed-all` endpoint + dashboard "Re-embed all articles" button

### Framing + article dates in LLM prompts
- Framing labels capped at max 3 per side in story analysis
- Article publish dates included in the LLM prompt
- Full article content (6000 chars) for premium-tier stories (was 1500)

### Last Maintenance card fix
- `_get_maintenance_info` now derives from DB (`max Article.ingested_at`) as primary fallback
- Survives Railway deploys (in-memory state + log file are ephemeral)

### Neon connection keepalive fix
- Root cause: asyncpg connection closed during long clustering (340s of LLM calls)
- `_keepalive(db)` helper does `SELECT 1` before each LLM call
- `pool_recycle` lowered 3600 → 240 in `database.py`

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
