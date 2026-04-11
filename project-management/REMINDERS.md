# Reminders & Action Items

Last updated: 2026-04-11

## 🔴 URGENT — Blocking Production

- [ ] **Fix Railway 502**: Set R2 env vars on Railway dashboard so the backend can start:
  ```
  R2_ACCOUNT_ID=dc19030b9b78a70652d26ab5b8e85d85
  R2_ACCESS_KEY_ID=<rotate after setting>
  R2_SECRET_ACCESS_KEY=<rotate after setting>
  R2_BUCKET_NAME=doornegar-images
  R2_PUBLIC_URL=https://pub-65f981ecf095486aaea3482ec613d9b1.r2.dev
  SECRET_KEY=<generate with `openssl rand -hex 32`>
  ADMIN_TOKEN=<generate with `openssl rand -hex 32`>
  ENVIRONMENT=production
  ```
- [ ] **Set OpenAI hard spending cap** ($30/month) at https://platform.openai.com/usage → Limits
- [ ] **Rotate exposed R2 token** after Railway is stable — it was shared in chat
- [ ] Rotate: Neon DB password, Upstash Redis password, Anthropic API key (all shared in chat history)

## Daily Tasks (run every day)
- [ ] Run `python manage.py pipeline` — full cycle including R2 image upload
- [ ] Check http://localhost:3000/fa — verify data is fresh

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
- [ ] Railway backend back online
- [ ] Cloudflare proxy in front of Railway + custom domain
- [ ] UptimeRobot monitoring active
- [ ] OpenAI hard cap set
- [ ] All shared credentials rotated

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
