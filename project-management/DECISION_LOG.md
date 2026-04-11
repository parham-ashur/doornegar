# Decision Log

Tracks key decisions, their reasoning, and any alternatives considered.

## 2026-04-07

### D001: Use OpenAI LLM for clustering instead of embeddings
**Decision**: Replace cosine-similarity clustering with GPT-4o-mini-based grouping.
**Why**: Embedding similarity maxed at 0.62 across Farsi/English articles — too low for reliable clustering. LLM understands semantic similarity across languages.
**Alternatives considered**: Lower similarity threshold (caused bad groupings), multilingual BERT (too slow and expensive to run locally).
**Cost impact**: ~$0.01 per clustering run (100 articles). Acceptable.
**Status**: Implemented ✓

### D002: Telegram as primary source for inside-Iran media
**Decision**: Treat Telegram posts as articles (not just social reactions) since many Iranian media channels are only accessible via Telegram.
**Why**: RSS feeds for Tasnim, Fars, ISNA, Mehr are geo-blocked. Telegram channels are the only reliable way to get their content.
**Impact**: 478 additional articles from 9 channels.
**Status**: Implemented ✓

### D003: Minimum 5 articles to show a story
**Decision**: Stories with fewer than 5 articles are hidden from the homepage.
**Why**: Small clusters are often noise or single-source stories. 5+ articles indicate genuine multi-source coverage worth analyzing.
**Trade-off**: Some real stories might be hidden if coverage is thin. Mitigated by incremental clustering (articles get added over time).
**Status**: Implemented ✓

### D004: Incremental clustering (not rebuild)
**Decision**: New articles are first matched to existing stories, then remaining ones are clustered into new stories.
**Why**: Rebuilding from scratch every time loses generated summaries, wastes OpenAI credits, and creates unstable story IDs.
**Status**: Implemented ✓

### D005: NYTimes-style design with system dark mode
**Decision**: Clean newspaper layout, no rounded corners, thin borders, white default with system-based dark mode.
**Why**: Parham's preference after multiple design iterations. Professional, readable, content-focused.
**Status**: Implemented ✓

### D006: Invite-only rating system
**Decision**: No public signup. Raters are hand-picked by Parham.
**Why**: Quality control. Public voting would be gamed. Trusted raters produce reliable ground truth for bias calibration.
**Status**: Built, not yet tested with real raters.

### D007: Store images locally
**Decision**: Download and serve images from the backend instead of hotlinking to source URLs.
**Why**: Telegram CDN links expire. Source websites may go offline or change URLs. Local storage is reliable.
**Trade-off**: Increases storage needs (~50MB for 500 images). Fine for VPS, needs cloud solution for Railway.
**Status**: Implemented locally, needs cloud solution for production.

## 2026-04-10

### D008: Cloudflare R2 for image storage
**Decision**: Store all article images in Cloudflare R2 (S3-compatible object storage).
**Why**: Telegram CDN URLs expire within hours. Local filesystem doesn't survive Railway deploys. R2 is:
- Free tier covers our use (~1% of 10 GB quota)
- Free egress (no bandwidth charges, unlike S3)
- Portable: works on Railway today, OVH tomorrow, anywhere
- CDN-backed globally (Cloudflare edge)
- Survives compute restarts
**Alternatives considered**:
- Railway persistent volume: simpler but tied to Railway, not portable
- Vercel Blob: tied to Vercel, more expensive
- S3: free tier smaller, paid egress
- Local disk: dies on restart
**Implementation**: `aioboto3` + `image_downloader.py` uploads to R2; URLs stored as permanent `https://pub-*.r2.dev/*` paths.
**Status**: Implemented ✓ (765 images migrated 2026-04-10)

