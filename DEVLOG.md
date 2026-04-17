# Doornegar Development Log

## 2026-04-17 — Audit, security fixes, 4-group narrative taxonomy, pipeline hardening, two new sources

### Key outcomes

- **Full wide-shallow audit across 8 dimensions** — security, infra, backend code quality, data pipeline, frontend, UX, data quality, tech debt. Report at `project-management/AUDIT_2026-04.md`. 36 findings total, tiered Blocker/Risk/Nice-to-have.
- **Security pass** — removed the hardcoded `doornegar2026` client-side password from 5 dashboard pages; gated `POST /api/v1/social/channels` with `require_admin`; tightened `.gitignore` to block every `.env*` variant with one glob (allowlisting `.env.example`); deleted `backend/.env.backup` and `frontend/.env.vercel` after verifying neither was in git history.
- **Pipeline hardening moved to `auto_maintenance.py`** — initial round of Celery time_limit + Redis locks was architecturally misplaced (Celery workers aren't actually running in the Railway deployment; only `web` + a daily cron). Removed the dead Celery decorators and ported the protection to the real execution path: per-step `asyncio.wait_for` timeout (budgets per step, 15 min default, up to 60 min for bias scoring), Redis SET NX EX lock (4h TTL, fails open if Redis is unreachable), a new `--mode ingest` flag that runs a 6-step lightweight subset for a 2-3 hour cron between daily runs. Auto-seeds new sources from `seed.py` on every ingest.
- **New ingest-cron service on Railway** (`0 */6 * * *` UTC). Paired with the daily full run at 04:00 UTC; the single-flight lock coordinates them. First run verified — produced 33 new articles + 570 Telegram posts from 47 channels.
- **4-subgroup narrative taxonomy shipped in 3 commits.** Split from «محافظه‌کار / اپوزیسیون» (2 sides by state vs diaspora) to «درون‌مرزی / برون‌مرزی» (2 sides by geography) × «اصول‌گرا / اصلاح‌طلب / میانه‌رو / رادیکال» (4 subgroups). No schema migration — derived from existing `production_location` × `factional_alignment`. Helper `backend/app/services/narrative_groups.py` + `counts_to_percentages` (largest-remainder rounding). Frontend `lib/narrativeGroups.ts` with colors (navy family inside, orange family outside). Story-level LLM prompt rewritten to tag each article by subgroup and emit structured bullets (`narrative.inside.principlist` etc.) instead of free-prose summaries. Backwards compat: legacy `state_summary_fa` / `diaspora_summary_fa` synthesized by joining bullets.
- **Clustering & silence-detection partition switched** from `state_alignment` to `narrative_group` (commit 3 of the taxonomy rollout). User-visible behavior change: Etemad-Online and other inside-reformist sources now correctly count as `covered_by_state` (inside-border) instead of being lumped with diaspora.
- **Two new sources added**: HRANA («هرانا», human-rights news agency, diaspora-moderate) and Etemad Online («اعتماد آنلاین», domestic reformist — slug intentionally `etemad-online` to avoid collision with an existing broken `etemad` source using a non-functional RSS URL).
- **Admin `is_active` toggle** on the Fetch Stats dashboard (both Sources and Channels tabs). Lets Parham deactivate geo-blocked feeds (tabnak, khabar-online, ilna, irna, mashregh-news, etc. — all covered via Telegram channels anyway) without touching SQL. Extended the existing `PATCH /sources/{slug}` endpoint to allow `is_active` and added `Depends(require_admin)` (it was previously ungated — small security fix bundled in). New `PATCH /channels/{channel_id}` for the channel side.
- **Auto-detach misclustered articles** replaces the old "auto-flag for human review" behavior. `step_flag_unrelated_articles` now directly sets `story_id = NULL` for articles with cosine similarity < 0.25 to their story centroid; the next clustering run re-places them. Step also deletes any residual `device_info='maintenance-bot'` rows from `improvement_feedback` on every run. `GET /improvements/admin` defaults to `include_bot=false` so the rater-submitted todo list stops getting polluted.
- **Bias scoring determinism fix** — `_call_openai` temperature was 0.3 despite the prompt explicitly promising deterministic output. Changed to 0.
- **Ingest resilience** — `ingest_all_sources` now wraps each source in its own try/except. One bad feed no longer aborts the run.
- **Silent exception handlers logged** — replaced `except: pass` with `logger.warning(...)` in `social_posting._load_posted`, `story_analysis` Telegram-context enrichment, `stories._increment_view_count`, `admin._get_maintenance_info`.
- **Telegram analysis cache TTL + admin invalidate endpoint.** Cache is 48h; `?force_refresh=1` query param bypasses for admins; `POST /social/stories/{id}/telegram-analysis/invalidate` clears a single story's cache. `cached_at` timestamp stored inside the JSONB (no schema change).
- **Aged-orphan counter.** Clustering step returns `aged_orphans` count (articles with `story_id=NULL` and `ingested_at` > 30 days) + logs a WARN. Visible to ops; doesn't auto-clean.
- **Blindspot logic** improved: 10% minority threshold → 20%, plus a small-cluster rule for stories with fewer than 6 articles (a lone voice against ≥2 is a blindspot regardless of percentage).
- **CI workflow** at `.github/workflows/ci.yml` runs frontend `tsc --noEmit` + backend `compileall` + import smoke + `pytest tests/` on every PR/push to main. 59 tests green (32 new for narrative_groups, 16 for blindspot, 11 for route registration + Persian normalization).
- **Fetch Stats admin dashboard** shipped — per-source and per-channel totals/24h/7d/freshness with click-to-drill-down (last 30 articles or posts). `/dashboard/fetch-stats` + 3 new backend endpoints. Linked from main dashboard.
- **Run Maintenance progress modal rebuilt** — minimize-to-corner pill, readable step stats ("33 new · 25 sources · 15 errors"), phase grouping (Data / Cluster / Analysis / Ops), summary metric cards instead of raw JSON dump on completion, prominent failed-steps banner during run.
- **CoverageBar 4-group UI** — 4 stacked segments with a 2px divider between sides; subgroup percentages now rendered as share-of-side (76% / 24%) instead of share-of-total (34% / 11%). Navy family for inside, orange family for outside. Fixed an invisible-bar bug where a wrapper flex div was collapsing segment widths.
- **i18n plan saved** at `project-management/I18N_PLAN.md` — three-tier rollout for EN + FR support with full RTL↔LTR layout flip. Tier 1 = UI chrome (~1-2 days), Tier 2 = story content (~1-2 weeks + ongoing LLM cost), Tier 3 = French native-speaker polish. Includes physical→logical Tailwind class mapping, before/after diagrams for the column swaps on story detail + homepage hero, and 30 anticipated complications (bidi content, font metrics, backend error-string leaks, LLM vocabulary decks per language, SEO hreflang, flag-icon UX, etc.).

### Infra changes
- **CORS_ORIGINS** on Railway — removed stale `frontend-tau-six-36.vercel.app`.
- **R2 spend cap** on OpenAI dashboard — hard monthly cap set.
- **Cloudflare Bot Fight Mode** — on (WAF ruleset deferred, paid tier).
- **UptimeRobot monitor** on `/health` — added.
- **Dashboard hardcoded password rip** across 5 pages (main, edit-stories, suggestions, improvements, architecture). Single token-validation flow in the main dashboard page; sub-pages read token from localStorage and redirect to main for login.

### RISK_REGISTER updates
- R2 (OpenAI cost cap) — mitigated.
- R14, R18 (Cloudflare Bot Fight + WAF) — mitigated (WAF deferred, paid tier).
- R19 (outage detection) — mitigated via UptimeRobot.
- R21 (Railway 502) — marked mitigated (stale from 2026-04-10; site is live).

### Open items for next session
- **R7 — Automated daily backup** script (pg_dump to Cloudflare R2 weekly, ~45 min).
- **R6 — Credential rotation playbook** (Parham drives; I draft the exact commands per service).
- **i18n Tier 1** when Parham gives the go-ahead.
- **B2 backend test suite Pass 2** — add pipeline integration tests with LLM mocks; currently Pass 1 (unit tests only) is shipping in CI.
- **Header nav re-enabling** — currently commented out; awaiting product decision from the audit.
- **Retire the dashboard-cosmetic-password localStorage key** (`doornegar_admin`) in a follow-up cleanup once the token-only flow has run for a week.

---

## 2026-04-17 (afternoon/evening session) — Niloofar removal-as-endpoint, bias-comparison depth, force-resummarize hardening, animation fixes

### Key outcomes

- **Niloofar endpoint removed from the admin API.** `/admin/niloofar/audit` and `/admin/niloofar/apply-fix` were routing to the legacy OpenAI path (`journalist_audit.py --llm`), which contradicted the intended workflow (Claude-in-chat only). Endpoint + the purple "Run Audit" dashboard card are gone; Niloofar now lives as a sixth card in the Claude Persona Audits grid with a "How to Run" hint, symmetric with Dariush/Sara/Kamran/Mina/Reza. `step_niloofar_editorial` (separate nightly step that writes `editorial_context_fa` with the nano model) preserved.
- **Niloofar persona language split** documented in `.claude/agents/niloofar.md`. Converses with Parham in English (plans, findings, reasoning) — writes Farsi into the DB (titles, summaries, bias comparisons, subgroup bullets). Same rule applied to the other five personas.
- **Bias-comparison depth scaling.** `story_analysis.py` prompt now scales bullet count with article count: 5-7 for <10 articles, 7-9 for 10-30, 8-10 for 30-60, 9-12 for 60+. Explicit anti-redundancy rule ("no two bullets may restate the same observation") with concrete failure-mode examples. New bullet patterns added (subgroup-internal differences, source-credibility contrasts). Niloofar persona mirrors the same targets for her `update_narratives` edits.
- **`update_narratives` fix_type extended** to accept `new_inside_principlist` / `new_inside_reformist` / `new_outside_moderate` / `new_outside_radical` — 2-3 Farsi bullets per subgroup. Legacy flat `state_summary_fa` / `diaspora_summary_fa` auto-synthesized from the subgroup bullets so the old fallback UI still renders. Tested on 3 stories (Islamabad talks, Hormuz blockade, Lebanon 2055) with all four subgroup slots populated.
- **Niloofar pass 1**: 11 edits applied (8 rename_story + 2 update_narratives + 1 update_summary) — fixed meta-titles adopting state framing, generic bias templates with fabricated diaspora quotes, wrong Jalali year (۱۴۰۲ → dropped), unsupported "۱۰۰ کشته" figure in Hezbollah siege.
- **Niloofar pass 2**: 3 deep rewrites on the worst is_edited stories — Islamabad talks (119 articles, 2 bullets → 9 bullets + 4 subgroup lists), Hormuz blockade (6 bullets with redundancy → 7 redundancy-free bullets + 4 subgroup lists), Lebanon 2055 (5 bullets → 8 bullets + 3 subgroup lists).
- **force-resummarize hardened in three steps.** (a) Now filters `is_edited=False` so curated stories stay untouched; (b) writes the new `narrative`/`dispute_score`/`loaded_words`/`narrative_arc`/`source_neutrality` fields; (c) refactored to fire-and-forget: background `asyncio.create_task` with shared state module `force_resummarize_state.py`, `GET /admin/force-resummarize/status` for polling. Dashboard progress bar now shows real processed/total counts, the current story title, ETA that converges after the first story. On page refresh the dashboard auto-attaches to any job already running on the server.
- **Durable failure logs + content cap.** Background job now writes a row to `maintenance_logs` on completion with per-story status/error_type/error_message (survives Railway redeploy). Per-article content cap dropped from 6000 to 3000 chars — 36-article clusters were blowing past token budgets and silently returning truncated JSON. Cost drops ~30-40% on input tokens too.
- **`step_niloofar_editorial` expanded** from top 15 to top 30. Context coverage was only ~6% of all stories; now ~11%, spans the homepage-visible slice most nights. Extra cost ~$0.10/night.
- **Niloofar title rule — no meta-framing.** New section in the persona doc bans phrases like «روایت‌های متفاوت رسانه‌ها», «پوشش یک‌سویه», «تحلیل سوگیری», «جنگ روانی» in titles. The platform's whole purpose is narrative comparison — the title shouldn't duplicate what the coverage bar and bias tab already show. When a cluster is genuinely one-sided, attribute to the source («پرس‌تی‌وی گزارش داد…») rather than label it «یک‌سویه». The story_analysis.py prompt equivalent rule is queued (holding to avoid another mid-run Railway redeploy).
- **Progress UI polish**: new "Reopen progress window" button on the Last Maintenance card (attaches to in-flight server-side runs after a page refresh); elapsed timer + phase hint on the Niloofar card (since removed); progress bar for Refresh 5 / Refresh 16 with auto-attach to running jobs.
- **Animation fix**: two-triangle Hourglass and Star figures in the footer's `DoornegarAnimation` were rendering as stacked up-triangles instead of apex-to-apex hourglass / interlocking Star of David. Added a `triangleDown` shape type and flipped the top triangle in both figures.
- **Homepage trim**: `TelegramDiscussions` right-rail card now shows top-2 predictions instead of top-3.
- **Daily freshness rotation**: hero / blindspot / Telegram-summary slots now rotate every 24h unless new articles arrive. Stateless `isFresh(story)` filter based on `last_updated_at` (already set by clustering when an article joins). Hero picker uses a 4-step fallback (fresh+balanced → fresh → balanced → top trending) so it never goes empty; blindspot slots render empty rather than re-surfacing yesterday's story; Telegram source pool prefers fresh stories with a "≥3 fresh" guard to keep the panel populated on quiet news days. `StoryBrief` schema + TS type gained `last_updated_at`.

### Commits (in order)
0e94bb3 · 96a5a99 · d3ba87a · 030b76c · 0ba518b · 656aa9e · 879b7ea · 40e73c5 · 5ffe35c · d4e1575 · 15d7b61 · 5e3d5b3 · dce2f86 · 743b903 (docs) · b74ec4c (rotation)

### Observations / known issues
- **Railway auto-deploys on any push to `main`** (not path-filtered). My frontend-only pushes keep killing in-flight background tasks on the backend. Needs a Railway-dashboard config change — path filter to `backend/**` only. Parham-driven.
- **Refresh 16 this session: 6/16 success, 9 failed.** Successes all ≤9 articles; failures likely the 36+ article clusters hitting context limits. Content cap (3000 chars) + persistent logs are the immediate fix; the next run will tell us whether the big-cluster failures are resolved.
- **4 pass-1 titles still violate the new no-meta-framing rule** ("پوشش یک‌سویه", "روایتی یک‌سویه", "روایت‌های حکومتی و برون‌مرزی"). Cleanup pass queued.

### Open items for next session
- **Story-analysis prompt tightening** for the no-meta-framing title rule (queued — pushing requires Railway redeploy).
- **Fix 4 pass-1 titles** that still have meta-framing per the new rule.
- **Railway watch-paths config** — backend-only redeploys. Parham dashboard task.
- **Retry-on-failure with exponential backoff** for the force-resummarize background job (one retry after 5s would catch rate-limit transients).
- **Small failure-log viewer** on the dashboard (currently `/admin/maintenance/logs` returns the new rows but there's no pretty UI).
- All prior open items from the morning entry still stand (R7 backup, R6 rotation, i18n Tier 1, B2 Pass 2).

---

## 2026-04-15 / 16 — Niloofar persona, performance optimization, bug fix sweep (P1–P7)

### Key outcomes
- **Niloofar writing style** defined via writing samples analysis → `.claude/agents/niloofar.md` + `~/.claude/output-styles/farsi-niloofar.md`. Iterated from literary-memoir (Khorramshahi-style) → analytical-essayist (Ashouri-style) → data-oriented copy-editor. Final principle: "edit and improve, don't replace."
- **Niloofar workflow: Claude-driven, no OpenAI.** `journalist_audit.py` restructured into gather (JSON dump) + apply-from (findings file). Claude reads the JSON in-conversation, writes findings, applies. Legacy `--llm` flag still available but not default.
- **Full Niloofar audit** (P7): 6 merges (Islamabad talks: 4 duplicates → 1 hub with 121 articles; Strait blockade: 3 → 1 hub with 18 articles), 3 title rewrites, «شهید» → «کشته» for editorial neutrality, Press TV meta-story hidden.
- **Homepage performance: 9.9s → 3.0s** (3.3× faster). Root cause: 4-stage sequential SSR waterfall. Fix: parallelized fetch stages + moved WeeklyDigest/WordsOfWeek to server-side props (0 client API calls).
- **`next/image` migration** — SafeImage rewritten on `next/image` fill mode with AVIF/WebP, responsive srcset, priority preload for hero. ~5-10× fewer image bytes on mobile.
- **Batch analyses endpoint** — `GET /stories/analyses?ids=a,b,c` replaces ~30 parallel round trips with 1.
- **Revalidate TTLs** bumped: trending 30→300s, analyses 60/120→600s.
- **Mobile homepage restructured** — hero now shows both-side bias comparison + telegram predictions/claims (matching desktop). Section order: hero → telegram → blindspot → most visited → last days → today's words.
- **Mobile story detail restructured** — narratives → telegram → narrative development → stats → articles. Desktop sidebar hidden on mobile, StatsPanel rendered inline.
- **P1: Hero selection** now prefers balanced stories (state_pct ≥5% AND diaspora_pct ≥5%). Telegram analysis centroid validation fixed (float*None crash).
- **P2: Image fallback** — source logo used when no article has an image.
- **P4/P5: Prompt fixes** — cross-narrative comparisons require same-subject validation; key_claims now subject-tagged.
- **P6: Weekly Brief** subsections wrapped in bordered containers.
- **Trending filter** — excludes stale stories (score <0.5) and blindspots from the feed.
- **3 new sources/channels**: HRA-News (RSS), @ettelaatonline, @kayhan_online. 1 new analyst: @Naghal_bashi.
- **`update_image` fix** — was a silent no-op for months (Story ORM has no image_url column). Now stores manual override in `summary_en` JSON blob.
- **`is_edited` guards** added to `step_story_quality` and `step_quality_postprocess` — prevents nightly pipeline from clobbering hand-edited titles/narratives.
- **Telegram CDN URLs blacklisted** in image scorer (auth tokens expire → 404 covers).
- **Playwright verify script** committed at `frontend/verify_homepage.mjs`.

### Domain & infrastructure (late April 16 / early April 17)
- **Purchased `doornegar.org`** from Namecheap (~€6.50/year, Domain Privacy free, auto-renew). Registered under Parham's name until IID is incorporated.
- **Cloudflare free tier** set up: DNS hosting, CDN, DDoS protection, Bot Fight Mode enabled, SSL Full mode.
- DNS records: `doornegar.org` → CNAME to Vercel (proxied), `www` → same, `api` → CNAME to Railway (proxied via Worker).
- **Cloudflare Worker `api-proxy`** created to route `api.doornegar.org/*` → `doornegar-production.up.railway.app` with host header rewrite. Bypasses Railway's custom domain limit (free plan) entirely.
- **Vercel custom domain** added: `doornegar.org` and `www.doornegar.org` both resolve to the frontend.
- **CORS updated** on Railway to allow `doornegar.org` and `www.doornegar.org`.
- **SSR data fetching** kept direct to Railway (`NEXT_PUBLIC_API_URL=https://doornegar-production.up.railway.app`) for reliability — the Worker route adds latency and isn't needed for server-side rendering.
- **ISR revalidate windows bumped**: trending 30min, analyses/telegram/story detail 1 hour. Most users now hit Vercel's static CDN cache (0ms compute, ~20ms TTFB).
- Old URLs (`frontend-tau-six-36.vercel.app`, `doornegar-production.up.railway.app`) still work as fallbacks.

### Open items for next session
- Weekly Brief story links (needs backend change: niloofar_weekly.py to emit story IDs)
- Latin → Farsi digit consistency in some story titles
- Further Niloofar audit refinement after observing the data-oriented principle in practice
- Transfer domain/accounts to IID once nonprofit is registered
- Reconnect GitHub → Vercel auto-deploy hook

---

## 2026-04-14 / 15 — Editor dashboard, mobile stories iteration, maintenance pipeline recovery

### Key outcomes

**Story editor dashboard (`/fa/dashboard/edit-stories`)**
- New `is_edited` column on the `stories` table (alembic `e9f7a3d5c8b1`) protects hand-edits from nightly regeneration.
- `PATCH /api/v1/admin/stories/{id}` now accepts `title_fa`, `title_en`, `state_summary_fa`, `diaspora_summary_fa`, `bias_explanation_fa`. Narrative fields are merged into the JSON blob stored in `stories.summary_en`.
- Clustering + force-summarize both skip stories where `is_edited=true`.
- Dashboard page lists top 15/30/50/100/200 trending stories, has Persian-insensitive search (handles ی/ي, ک/ك, zero-width joiners), one-click save per story, amber "ویرایش دستی" badge on edited rows.
- Force-summarize endpoint returns 409 Conflict on edited stories to prevent accidental overwrites.

**Maintenance pipeline recovery**
- `maintenance_logs` INSERT was silently failing with `NotNullViolationError` on the `id` column (no DB default, INSERT omitted id). Only 1 row had ever persisted since the feature was added. Fix: explicit `uuid.uuid4()` in both success + error paths.
- `telegram_link` step was crashing with `unsupported operand type(s) for *: 'float' and 'NoneType'` whenever a Story's `centroid_embedding` contained null values or was in an unexpected shape. Fix: validate centroids before use and wrap `cosine_similarity` in try/except.
- `merge_similar_visible_stories` was crashing on `db.delete(victim)` because `telegram_posts.story_id` still pointed at the victim. Fix: re-point `TelegramPost.story_id` to the keeper before delete.
- Fixed `GET /api/v1/stories/{story_id}` returning 500 with `MissingGreenlet: greenlet_spawn has not been called` — moved the `view_count` bump into a FastAPI `BackgroundTasks` running in a fresh session after the response is built.

**Telegram on Railway (StringSession)**
- Added `telethon>=1.36` to `requirements.txt` — it was previously only in `[project.optional-dependencies].social` but the Docker build only reads `requirements.txt`, so Railway never had it installed.
- New `telegram_session_string` setting → uses Telethon `StringSession` when set, falls back to file-based `doornegar_session.session` locally.
- All three Telethon entry points updated: `telegram_service.py`, `social_posting.py`, `auto_maintenance.py`.
- New helper `backend/scripts/export_telegram_session.py` converts the local file session to a `StringSession` blob.
- Generated the session string from Parham's authorized local session (353 chars) and set it on both `doornegar` and `maintenance-cron` services.
- Triggered a manual maintenance run: **fetched 363 new telegram posts in 30 minutes** from the Railway container. Latest post timestamp `2026-04-15 06:36:42 UTC`. Previously last fetch was `2026-04-13 07:08 UTC` (2 days ago, when Parham last ran it locally).
- Iran-hosted Telegram channels work via Telegram API even though their RSS feeds are geoblocked — Telegram is now the more reliable pipeline for those outlets.

**RSS feed audit and cleanup**
- 17 feeds were reporting "failing" in `source_health`. Probed each:
  - **Updated URLs (3)**: `press-tv` `/RSS → /rss.xml`, `ilna` `/fa/rss → /rss`, `entekhab` `/fa/rss → /fa/rss/allnews`.
  - **Deactivated (4)**: `fars-news` (removed public RSS), `dw-persian` (discontinued Farsi RSS), `radio-zamaneh` (Cloudflare Access auth), `isna` (Cloudflare challenge). All soft-deleted via `is_active=false` — preserves existing articles and relationships.
  - **Iran-hosted geoblocked (7)**: `khabaronline`, `tasnimnews`, `mehrnews`, `mashreghnews`, `nournews`, `iribnews`, `etemadnewspaper`. Railway US IP can't reach them. Still fetched via Telegram.
  - **Working but reported as failing (3)**: `radio-farda`, `voa-farsi`, `tabnak` — return valid XML on probe. Probably transient network on Railway. Watch after new telemetry.
- Source count: **27 → 23 active**.

**Mobile stories carousel — full 13-step build under `/stories-beta`**
- Instagram-style 6-slot (later 7 with a desktop-preview iframe slot) looping horizontal carousel, drilldown via tap/swipe.
- 4 layout types: Story, Telegram, Blindspot, MaxDisagreement, plus DesktopPreview.
- Built StoryBackground (video + image fallback), StoryLayout (State A hero title → State B sticky), StoryContentPanel (bias + narratives + telegram + sources), SplitScreen base, BlindspotLayout, MaxDisagreementLayout, TelegramLayout, StoryDetailOverlay, OnboardingHints.
- Real data wiring via `src/lib/stories-data.ts` using trending + blindspots + analysis + telegram endpoints. Source names come from `/api/v1/articles?story_id=X` joined with `/api/v1/sources`.
- Iterated on design per feedback: title mix-blend-difference, scroll behavior with dead zone and snap, content panel transparency, percentages overlay on image, darker violet borders for MaxDisagreement, text-over-images for cards, seen-stories tracking, view-count pings, swipe fixes for mouse drag and trackpad wheel, Chrome devtools support, animated swipe-up arrow.
- **Parked**: reverted `/fa` mobile to the original `MobileHome()` scrolling list. Carousel lives at `/fa/stories-beta` for continued iteration.

**Suggest-source page simplified** (`/fa/suggest`)
- Removed the category grouping (محافظه‌کار / نیمه‌محافظه‌کار / مستقل / اپوزیسیون). Now a single flat list under "رسانه‌ها" and "کانال‌های تلگرام". Shortened intro.

**Deploy pipeline notes**
- GitHub → Vercel auto-deploy hook appears disconnected (14h stale). Been triggering production deploys manually via `cd frontend && vercel deploy --prod --yes`. Worth reconnecting in the Vercel project settings.
- A previous session left a phantom alembic revision `da6408183397` stamped in production. No file for it exists in git history (checked reflog, stashes, dangling objects, deployed commits). Schema was unchanged. Recovered by directly updating `alembic_version` to `d8e5f1a2b3c4` before applying the new migration. Added a permanent note to `CLAUDE.md` and persistent memory: commit alembic files to git BEFORE running `upgrade head` on production.

### Open items for next session
- Reconnect GitHub → Vercel auto-deploy integration.
- Investigate `source_health` false positives (radio-farda, voa, tabnak showing failing but returning valid XML).
- Consider removing Iran-hosted RSS feeds entirely since their Telegram channels cover the same content.
- Continue mobile stories carousel iteration at `/stories-beta` when ready.
- Rotate exposed credentials before launch (R2, Neon, Upstash, Anthropic).

---

## 2026-04-13 — Intelligence layer, two-pass analysis, cost optimization mega-session

### Key outcomes

1. **Two-pass analysis (nano fact extraction → premium framing analysis)**:
   - Pass 1: `gpt-4.1-nano` extracts structured facts from each article (~$0.001/story) via `FACT_EXTRACTION_PROMPT`
   - Pass 2: premium model (`gpt-5-mini`) receives pre-extracted facts + context for deep framing/bias analysis
   - Result: better quality at lower cost — nano handles the grunt work, premium focuses on interpretation

2. **Cross-story memory**:
   - When summarizing a story, finds up to 3 related stories (centroid cosine > 0.5) and injects their summaries as context
   - LLM can reference broader narrative trends and avoid repeating what's already been analyzed

3. **Source track records**:
   - Historical reliability/bias patterns per source injected into analysis prompt
   - Conservative sources flagged for tendency to exaggerate achievements, opposition sources for emphasis on repression
   - Stored per-source alignment labels in Persian for prompt injection

4. **Five intelligence features**:
   - **Silence detection** (`step_detect_silences`): finds stories covered by 3+ sources on one side with 0 on the other; generates LLM hypothesis for top 5 silences explaining why one side is silent
   - **Coordinated messaging** (`step_detect_coordination`): detects 3+ articles from different sources in same alignment group with cosine > 0.85 published within 6 hours — flags as coordinated; stored in `summary_en` JSON under `"coordinated_messaging"`
   - **Narrative arc tracking**: LLM generates `narrative_arc` field showing how a story evolved over time, stored in story extras
   - **What-changed delta**: old summary saved before re-analysis; `delta` field captures only new information since last analysis (avoids repetition in re-summarized stories)
   - **Prediction verification** (`step_verify_predictions`): checks past analyst predictions against current events, marks as verified/falsified with notes

5. **Cost optimizations**:
   - **Embedding dedup** (cosine > 0.92): 3rd layer of dedup catches paraphrased reposts within 48h window
   - **3-layer dedup** (`step_deduplicate_articles`): title match → URL match → embedding similarity
   - **Priority scoring**: `_analysis_priority()` ranks stories by diversity/coverage/recency; only top 15 get deep analysis per run (`MAX_STORIES_PER_RUN = 15`)
   - **Smart article selection**: one per source, balanced across alignments, longest content preferred — instead of just "most recent"
   - **Visible-only bias scoring**: reduced `MAX_PER_RUN` from 150 to 100 with priority scoring to save cost
   - **Summary throttle**: 15 stories/run cap, skips low-priority candidates

6. **Quality post-processing** (`step_quality_postprocess`):
   - Final LLM review of top 15 stories after all other steps complete
   - Catches inconsistencies, missing data, and quality issues in generated summaries

7. **Analyst model + AnalystTake model + extraction pipeline**:
   - `Analyst` model: name (en/fa), slug, platform presence (Telegram, Twitter, website), political leaning, location (inside/outside Iran), affiliation, focus areas, bio, imprisonment status
   - `AnalystTake` model: extracted insights from analyst Telegram posts — linked to analyst, story, and telegram_post; classified by type (prediction, reasoning, insider_signal, fact_check, historical_parallel, commentary) and confidence direction (bullish/bearish/neutral); verification fields filled later
   - `step_extract_analyst_takes`: LLM pipeline extracts structured takes from Telegram posts

8. **Aggregator link extraction from Telegram**:
   - `extract_articles_from_aggregators()` in telegram_service.py — pulls URLs from aggregator channels and creates article records from linked pages

9. **New API endpoints**:
   - `GET /stories/insights/loaded-words` — aggregate loaded/charged words across top trending stories for "Words of the Week" section
   - `GET /stories/{id}/article-positions` — PCA-reduced 2D coordinates for each article in a story (for scatter plot visualization)
   - `POST /admin/create-tables` — create new DB tables without running full Alembic migration
   - `POST /admin/cleanup-unrelated` — remove unrelated articles from stories

10. **Frontend updates**:
    - **NarrativeMap** (`components/home/NarrativeMap.tsx`): PCA scatter plot visualization — fetches article positions from API, plots dots colored by alignment (conservative/opposition/independent) with hover tooltips
    - **WordsOfWeek** (`components/home/WordsOfWeek.tsx`): now API-driven — fetches from `/insights/loaded-words`, falls back to hardcoded data if API unavailable; toggle between conservative and opposition vocabulary
    - **Battle of Numbers**: dynamic data from story analysis instead of hardcoded

11. **Pipeline now 31 steps** (was ~26):
    ```
    ingest → process → backfill_farsi_titles → cluster → centroids → merge_similar →
    summarize → bias_score → fix_images → story_quality → detect_silences →
    detect_coordination → source_health → archive_stale → recalc_trending →
    dedup_articles → fixes → flag_unrelated → image_relevance → analyst_takes →
    verify_predictions → rater_feedback → feedback_health → telegram_health →
    visual → uptime → disk → cost_tracking → backup → quality_postprocess →
    weekly_digest → update_docs
    ```

### Key decisions
- D032: Two-pass analysis — nano for fact extraction, premium for framing
- D033: Cross-story memory via centroid similarity (threshold 0.5)
- D034: Source track records injected into analysis prompt
- D035: Silence detection with LLM-generated hypotheses (top 5 only)
- D036: Coordinated messaging detection (cosine > 0.85 within 6h window)
- D037: 3-layer dedup (title + URL + embedding cosine > 0.92)
- D038: Priority scoring caps deep analysis at 15 stories/run
- D039: Analyst model for tracking Iranian political commentators
- D040: AnalystTake extraction pipeline from Telegram

### Lessons learned
- **Two-pass analysis is both cheaper and better.** Nano extracts facts for ~$0.001; premium model gets clean structured input instead of raw messy articles. Quality goes up, cost goes down.
- **Cross-story memory prevents analytical amnesia.** Without context from related stories, the LLM analyzes each story in isolation and misses how narratives connect.
- **Silence detection is more revealing than bias scoring.** What media chooses NOT to cover tells you more about their agenda than how they cover it.
- **Coordinated messaging detection needs tight time windows.** 6 hours is enough to catch synchronized coverage campaigns without false-flagging stories that naturally get covered by multiple outlets.
- **3-layer dedup catches different duplication patterns.** Title match catches exact reposts, URL match catches cross-posted articles, embedding similarity catches paraphrased content.
- **Priority scoring over brute-force is the right cost strategy.** Spending premium on 15 high-value stories beats spending baseline on 150 low-value ones.

### New models
- `analysts` table: Iranian political analysts/commentators with classification metadata
- `analyst_takes` table: LLM-extracted structured insights from analyst Telegram posts

### Files changed (summary)
```
backend/app/models/analyst.py              # NEW: Analyst model (name, leaning, location, bio)
backend/app/models/analyst_take.py         # NEW: AnalystTake model (extracted insights)
backend/app/services/story_analysis.py     # Two-pass analysis, FACT_EXTRACTION_PROMPT, cross-story memory, source track records, delta
backend/app/services/telegram_service.py   # extract_articles_from_aggregators()
backend/app/api/v1/stories.py             # /insights/loaded-words, /{id}/article-positions endpoints
backend/app/api/v1/admin.py               # /create-tables, /cleanup-unrelated endpoints
backend/auto_maintenance.py               # step_detect_silences, step_detect_coordination, step_quality_postprocess, step_verify_predictions, step_extract_analyst_takes, 3-layer dedup, priority scoring, smart article selection, cross-story memory, source track records
frontend/src/components/home/NarrativeMap.tsx  # PCA scatter plot (API-driven article positions)
frontend/src/components/home/WordsOfWeek.tsx   # API-driven loaded words (was hardcoded)
frontend/src/app/[locale]/page.tsx         # Battle of numbers now dynamic
```

---

## 2026-04-12 — Major homepage & story detail redesign session

### Key outcomes

1. **Homepage redesign (BBC-style)**:
   - BBC-style top section with featured story prominence
   - Weekly briefing card (خلاصه هفتگی)
   - Most disputed stories section (بیشترین اختلاف)
   - Battle of numbers section (نبرد اعداد) — contrasting statistics across outlets
   - Narrative map (نقشه روایت‌ها) — visual display of competing narratives
   - Words of the week (واژه‌های هفته) — trending terminology across media

2. **Story detail page redesign**:
   - Tabbed analysis interface for organized content exploration
   - Political spectrum visualization
   - Stats panel with key metrics

3. **Label changes (Persian terminology)**:
   - حکومتی → محافظه‌کار (Government → Conservative)
   - برون‌مرزی → اپوزیسیون (Diaspora → Opposition)
   - نقاط کور → نگاه یک‌طرفه (Blind spots → One-sided view)

4. **Quality audit system**:
   - Daily 5-check audit cycle
   - Neon query optimization for audit performance

5. **Auto-merge similar stories**: Automatic detection and merging of duplicate/highly-similar story clusters

6. **Title auto-update from LLM**: Story titles refreshed by LLM when new articles change the story's scope

7. **Trending diversity reranking**: Exponential decay function ensures source diversity in trending results — prevents single-outlet domination

8. **Source logos**: Added logos for all 18 tracked outlets

9. **Source neutrality scoring**: Per-source neutrality metric derived from bias scoring history

10. **Telegram embed image fallback**: Graceful fallback when Telegram embed images are unavailable

11. **New admin endpoints**:
    - `PATCH /admin/stories/{id}` — edit story metadata
    - `PATCH /admin/articles/{id}` — edit article metadata
    - `PATCH /admin/sources/{id}` — edit source metadata

### Key decisions
- D026: BBC-style homepage layout replacing hero card design
- D027: Persian label renaming for political neutrality (محافظه‌کار/اپوزیسیون/نگاه یک‌طرفه)
- D028: Daily quality audit system (5 checks/day)
- D029: Auto-merge similar stories
- D030: Exponential decay for trending diversity reranking
- D031: Source neutrality scoring from bias history

### Lessons learned
- **Label choices matter politically.** "حکومتی" (governmental) and "برون‌مرزی" (diaspora) carry loaded connotations. "محافظه‌کار" (conservative) and "اپوزیسیون" (opposition) are more neutral descriptors.
- **"Blind spots" framing was too dramatic.** "نگاه یک‌طرفه" (one-sided view) is factual without implying conspiracy.
- **Trending lists dominated by high-volume outlets.** Exponential decay reranking ensures diversity without completely ignoring article volume.

### Files changed (summary)
```
frontend/src/app/[locale]/page.tsx              # BBC-style homepage with new sections
frontend/src/app/[locale]/stories/[id]/page.tsx # Tabbed analysis, political spectrum, stats panel
frontend/src/components/WeeklyBriefing.tsx      # Weekly briefing card
frontend/src/components/MostDisputed.tsx        # Most disputed stories
frontend/src/components/BattleOfNumbers.tsx     # Contrasting statistics
frontend/src/components/NarrativeMap.tsx        # Narrative map visualization
frontend/src/components/WordsOfWeek.tsx         # Trending terminology
frontend/src/lib/types.ts                       # Updated labels/types
backend/app/api/v1/admin.py                     # PATCH endpoints for stories, articles, sources
backend/app/services/clustering.py              # Auto-merge similar stories
backend/app/services/story_analysis.py          # Title auto-update from LLM
backend/app/services/trending.py                # Exponential decay diversity reranking
backend/app/services/source_scoring.py          # Source neutrality scoring
backend/auto_maintenance.py                     # Quality audit system (5 daily checks)
frontend/public/logos/                          # Source logos for 18 outlets
```

---

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
