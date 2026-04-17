# Doornegar - Backlog

**Last updated**: 2026-04-17 (Audit + security + narrative taxonomy + pipeline hardening + i18n plan)

## Done this session (2026-04-17)

### Audit
- [x] **Wide-shallow audit across 8 dimensions** — security, infra, backend code, pipeline, frontend, UX, data quality, tech debt. Report at `AUDIT_2026-04.md` with 36 findings tiered Blocker/Risk/Nice-to-have.
- [x] **I18N_PLAN.md** — 3-tier plan (chrome / content / polish) + before/after layout diagrams + 30 anticipated complications. Ready to execute when Parham greenlights.

### Security (Blockers closed)
- [x] Hardcoded `doornegar2026` password removed from 5 dashboard pages; single token-validation flow in main dashboard.
- [x] `.gitignore` tightened to `.env*` glob with `!.env.example` exception.
- [x] Orphan `backend/.env.backup` + `frontend/.env.vercel` deleted.
- [x] `POST /social/channels` gated with `require_admin`.
- [x] `PATCH /sources/{slug}` + `PATCH /channels/{id}` both gated with `require_admin` and accept `is_active`.
- [x] OpenAI monthly spend cap set, Cloudflare Bot Fight enabled, UptimeRobot monitor active.

### Pipeline hardening (moved to auto_maintenance after discovering Celery isn't running in prod)
- [x] Per-step `asyncio.wait_for` timeout map in `auto_maintenance.py`.
- [x] Redis single-flight lock with fail-open fallback.
- [x] `--mode {full,ingest}` CLI flag; `ingest-cron` Railway service at `0 */6 * * *` UTC shares the lock with the daily full run.
- [x] Auto-seed RSS sources from `seed.py` on every ingest run.
- [x] Celery decorators + `task_lock.py` removed; worker files note dormant status.
- [x] `step_flag_unrelated_articles` auto-detaches instead of flagging; residual bot rows cleared every run.
- [x] Per-source try/except in `ingest_all_sources`; silent exception handlers logged.

### Narrative taxonomy (3 commits)
- [x] New `backend/app/services/narrative_groups.py` + 32 parameterized tests per existing source.
- [x] `NarrativeGroupPercentages` on StoryBrief; `inside_border_pct` / `outside_border_pct` totals; legacy `state_pct` / `diaspora_pct` kept for backwards compat.
- [x] `frontend/src/lib/narrativeGroups.ts` with navy/orange color palette and share-of-side percentage calculator.
- [x] Frontend label sweep: محافظه‌کار → درون‌مرزی, اپوزیسیون → برون‌مرزی across ~28 files.
- [x] `StoryAnalysisPanel` tabs renamed; renders subgroup bullets with colored dots when available.
- [x] `CoverageBar` rewrite — 4 stacked segments, 2px divider, share-of-side percentages.
- [x] `story_analysis.py` prompt rewritten to tag articles by subgroup on input and emit structured bullet output. Legacy flat summaries synthesized by joining bullets.
- [x] Blindspot + silence-detection partition switched from `state_alignment` to `narrative_group`. Etemad-Online now correctly inside-border.
- [x] `bias_scoring` temperature fixed to 0 (was 0.3).

### Data
- [x] HRANA + Etemad Online added to `seed.py`; both verified live.
- [x] Blindspot threshold 10% → 20% + small-cluster rule for <6 articles.
- [x] Aged-orphan counter (articles `story_id=NULL` older than 30 days).
- [x] Telegram analysis cache TTL (48h) + admin `force_refresh` bypass + explicit invalidate endpoint.

### Admin dashboard
- [x] **Fetch Stats** page at `/dashboard/fetch-stats` with `is_active` toggle per row.
- [x] `improvements/admin` default `include_bot=false` — rater-only todo list.
- [x] **Run Maintenance progress modal** rebuilt with minimize-to-corner, phase grouping, readable step stats, summary metric cards, failed-step banner.
- [x] 3 dead components deleted.

