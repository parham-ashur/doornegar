# Doornegar - Backlog

**Last updated**: 2026-04-16 (Niloofar persona + performance + P1–P7 bug sweep)

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
- [ ] **Set R2 env vars on Railway** (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL) — backend is 502 without these
- [ ] **Set SECRET_KEY and ADMIN_TOKEN on Railway** (generate random 32+ char strings)
- [ ] **Set OpenAI hard spending limit** ($30/month) on platform.openai.com/usage
- [ ] **Rotate exposed R2 API token** (shared in chat) after deployment works
- [ ] Rotate Neon DB password, Upstash Redis password, Anthropic API key (shared in chat previously)
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

## Phase 5: Cloudflare + Monitoring (Next Up)

**Goal**: Make the site resilient to attacks and get visibility into outages.

### Setup checklist
- [ ] Purchase domain (e.g. `doornegar.com`) from Namecheap / Porkbun
- [ ] Sign up for Cloudflare (free tier)
- [ ] Add domain to Cloudflare, update nameservers at registrar
- [ ] DNS records:
  - `doornegar.com` → CNAME to Vercel (proxied, orange cloud ON)
  - `api.doornegar.com` → CNAME to Railway (proxied, orange cloud ON)
- [ ] Add custom domain in Railway dashboard for backend
- [ ] Add custom domain in Vercel dashboard for frontend
- [ ] Update `NEXT_PUBLIC_API_URL=https://api.doornegar.com` in Vercel env
- [ ] Cloudflare settings:
  - SSL/TLS → Full (strict)
  - Security → Bots → Enable Bot Fight Mode
  - Security → WAF → Enable Free Managed Ruleset
  - Rules → Rate limiting → 100 req/min per IP → challenge
  - Speed → Cache → Aggressive
- [ ] UptimeRobot:
  - Create free account (uptimerobot.com)
  - Add monitor: HTTPS, `https://api.doornegar.com/health`, check every 5 min
  - Add email alert
  - Add second monitor for the frontend homepage
- [ ] Test "Under Attack" mode toggle (one-click WAF lockdown)
- [ ] Document DNS/domain credentials in a password manager

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
