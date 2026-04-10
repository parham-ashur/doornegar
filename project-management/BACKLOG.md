# Doornegar - Backlog

**Last updated**: 2026-04-10

## Must Have (before public launch)

### Immediate (blocks launch)
- [ ] **Set R2 env vars on Railway** (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL) — backend is 502 without these
- [ ] **Set SECRET_KEY and ADMIN_TOKEN on Railway** (generate random 32+ char strings)
- [ ] **Set OpenAI hard spending limit** ($30/month) on platform.openai.com/usage
- [ ] **Rotate exposed R2 API token** (shared in chat) after deployment works
- [ ] Rotate Neon DB password, Upstash Redis password, Anthropic API key (shared in chat previously)

### Security & Operations
- [ ] **Cloudflare CDN/WAF in front of Railway** — single biggest security win
  - Requires a custom domain (~$10/year)
  - Gives: DDoS protection, bot detection, WAF, rate limiting at edge, analytics
  - See RUNBOOK for setup steps
- [ ] **UptimeRobot monitoring** — free, pings /health every 5 min, emails on outage
- [ ] **Railway max-instance limit** — prevent runaway scaling costs
- [ ] Celery workers for automated pipeline (currently manual)
- [ ] Automated daily database backup (Neon → local/S3)
- [ ] Sentry error tracking (free tier)

### Content
- [ ] Bias scoring for all articles (currently only partial coverage)
- [ ] Content review of LLM-generated summaries (spot-check for accuracy)
- [ ] Add more Iranian media sources (geo-blocked ones via proxy)

## Should Have

### UX Improvements
- [ ] Test thoroughly on actual mobile device
- [ ] Search functionality (full-text search)
- [ ] Pagination or infinite scroll on story lists
- [ ] Story detail: timeline of when each outlet published
- [ ] Improve LLM clustering precision (avoid merging unrelated events)

### Phase 4 Prep (Rating System)
- [ ] Create first admin rater account
- [ ] Email-based invite system for new raters
- [ ] Rating UI polish

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