### CI & tests
- [x] `.github/workflows/ci.yml` — frontend tsc + backend compile + import smoke + pytest on every PR/push to main.
- [x] 59 tests green (32 narrative_groups, 16 blindspot, 11 routes + Persian normalization).

### Docs
- [x] `DEVLOG.md`, `CHANGELOG.md`, `PROJECT_STATUS.md`, `BACKLOG.md`, `ARCHITECTURE.md` updated with this session.
- [x] `RISK_REGISTER.md` refreshed: R2 / R14 / R18 / R19 / R21 mitigated.

## Done this session (2026-04-17 afternoon/evening)

### Niloofar
- [x] `/admin/niloofar/audit` + `/admin/niloofar/apply-fix` endpoints deleted. Dashboard Niloofar card removed; Niloofar moved into the Claude Persona Audits grid as a 6th card.
- [x] English-conversation / Farsi-DB-output rule documented in `.claude/agents/niloofar.md` and in `project_personas.md` memory (all six personas).
- [x] `update_narratives` fix_type accepts 4 new subgroup arrays (principlist/reformist/moderate/radical); legacy flat summaries auto-synthesized from bullets.
- [x] **Pass 1** — 11 edits applied (8 renames, 2 narrative rewrites, 1 summary rewrite) via `--apply-from`.
- [x] **Pass 2** — 3 deep rewrites with full 4-subgroup narratives on is_edited stories (Islamabad talks 119 articles, Hormuz blockade 18, Lebanon 2055 26).
- [x] Niloofar persona — "Bias comparison editing rules" section (4-12 bullets scaling by article count + exclusivity), "Narrative editing and the 4-subgroup format" section, "Title rule — no meta-framing" section with banned phrase list.

### Pipeline / prompt
- [x] `story_analysis.py` prompt: bullet count scales with article count (5-7 to 9-12), explicit anti-redundancy rule with concrete failure-mode examples, two new bullet patterns (subgroup-internal differences + source credibility contrasts).
- [x] `step_niloofar_editorial` expanded from top 15 to top 30 stories.
- [ ] `story_analysis.py` title rule — no-meta-framing strengthening pass (queued — will push after next Refresh 16 completes to avoid killing it).

### Force-resummarize
- [x] Filters `is_edited=False` so Niloofar edits aren't overwritten.
- [x] Writes `narrative`, `dispute_score`, `loaded_words`, `narrative_arc`, `source_neutrality` to `summary_en`.
- [x] Preserves `manual_image_url` across rewrites.
- [x] Refactored to fire-and-forget background task (`asyncio.create_task` + `force_resummarize_state.py`). `GET /admin/force-resummarize/status` for polling. Survives Cloudflare 100s edge timeout.
- [x] Per-story outcomes persisted to `maintenance_logs` (survives Railway redeploy). Status values: `force_resummarize_ok`, `force_resummarize_partial`, `force_resummarize_error`.
- [x] Per-article content cap: 6000 → 3000 chars. Halves input tokens, fits big clusters under budget.

### Dashboard UX
- [x] "Reopen progress window" button on the Last Maintenance card — attaches to running server-side jobs after a page refresh.
- [x] Progress bar for Refresh 5 / Refresh 16 — dynamic ETA (converges to actual per-story time after first story), real processed/total count, current story title, auto-attach on page mount.
- [x] `TelegramDiscussions` homepage card: 3 predictions → 2.

### Animation
- [x] `DoornegarAnimation.tsx` — new `triangleDown` shape type. Hourglass pattern fixed (apex-to-apex meeting at the pinch-point circle). Star pattern fixed (Star of David hexagram with interlocking up + down triangles).

### Homepage slot rotation (commit b74ec4c)
- [x] `Story.last_updated_at` exposed on `StoryBrief` schema + TS type.
- [x] `isFresh(s)` stateless helper = `last_updated_at` within 24h.
- [x] Hero picker: 4-step fallback (fresh+balanced → fresh → balanced → top trending).
- [x] Blindspots: prefer fresh per side; empty slot if no fresh blindspot rather than re-surfacing stale.
- [x] Telegram predictions/claims source pool prefers fresh stories with a ≥3-fresh safety threshold.