### D009: slowapi for application-layer rate limiting
**Decision**: Add `slowapi` with default 200/min per IP, aggressive 10/hour on LLM endpoints.
**Why**: Cost abuse prevention. Even if an attacker gets past auth, they hit the cap. Admin-only auth is the primary defense; rate limiting is defense-in-depth.
**Alternatives considered**:
- `fastapi-limiter` (requires Redis, more ops overhead)
- Cloudflare-only rate limiting (edge-only, can't protect against authenticated abuse)
- No rate limiting (too risky after shipping public-facing LLM endpoints)
**Status**: Implemented ✓

### D010: Cloudflare CDN/WAF in front of Railway (planned)
**Decision**: Proxy all production traffic through Cloudflare before hitting Railway/Vercel.
**Why**: Free tier gives volumetric DDoS protection, bot detection, WAF, edge-level rate limiting, and "Under Attack" mode for emergencies. This is the highest-impact security improvement we can make.
**Requires**: Custom domain purchase (~$10/year) and DNS migration.
**Status**: Planned — not yet implemented.

### D011: sessionStorage over localStorage for UI state
**Decision**: Use `sessionStorage` for the welcome modal's "seen" flag.
**Why**: Better UX for testing (resets on tab close) and aligns with privacy stance (no long-term client tracking). Also added `?welcome=1` URL override for manual re-showing.
**Status**: Implemented ✓

### D012: Admin-only gating for all LLM-triggering endpoints
**Decision**: Every endpoint that can cause a billable LLM call is admin-only.
**Affected**: `POST /stories/{id}/summarize`, `POST /lab/topics/{id}/analyze`, `POST /lab/topics/{id}/generate-analysts`, all lab mutation endpoints.
**Why**: Primary defense against cost abuse. Even a successful DDoS against these endpoints only wastes bandwidth, not API credits.
**Status**: Implemented ✓

## 2026-04-11

### D013: 3-tier LLM model strategy (cost/quality tradeoff)
**Decision**: Use different OpenAI models for different tasks based on visibility and task complexity.
- **Premium (`gpt-5-mini`)**: story analysis for the top-30 trending stories (the ones visible on the homepage)
- **Baseline (`gpt-4o-mini`)**: bias scoring + long-tail story analysis
- **Economy (`gpt-4.1-nano`)**: headline translation
**Why**: Uniform gpt-5-mini would have cost ~$12-15/month; uniform gpt-4o-mini would have compromised quality on the most visible outputs (homepage summaries + side comparisons). Tiering gives us best-quality on visible content, cheap on everything else.
**Alternatives considered**:
- Uniform gpt-5-mini: rejected as unnecessary for bias scoring + translations
- Uniform gpt-4o-mini: rejected because Parham verified gpt-5-mini is noticeably better for Persian summaries and bias comparison via `compare_models.py`
- Anthropic Claude: rejected because output tokens dominate reasoning-model cost and Claude Sonnet 4.5 would cost 5-8× more than gpt-5-mini for similar quality
**Cost impact**: ~$8-10/month total (down from ~$12-15 uniform premium, up from ~$5 uniform baseline).
**Implementation**: New config fields in `app/config.py` (`bias_scoring_model`, `story_analysis_model`, `story_analysis_premium_model`, `translation_model`, `clustering_model`, `premium_story_top_n`), all override-able via env vars. `step_summarize` pre-computes top-N trending IDs and picks model per story. Shared helper `app/services/llm_helper.py` handles gpt-5-family parameter differences.
**Verification**: `backend/scripts/compare_models.py` runs the exact production prompts against all 4 candidate models on real articles and outputs `model_comparison_results.md` for human review.
**Status**: Implemented ✓

### D014: Clustering — size ceiling + time window + strict prompt + article content
**Decision**: Prevent 209-article "attractor" clusters via multiple stacked defenses.
- `max_cluster_size = 30` — story stops accepting new articles once it reaches 30
- `clustering_time_window_days = 7` — story must have `last_updated_at` within the last 7 days to be considered open for matching
- Rewrote `MATCHING_PROMPT` with "REJECTION IS THE DEFAULT", explicit reject/accept examples, "Iran-related is NOT enough", "no penalty for nulls"
- `_build_articles_block` now includes first 400 chars of article content (not just title) so the LLM can actually understand what each article is about
- Upgraded `clustering_model` default to `gpt-5-mini` (~$0.20/month extra, much more conservative matching behavior)
**Why**: The Hormuz Draft Resolution story had 209 articles about wildly different topics (moon missions, Panama gas explosions, archaeology). Root cause: the LLM matched on title keywords alone, drifted over many runs, and nothing ever shrank a cluster. User spotted it via a rater feedback item (`4ea8d828`).
**Alternatives considered**:
- Tighter embedding-similarity threshold: rejected because clustering is actually LLM-based, not embedding-based
- Post-hoc audit step (find clusters >20, ask LLM if they should be split): deferred; will add if stacked defenses aren't sufficient
- Embedding pre-filter (only show stories with cosine > 0.65 to the LLM): deferred
**Cost impact**: ~$0.50/month total for clustering (was ~$0.10/month).
**Status**: Implemented ✓

### D015: Rich bias scoring prompt with Persian glossary + few-shot examples
**Decision**: Rewrite `BIAS_ANALYSIS_PROMPT` from a short ~450-token prompt to a rich ~2,200-token prompt with role/context, Persian media glossary (state ↔ opposition term pairs), three worked examples, and a scoring rubric per dimension.
**Why**:
1. Consistency — prior prompt produced variable scores on the same article type across runs
2. Calibration — few-shot examples anchor the meaning of -0.85 vs -0.5
3. Prompt caching — static prefix ≥1024 tokens unlocks OpenAI's 90% cached-input discount
4. Quality — explicit Persian glossary helps the model recognize state vs diaspora vocabulary (فتنه / قیام, شهید / قربانی, اغتشاشگر / معترض)
**Cost impact**: essentially neutral — longer prompt per call, but prompt caching recovers most of the extra cost since a run makes 150+ calls with the same static prefix.
**Status**: Implemented ✓

### D016: Fire-and-forget maintenance endpoint with shared state tracker
**Decision**: `POST /admin/maintenance/run` now returns immediately after spawning an `asyncio.create_task`. Progress is tracked in `app/services/maintenance_state.py` (shared module with module-level STATE dict) and exposed via `GET /admin/maintenance/status`.
**Why**: Railway's HTTP proxy cuts connections after ~2 minutes of inactivity. Long maintenance runs (20-45 min with backlogs) were hitting timeout and showing "Failed to fetch" in the dashboard modal even though the backend kept working. The fire-and-forget pattern decouples HTTP lifetime from task lifetime.
**Trade-off**: If the backend container restarts (e.g. from a deploy) the asyncio task dies and loses unfinished work. Completed DB writes are persistent. Frontend now detects the "backend restarted mid-task" case (sees `idle` status after `running`) and surfaces a clear error.
**Lesson**: Do NOT push backend code while a long maintenance is in progress — Railway redeploys kill in-flight background tasks.
**Status**: Implemented ✓

### D017: Image relevance via title-word overlap heuristic
**Decision**: `step_fix_images` now picks an explicit `story.image_url` per visible story by choosing the article whose title shares the most words (≥3 chars) with the story title. Falls back to the most recent article with a valid image.
**Why**: Previously the frontend just used `story.articles[0].image_url` — arbitrary order. Combined with broken clusters (see D014), this often produced misleading hero images (e.g. a moon mission photo on a Hormuz resolution story).
**Alternatives considered**:
- Vision LLM validation (send image + title to gpt-4o-mini vision, ask if related): deferred as too expensive for every story; revisit if top-30 stories still show irrelevant images after D014 + D017 land
- Embedding similarity between story title and article title: deferred; heuristic is good enough and deterministic
**Status**: Implemented ✓

### D018: Nullify `http://localhost:8000/images/*` URLs (admin endpoint, not auto-migration)
**Decision**: Provide a one-shot admin endpoint (`POST /admin/nullify-localhost-images`) to bulk-null every row with a dev-only image URL. Those files were never migrated to R2 (verified — R2 returns 404 for the affected hashes). Post-null, `step_fix_images` re-fetches og:images from article source URLs.
**Why**: Simple rewrite `localhost:8000/...` → `pub-*.r2.dev/...` won't work because the files aren't in R2. The only recovery is to re-fetch from the original article URLs.
**Alternatives considered**:
- Hidden automatic migration during maintenance: rejected because `step_fix_images` already handles broken URLs — just need to trigger the initial null-out
**Status**: Implemented ✓, awaiting one-shot execution from dashboard

## Pending Decisions

### P001: Cloud provider for production (partially resolved)
**Options**: OVHcloud VPS still planned for Phase 7. For now, Railway + Neon + R2 works.

### P002: Domain name
**Options**: doornegar.com, doornegar.ir, doornegar.org — need to check availability and Iranian domain regulations. **Required before Cloudflare setup**.

### P003: Image storage (resolved)
**Resolved**: Cloudflare R2 (see D008).

### P004: How to handle rater disagreements
**Options**: Majority vote, weighted by rater trust score, flagged for admin review. Not yet needed (no raters active).

### P005: OpenAI hard spending cap
**Decision needed**: What monthly cap to set. Current spend is ~$1-5/month. Suggested: $30/month hard, $15/month soft alert. **Needs Parham to set on OpenAI dashboard.**
