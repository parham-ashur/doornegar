# Reminders & Action Items

Last updated: 2026-04-08

## Daily Tasks (run every day)
- [ ] Run `python manage.py telegram` — fetch new Telegram posts
- [ ] Run `python manage.py ingest` — fetch new RSS articles
- [ ] Run `python manage.py process` — translate & embed new articles
- [ ] Run `python manage.py cluster` — assign articles to stories
- [ ] Check http://localhost:3001/fa — verify data is fresh

**Quick command to run everything:**
```bash
cd ~/Desktop/claude_door-bin/doornegar/backend && python manage.py pipeline
```

## Weekly Tasks
- [ ] Review new stories for quality — are titles accurate? Are clusters correct?
- [ ] Run `python manage.py summarize` — generate summaries for new stories
- [ ] Check `python manage.py status` — review system metrics
- [ ] Invite 1-2 new raters if needed
- [ ] Update PROJECT_STATUS.md with latest metrics
- [ ] Review rater feedback: `curl http://localhost:8000/api/v1/feedback/stats`

## Monthly Tasks
- [ ] Review and update BACKLOG.md — reprioritize items
- [ ] Check OpenAI API costs (https://platform.openai.com/usage)
- [ ] Review Telegram channel list — any new channels to add?
- [ ] Review source categorization — any changes needed?
- [ ] Backup database: `pg_dump doornegar > backup_$(date +%Y%m%d).sql`
- [ ] Update CHANGELOG.md with month's progress

## Upcoming Milestones

### By April 14, 2026 (1 week)
- [ ] Have 5+ active raters giving feedback
- [ ] Bias scoring on all visible stories
- [ ] Fix production database (truncated URLs in .env)
- [ ] Celery workers running for automation

### By April 30, 2026 (1 month)
- [ ] OVHcloud VPS set up and running
- [ ] Migration from Railway/Vercel/Neon complete
- [ ] 50+ visible stories with summaries
- [ ] Image storage solution (cloud or VPS-based)

### By June 30, 2026 (3 months)
- [ ] 200+ stories accumulated
- [ ] Search functionality
- [ ] Public beta launch
- [ ] 10+ active raters

## Blocked Items (need your action)
- **Fix .env URLs**: The DATABASE_URL and REDIS_URL in `backend/.env` are truncated. Get full URLs from Neon and Upstash dashboards.
- **OVHcloud access**: Need VPS credentials to start migration planning
- **Rater recruitment**: Identify 3-5 trusted people to invite as raters
- **Domain name**: Decide on production domain (doornegar.com? doornegar.ir?)