## Done this session (2026-04-15/16)
- [x] **Niloofar writing style** — defined, iterated 3 versions, agent file + output style + prompt all aligned
- [x] **Niloofar Claude-driven workflow** — gather JSON → analyze in chat → apply findings. No OpenAI.
- [x] **Homepage performance 9.9s → 3.0s** — parallelized SSR, batch analyses, server-side WeeklyDigest/WordsOfWeek, next/image
- [x] **Mobile homepage restructured** — hero with bias+telegram, section reorder (telegram → blindspot → most visited → last days → words)
- [x] **Mobile story detail restructured** — narratives → telegram → dev → stats → articles
- [x] **P1: Hero balanced coverage** + centroid validation fix + telegram analysis regenerated
- [x] **P2: Source logo fallback** for imageless stories
- [x] **P4: Same-subject validation** in number comparison prompts
- [x] **P5: Subject-tagged key_claims** for same-topic pairing
- [x] **P6: Weekly Brief** bordered subsections
- [x] **P7: Trending filter** (stale + blindspot exclusion), 6 merges, neutral title, Press TV hidden
- [x] **update_image fix** — was silent no-op, now writes to summary_en blob
- [x] **is_edited guards** on step_story_quality + step_quality_postprocess
- [x] **3 new sources/channels** (HRA-News, @ettelaatonline, @kayhan_online) + 1 analyst (@Naghal_bashi)
- [x] **Playwright verify script** committed

## Done this session (2026-04-14/15)
- [x] **Story editor dashboard** — `/fa/dashboard/edit-stories` with search + is_edited flag protecting manual edits from regeneration
- [x] **Telegram ingestion on Railway** — `TELEGRAM_SESSION_STRING` env var, telethon in requirements.txt, verified 363 new posts fetched from the cron container
- [x] **Maintenance pipeline recovery** — maintenance_logs INSERT, telegram_link NoneType, merge_similar FK violation, GET /stories/{id} MissingGreenlet
- [x] **RSS cleanup** — 4 sources deactivated (fars-news, dw-persian, radio-zamaneh, isna), 3 URLs updated (press-tv, ilna, entekhab). Active count 27 → 23.
- [x] **Suggest-source page** simplified (removed category grouping)
- [x] **Mobile stories carousel** exploration at `/fa/stories-beta` — parked for future iteration; production mobile homepage reverted to original `MobileHome()`

## Must Have (before public launch)

### Immediate (blocks launch)
- [ ] **Railway watch-paths config** — auto-deploys on any push to `main` including frontend-only commits. Needs path filter to `backend/**` so Vercel-only deploys don't kill in-flight background tasks (Refresh 16 keeps getting interrupted). Parham-driven dashboard change.
- [ ] **Fix 4 pass-1 Niloofar titles** that still have meta-framing («پوشش یک‌سویه», «روایت‌های حکومتی و برون‌مرزی») per the new no-meta-framing rule. IDs: 603d8621, e0e0a475, ba2ed5b7, d2491715.
- [ ] **Story-analysis prompt title rule tightening** — already forbids «روایت» but LLM ignores it sometimes; needs stronger language + more examples. Requires Railway redeploy so hold until no active Refresh job.
- [ ] **Retry-on-failure with exponential backoff** for force-resummarize background job — one retry after 5s would catch rate-limit transients.
- [ ] **Failure-log viewer** for force-resummarize on the dashboard — `/admin/maintenance/logs` returns the new rows but there's no pretty UI for the per-story error breakdown.
- [ ] **Set R2 env vars on Railway** (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL) — backend is 502 without these
- [ ] **Set SECRET_KEY and ADMIN_TOKEN on Railway** (generate random 32+ char strings)
- [ ] **Set OpenAI hard spending limit** ($30/month) on platform.openai.com/usage
- [ ] **Rotate exposed R2 API token** (shared in chat) after deployment works
- [ ] Rotate Neon DB password, Upstash Redis password, Anthropic API key (shared in chat previously)
- [x] **Custom domain `doornegar.org`** — Namecheap + Cloudflare free tier + Vercel custom domain. API via Cloudflare Worker at `api.doornegar.org`.
- [ ] **Reconnect GitHub → Vercel auto-deploy hook** — currently disconnected, requires manual `vercel deploy --prod --yes` after every push
- [ ] **Weekly Brief story links** — backend `niloofar_weekly.py` needs to emit story IDs so frontend can render clickable links under each subsection (P6 partial)
- [ ] **Latin → Farsi digit consistency** — some story titles still use Latin digits (2055 vs ۲۰۵۵). Should be caught by Niloofar audits going forward

