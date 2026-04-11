# Reminders & Action Items

Last updated: 2026-04-11

## 🔴 URGENT — Action items from this session

- [ ] **Click "Null localhost image URLs"** on `/fa/dashboard` → Data Repair section (one-shot, ~2,000 rows affected)
- [ ] **Click "Unclaim story articles…"** on `/fa/dashboard` → paste story ID `53f091c9-52b4-467f-8f55-3a71e9b8ae2c` (the Hormuz 209-article cluster)
- [ ] **Click "Run Maintenance"** — lets the clustering + image fixes catch up with the new rules
- [ ] **Mark improvement feedback item `4ea8d828` as done** at `/fa/dashboard/improvements`
- [ ] **Click "Refresh 30"** on the dashboard to regenerate the top-30 trending stories with the new gpt-5-mini + improved prompt (~$1-2 one-shot)
- [ ] **Set OpenAI hard spending cap** ($30/month) at https://platform.openai.com/usage → Limits
- [ ] **Rotate credentials** that were shared in chat: R2 token, Neon DB password, Upstash Redis password, Anthropic API key

## Daily Tasks
- [x] **Automatic**: Railway cron service `maintenance-cron` runs `python auto_maintenance.py` nightly
- [ ] Spot-check the homepage in the morning (is data fresh? are summaries sensible?)
- [ ] Glance at `/fa/dashboard` → Diagnostics → bias coverage % of eligible is catching up

## Weekly Tasks
- [ ] Review new stories for quality
- [ ] Run `python manage.py check-images` — confirm no missing images
- [ ] Check `python manage.py status`
- [ ] Review rater feedback: `curl http://localhost:8000/api/v1/feedback/stats`
- [ ] Update PROJECT_STATUS.md with latest metrics

## Monthly Tasks
- [ ] Review BACKLOG.md — reprioritize items
- [ ] Check LLM API costs (OpenAI + Anthropic dashboards)
- [ ] Review R2 storage usage (should stay well under 10 GB free tier)
- [ ] Review Telegram channel list — add new channels if needed
- [ ] Backup database: `pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql`
- [ ] Update CHANGELOG.md

## Upcoming Milestones

### By April 17, 2026 (1 week)
- [x] Railway backend back online
- [ ] Cloudflare proxy in front of Railway + custom domain
- [ ] UptimeRobot monitoring active
- [ ] OpenAI hard cap set
- [ ] All shared credentials rotated
- [ ] Bias coverage of eligible articles reaches ~80% (runs 9-10 will get there at 150/run cap)
- [ ] Localhost image URLs all cleaned (post-nullify + 3-4 maintenance runs of OG refetching)

### By April 30, 2026 (1 month)
- [ ] Celery workers running for automated pipeline
- [ ] 3-5 active raters recruited
- [ ] Search functionality in frontend
- [ ] Daily DB backup automated

### By June 30, 2026 (3 months)
- [ ] 500+ stories accumulated
- [ ] Public beta launch
- [ ] OVHcloud VPS evaluated (decide: stay on Railway or migrate)

## Blocked Items (need your action)

### High Priority
- **Railway env vars**: Backend is 502 until you set the R2 credentials
- **Domain name**: Decide on production domain (doornegar.com / .org / .ir) — required before Cloudflare setup
- **OpenAI spending cap**: Set immediately regardless of anything else — hard $30/month limit

### Medium Priority
- **Rater recruitment**: Identify 3-5 trusted people to invite as raters
- **Credential rotation**: R2 token, Neon password, Upstash password, Anthropic key

### Low Priority
- **OVHcloud decision**: Whether to migrate from Railway or stay put given R2 already decouples image storage
