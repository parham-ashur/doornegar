# Doornegar - Backlog

**Last updated**: April 7, 2026

## Must Have (MVP)

These items are needed for a functional, reliable production system:

- [ ] Run full pipeline on production database (Neon has old/stale data)
- [ ] Set up Celery workers for automated pipeline scheduling (currently manual)
- [ ] Fix truncated DATABASE_URL and REDIS_URL in production .env
- [ ] Add more Iranian media sources (geo-blocked ones via proxy)
- [ ] Bias scoring for all articles (currently only 86/1094 scored -- ~8% coverage)
- [ ] Ensure pipeline runs automatically every 15-30 minutes
- [ ] Production error handling (graceful failures, retries for RSS timeouts)
- [ ] Rate limiting on public API endpoints
- [ ] Admin authentication for pipeline trigger endpoints

## Should Have

These improve quality and usability significantly:

- [ ] Cloud image storage (Vercel Blob or S3) instead of local files
- [ ] Auto-translate all English titles to Farsi
- [ ] Improve LLM clustering precision (avoid merging unrelated events)
- [ ] Email-based rater invitation system (Phase 4 prep)
- [ ] Mobile-responsive refinements
- [ ] Search functionality (full-text search across articles/stories)
- [ ] Pagination improvements (infinite scroll or load-more)
- [ ] Story detail page: show timeline of when each outlet published
- [ ] Source reliability scores (based on historical accuracy)
- [ ] Article deduplication (some RSS feeds publish duplicates)

## Nice to Have

These are enhancements for future phases:

- [ ] Live Telegram channel monitoring (real-time updates via WebSocket)
- [ ] Push notifications for breaking news
- [ ] Public API documentation (Swagger/OpenAPI auto-generated)
- [ ] Analytics dashboard (cost tracking, usage metrics, pipeline stats)
- [ ] Multi-language support (full English version of the site)
- [ ] Community voting on bias scores
- [ ] RSS feed for Doornegar itself (so others can subscribe)
- [ ] Export stories as PDF reports
- [ ] Comparison tool (select 2+ articles side-by-side)
- [ ] Historical trend analysis (how coverage of a topic evolves over weeks)
- [ ] Social media sharing (Open Graph images for stories)
- [ ] Dark mode toggle

## Phase 4: Private Rating System (Not Started)

This is the next major feature phase. Key decisions already made:

- Rating is **invite-only**, NOT public
- Parham personally selects trusted raters
- Raters evaluate bias scores and article analysis quality
- This helps calibrate and improve the AI bias scoring

Tasks:
- [ ] Design rater invitation flow
- [ ] Build rater authentication (email + invite code)
- [ ] Create rating UI (agree/disagree with AI bias score, add notes)
- [ ] Store ratings in database
- [ ] Dashboard showing rater activity and agreement rates
- [ ] Use rater feedback to improve bias scoring prompts

## Phase 5: OVHcloud Migration (Not Started)

See `MIGRATION_PLAN.md` for the full step-by-step plan.

- [ ] Purchase OVHcloud VPS
- [ ] Set up Docker + Nginx + SSL
- [ ] Migrate database from Neon
- [ ] Deploy all services
- [ ] Configure domain/DNS
- [ ] Set up backups and monitoring
- [ ] Decommission old cloud services

## Completed

- [x] Phase 1: Backend models, RSS ingestion, NLP pipeline
- [x] Phase 2: Story clustering, bias scoring, Telegram integration
- [x] Phase 3: Next.js bilingual frontend with RTL support
- [x] 18 news sources seeded
- [x] 15 Telegram channels configured
- [x] 1,094 articles ingested
- [x] 132 stories clustered
- [x] 132 story summaries generated (AI)
- [x] 86 bias scores generated (AI)
- [x] Image downloading service
- [x] Deployed backend to Railway
- [x] Deployed frontend to Vercel
- [x] Connected to Neon PostgreSQL and Upstash Redis