### Security & Operations
- [ ] **Cloudflare CDN/WAF in front of Railway** — single biggest security win
  - Requires a custom domain (~$10/year)
  - Gives: DDoS protection, bot detection, WAF, rate limiting at edge, analytics
  - See RUNBOOK for setup steps
- [ ] **UptimeRobot monitoring** — free, pings /health every 5 min, emails on outage
- [ ] **Railway max-instance limit** — prevent runaway scaling costs
- [x] **Automated maintenance scheduler** — Railway cron service `maintenance-cron` runs `python auto_maintenance.py` nightly
- [ ] Automated daily database backup (Neon → local/S3)
- [ ] Sentry error tracking (free tier)

### Content
- [ ] Bias scoring full coverage — priority scoring now caps at 100/run; focus is on visible stories first
- [ ] Content review of LLM-generated summaries (spot-check for accuracy — use dashboard "Recently re-summarized" card + quality post-processing now catches some issues automatically)
- [ ] Add more Iranian media sources (geo-blocked ones via proxy)
- [ ] Clean up pre-size-ceiling oversized clusters (use dashboard "Unclaim story articles" button as spotted)
- [ ] One-shot: click "Null localhost image URLs" on dashboard + run maintenance 3-4 times to re-fetch og:images for ~2,000 articles
- [ ] Seed initial analyst records (Telegram commentators, political analysts) for AnalystTake extraction pipeline

## Should Have

### UX Improvements
- [ ] Test thoroughly on actual mobile device
- [ ] Search functionality (full-text search)
- [ ] Pagination or infinite scroll on story lists
- [ ] Story detail: timeline of when each outlet published
- [ ] Display silence detection results on story detail page (data available in summary_en JSON)
- [ ] Display coordinated messaging alerts on story detail page
- [ ] Display narrative arc / what-changed delta on story detail page
- [ ] Analyst takes section on story detail page (show extracted predictions, reasoning)
- [x] ~~Improve LLM clustering precision~~ — embedding pre-filter + double-match guard + keepalive (2026-04-12)
- [x] ~~Homepage redesign~~ — BBC-style top section, weekly briefing, most disputed, battle of numbers, narrative map, words of week (2026-04-12)
- [x] ~~Story detail page redesign~~ — tabbed analysis, political spectrum, stats panel (2026-04-12)
- [x] ~~Label neutrality~~ — حکومتی→محافظه‌کار, برون‌مرزی→اپوزیسیون, نقاط کور→نگاه یک‌طرفه (2026-04-12)
- [x] ~~Source logos~~ — added for all 18 outlets (2026-04-12)
- [x] ~~NarrativeMap PCA scatter plot~~ — API-driven article positions visualization (2026-04-13)
- [x] ~~WordsOfWeek API integration~~ — fetches from /insights/loaded-words endpoint (2026-04-13)
- [x] ~~Battle of Numbers dynamic data~~ — now uses story analysis data instead of hardcoded (2026-04-13)

### Phase 4 Prep (Rating System)
- [ ] Create first admin rater account
- [ ] Email-based invite system for new raters
- [ ] Rating UI polish

### Intelligence Layer (New — Future Enhancements)
- [ ] Expand analyst database — seed 20+ Iranian political commentators with Telegram handles
- [ ] Prediction scorecard — aggregate verified/falsified predictions per analyst, show reliability %
- [ ] Silence detection dashboard — dedicated page showing all current silences with hypotheses
- [ ] Coordinated messaging timeline — visual timeline of synchronized coverage events
- [ ] Narrative arc visualization — show story evolution over days/weeks with key turning points
- [ ] Cross-story intelligence briefing — weekly summary of how stories connect and influence each other

## Nice to Have

- [ ] **Next.js 14 → 15/16 upgrade** — currently on 14.2.35 (stable but aging). Upgrade path:
  - Use `npx @next/codemod@canary upgrade latest` for automated migration
  - Review breaking changes in async request APIs (`cookies()`, `headers()`, `params`, `searchParams` become Promises)
  - Test all pages with RTL layout, next-intl, and static generation
  - Evaluate Turbopack for faster dev builds (stable in 15+)
  - Check next-intl compatibility with new version
  - Not urgent — current version works and gets security patches
- [ ] Live Telegram channel monitoring (real-time via WebSocket)
- [ ] Analytics dashboard (cost tracking, usage metrics, pipeline stats)
- [ ] Full English translation (site currently Farsi-only)
- [ ] Community voting on bias scores (public)
- [ ] Export stories as PDF
- [ ] Dark mode toggle (currently system-based only)
- [ ] Tune quality audit thresholds after initial data collection
- [ ] Auto-merge confidence threshold tuning (monitor false merges)

## Phase 5: Cloudflare + Monitoring — DONE (2026-04-17)

**Goal**: Make the site resilient to attacks and get visibility into outages.

### Setup checklist
- [x] Purchase domain — `doornegar.org` from Namecheap (~€6.50/year, Domain Privacy free, auto-renew)
- [x] Cloudflare free tier — existing account (same as R2)
- [x] Add domain to Cloudflare, update nameservers (kai.ns.cloudflare.com, martha.ns.cloudflare.com)
- [x] DNS records:
  - `doornegar.org` → CNAME to `cname.vercel-dns.com` (proxied)
  - `api.doornegar.org` → CNAME to `doornegar-production.up.railway.app` (proxied) + Cloudflare Worker `api-proxy` for host header rewrite
  - `www.doornegar.org` → CNAME to `cname.vercel-dns.com` (proxied)
- [x] Add custom domain in Vercel: `doornegar.org` + `www.doornegar.org`
- [x] Railway custom domain skipped (free plan limit) — Worker proxy handles `api.doornegar.org` instead
- [x] SSR data fetching kept direct to Railway for reliability (`NEXT_PUBLIC_API_URL=https://doornegar-production.up.railway.app`)
- [x] Cloudflare settings: SSL/TLS → Full, Bot Fight Mode → enabled, detection tools active
- [x] CORS updated to allow `doornegar.org` + `www.doornegar.org`
- [ ] UptimeRobot:
  - Create free account (uptimerobot.com)
  - Add monitor: HTTPS, `https://api.doornegar.org/health`, check every 5 min
  - Add email alert
  - Add second monitor: `https://doornegar.org`
- [ ] Document DNS/domain credentials in a password manager
- [ ] Transfer domain + accounts to IID once nonprofit is registered

## Phase 6: OVHcloud Migration (Future)

See `MIGRATION_PLAN.md` for the full step-by-step plan.

- [ ] Purchase OVHcloud VPS (EU region, ~10€/mo)
- [ ] Set up Docker + Nginx + Certbot
- [ ] Migrate database from Neon (`pg_dump`/`pg_restore`)
- [ ] Move Celery + Telegram worker to VPS
- [ ] Update DNS: `api.doornegar.com` → VPS IP
- [ ] Keep R2 for images (portable across providers)
- [ ] Keep Vercel for frontend (free CDN)
- [ ] Decommission Railway + Upstash

## Completed

- [x] Phase 1: Backend models, RSS ingestion, NLP pipeline
- [x] Phase 2: Story clustering, bias scoring, Telegram integration
- [x] Phase 3: Next.js bilingual frontend with RTL support
- [x] 28 news sources seeded (was 18)
- [x] 16 Telegram channels configured (was 15)
- [x] 8-dimension media scoring system
- [x] Homepage redesign (hero, StoryReveal, AnalystTicker, PageAtmosphere)
- [x] Welcome modal with looping animation
- [x] Error/loading/404 pages with themed animations
- [x] Admin token authentication on all mutation endpoints
- [x] Rate limiting (slowapi, 200/min default + per-endpoint overrides)
- [x] Request size limits, security headers, CORS restrictions
- [x] LLM endpoints protected (admin-only + 10/hour cap)
- [x] Cloudflare R2 image storage (765 images uploaded)
- [x] Image quality filtering (SafeImage)
- [x] Footer animation with day-seeded geometric figures
- [x] Story detail page: interactive DimensionPlot, scrollable article list
- [x] Navigation hidden from menu (kept in code)
- [x] Pushed to GitHub and deployed (commits b1541a6, 0e5a272)
- [x] OpenAI embeddings (text-embedding-3-small, replaced sentence-transformers/TF-IDF)
- [x] Embedding pre-filter for clustering (cosine pre-filter → LLM confirmation)
- [x] Story centroid embeddings with step_recompute_centroids
- [x] Deep analyst factors (15 categories) for premium-tier stories
- [x] Neon connection keepalive fix (pool_recycle 240s + _keepalive pings)
- [x] LLM retry backoff (llm_failed_at column, 24h window)
- [x] Maintenance pipeline audit — 8 fixes (batched metadata refresh, memory-safe summarize, image_checked_at, dedup guard, translation model fix, double-match guard)
- [x] Story.image_url bug fix (moved to response-time computation)
- [x] Premium tier 30 → 16
- [x] Priority vote + merge suggestion buttons on story cards
- [x] Device context on improvement feedback
- [x] New issue types: priority_higher, priority_lower, merge_stories
- [x] Homepage redesign — BBC-style top section with weekly briefing, most disputed, battle of numbers, narrative map, words of week
- [x] Story detail page redesign — tabbed analysis, political spectrum, stats panel
- [x] Label renaming for neutrality: حکومتی→محافظه‌کار, برون‌مرزی→اپوزیسیون, نقاط کور→نگاه یک‌طرفه
- [x] Quality audit system — daily 5 checks with Neon optimization
- [x] Auto-merge similar stories
- [x] Title auto-update from LLM
- [x] Trending diversity reranking with exponential decay
- [x] Source logos for all 18 outlets
- [x] Source neutrality scoring
- [x] Telegram embed image fallback
- [x] PATCH admin endpoints for stories, articles, sources
- [x] Two-pass analysis (nano fact extraction → premium framing) (2026-04-13)
- [x] Cross-story memory (related story summaries injected as context) (2026-04-13)
- [x] Source track records (historical reliability per source in prompts) (2026-04-13)
- [x] Silence detection with LLM-generated hypotheses (2026-04-13)
- [x] Coordinated messaging detection (cosine > 0.85 within 6h) (2026-04-13)
- [x] Narrative arc tracking + what-changed delta (2026-04-13)
- [x] Prediction verification pipeline (2026-04-13)
- [x] 3-layer dedup (title + URL + embedding cosine > 0.92) (2026-04-13)
- [x] Priority scoring — top 15 stories per run for deep analysis (2026-04-13)
- [x] Smart article selection (one per source, balanced alignments) (2026-04-13)
- [x] Quality post-processing (final LLM review of top stories) (2026-04-13)
- [x] Analyst model + AnalystTake model + extraction pipeline (2026-04-13)
- [x] Aggregator link extraction from Telegram (2026-04-13)
- [x] /insights/loaded-words API endpoint (2026-04-13)
- [x] /stories/{id}/article-positions PCA endpoint (2026-04-13)
- [x] /admin/create-tables + /admin/cleanup-unrelated endpoints (2026-04-13)
- [x] NarrativeMap PCA scatter plot (API-driven) (2026-04-13)
- [x] WordsOfWeek API integration (was hardcoded) (2026-04-13)
- [x] Battle of Numbers dynamic data (2026-04-13)
- [x] Pipeline expanded to 31 steps (was ~26) (2026-04-13)
