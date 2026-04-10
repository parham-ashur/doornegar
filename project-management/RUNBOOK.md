# Doornegar - Operations Runbook

This document explains how to run, deploy, monitor, and troubleshoot the Doornegar system. Written for non-developers -- each section includes the exact commands to run.

## Table of Contents

1. [Starting the Local Development Environment](#1-starting-the-local-development-environment)
2. [Running Pipeline Steps](#2-running-pipeline-steps)
3. [Creating Rater Accounts](#3-creating-rater-accounts)
4. [Deploying to Production](#4-deploying-to-production)
5. [Monitoring the System](#5-monitoring-the-system)
6. [Troubleshooting Common Issues](#6-troubleshooting-common-issues)
7. [Adding New News Sources](#7-adding-new-news-sources)
8. [Adding New Telegram Channels](#8-adding-new-telegram-channels)
9. [Environment Variables Reference](#9-environment-variables-reference)

---

## 1. Starting the Local Development Environment

### Start everything from scratch

```bash
# 1. Start the database and Redis
cd /Users/parham/Desktop/claude_door-bin/doornegar
docker compose up -d db redis

# 2. Wait a few seconds for them to be ready, then start the backend
cd backend
uvicorn app.main:app --reload

# 3. In a NEW terminal, start the frontend
cd /Users/parham/Desktop/claude_door-bin/doornegar/frontend
npm run dev
```

After this:
- Backend API: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs
- Frontend: http://localhost:3000

### Start everything with Docker (alternative)

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar
docker compose up -d
```

This starts all services (db, redis, backend, worker, beat, frontend) at once.

### Stop everything

```bash
# Docker services
docker compose down

# Or just stop without removing:
docker compose stop
```

### Check if services are running

```bash
docker compose ps
```

---

## 2. Running Pipeline Steps

The pipeline is what fetches news, processes it, and generates analysis. You can run the whole thing or individual steps.

### Run the full pipeline

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
python manage.py pipeline
```

This runs all 6 steps in order:
1. **Ingest** -- Fetch articles from RSS feeds
2. **Process** -- Run NLP (normalize text, generate embeddings, extract keywords)
3. **Cluster** -- Group articles into stories
4. **Score** -- Run LLM bias analysis on unscored articles
5. **Telegram ingest** -- Fetch posts from tracked channels
6. **Telegram convert** -- Convert Telegram posts into articles

### Run individual steps

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend

# Just fetch new articles from RSS feeds
python manage.py ingest

# Just process unprocessed articles (NLP)
python manage.py process

# Just cluster articles into stories
python manage.py cluster

# Just run bias scoring on unscored articles
python manage.py score

# Just fetch Telegram posts
python manage.py telegram

# Generate AI summaries for stories that don't have them
python manage.py summarize

# Download article images locally
python manage.py download-images
```

### Check current data status

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
python manage.py status
```

This shows counts of sources, articles, stories, bias scores, etc.

### Seed the database (first time only)

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
python manage.py seed
```

This adds the initial 18 news sources and 15 Telegram channels.

---

## 3. Creating Rater Accounts

The private rating system (Phase 4) is not yet built. When it is ready, this section will explain:
- How to invite a trusted rater
- How to create their account
- How to manage rater access

For now, there is no user authentication system in place.

---

## 4. Deploying to Production

### Current setup: Railway + Vercel + Neon + Upstash

**Backend (Railway)**:
- Railway auto-deploys from the git repository
- Push to main branch to trigger a deploy
- Check Railway dashboard for logs and status

**Frontend (Vercel)**:
- Vercel auto-deploys from the git repository
- Push to main branch to trigger a deploy
- Check Vercel dashboard for deployment status

**Database (Neon)**:
- Managed PostgreSQL, no deployment needed
- Connection string is in the production .env

**Redis (Upstash)**:
- Managed Redis, no deployment needed
- Connection string is in the production .env

### Manual deploy commands

```bash
# Deploy backend to Railway (if not auto-deploying)
# Use the Railway CLI or push to git

# Deploy frontend to Vercel
cd /Users/parham/Desktop/claude_door-bin/doornegar/frontend
vercel deploy --prod

# Run database migrations on production
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
DATABASE_URL="your-neon-url" alembic upgrade head
```

### Future setup: OVHcloud VPS

See `MIGRATION_PLAN.md` for the complete migration procedure.

---

## 4a. Setting Up Cloudflare (edge protection)

Goal: put Cloudflare between users and Railway/Vercel for DDoS protection, bot detection, WAF, and caching.

### Prerequisites
- A custom domain (e.g. `doornegar.com`) — buy from Namecheap/Porkbun (~$10/year)
- Cloudflare account (free tier is enough)

### Steps

1. **Add site to Cloudflare**: cloudflare.com → Add a site → enter domain → Free plan
2. **Update nameservers**: Cloudflare shows 2 nameservers → set them at your registrar (Namecheap/Porkbun) → wait 5-15 min
3. **Configure DNS records in Cloudflare**:
   - Type `CNAME`, name `@` or `doornegar.com`, target `cname.vercel-dns.com`, **Proxy status: Proxied** (orange cloud ON)
   - Type `CNAME`, name `api`, target `doornegar-production.up.railway.app`, **Proxied**
4. **Add custom domain on Railway**: Railway dashboard → backend service → Settings → Domains → Add `api.doornegar.com`
5. **Add custom domain on Vercel**: Vercel dashboard → frontend project → Settings → Domains → Add `doornegar.com`
6. **Update frontend env var**: Vercel → Settings → Environment Variables → `NEXT_PUBLIC_API_URL=https://api.doornegar.com` → Redeploy

### Security settings to enable (Cloudflare dashboard)

| Setting | Location | Value |
|---------|----------|-------|
| SSL/TLS mode | SSL/TLS → Overview | **Full (strict)** |
| Always Use HTTPS | SSL/TLS → Edge Certificates | **On** |
| Bot Fight Mode | Security → Bots | **On** |
| WAF Managed Rules | Security → WAF → Managed rules | Enable **Free managed ruleset** |
| Rate limiting rule | Security → WAF → Rate limiting rules | 100 req / 1 min / IP → Challenge |
| Browser Integrity Check | Security → Settings | **On** |
| Challenge Passage | Security → Settings | 30 min |
| Security Level | Security → Settings | **Medium** |

### Emergency: "Under Attack" mode
If you notice unusual traffic or your site is being hammered:
- Cloudflare dashboard → Security → Settings → Security Level → **Under Attack**
- This shows a JS challenge page to all visitors — stops bots instantly
- Turn it back to Medium once the attack stops

---

## 4b. Setting Up UptimeRobot (outage monitoring)

Goal: get an email within 5 minutes of the site going down.

### Steps

1. Sign up at https://uptimerobot.com (free plan = 50 monitors, 5-min interval)
2. **Add first monitor**:
   - Monitor Type: HTTPS
   - Friendly Name: `Doornegar Backend`
   - URL: `https://api.doornegar.com/health` (or Railway URL if no custom domain yet)
   - Monitoring Interval: 5 minutes
   - Alert Contact: your email
   - Save
3. **Add second monitor**:
   - Monitor Type: HTTPS
   - Friendly Name: `Doornegar Frontend`
   - URL: `https://doornegar.com` (or Vercel URL)
   - Same settings
4. **Optional**: add a Telegram alert — create a bot via @BotFather, add the token to UptimeRobot alert contacts
5. **Test**: temporarily stop the backend and confirm you get an email within 5-10 min

### Expected alerts
- **Down**: backend not responding → email within 5 min
- **SSL expiring**: certificate expires in <30 days → email weekly warning
- **Up**: after a downtime, confirmation email when service recovers

---

## 4c. OpenAI Spending Protection

Goal: ensure a runaway LLM abuse cannot bankrupt the project.

### Steps

1. Log in to https://platform.openai.com
2. Go to Settings → Billing → **Limits**
3. Set **Hard limit**: $30/month (adjust based on expected usage)
4. Set **Soft limit**: $15/month (email warning)
5. Under API keys, confirm only the production key is active
6. If compromised: revoke key immediately and generate new one

### Current cost baseline (as of 2026-04-10)
- ~$0.01 per clustering run (100 articles) via GPT-4o-mini
- ~$0.005 per story summary
- ~$0.003 per bias score
- Monthly total: historically $1-5

A hard cap at $30 gives 6x safety margin while still keeping the site useful.

---

## 5. Monitoring the System

### Check if the backend is healthy

```bash
# Local
curl http://localhost:8000/health

# Production (replace with actual URL)
curl https://your-railway-url.railway.app/health
```

### Check data freshness

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
python manage.py status
```

If article counts aren't growing, the pipeline may not be running.

### View Docker logs

```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar

# All services
docker compose logs -f

# Just the backend
docker compose logs -f backend

# Just the worker (Celery)
docker compose logs -f worker

# Last 100 lines only
docker compose logs --tail=100 backend
```

### Check Railway logs

Visit the Railway dashboard and click on the backend service to see logs.

### Check Vercel logs

Visit the Vercel dashboard and click on the frontend project for deployment logs.

---

## 6. Troubleshooting Common Issues

### "Connection refused" when starting backend

**Cause**: PostgreSQL or Redis isn't running.
**Fix**:
```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar
docker compose up -d db redis
# Wait 5 seconds, then try again
```

### "relation does not exist" database error

**Cause**: Database tables haven't been created yet.
**Fix**:
```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
alembic upgrade head
```

### RSS feed returns no articles

**Cause**: The source might be geo-blocked (Iranian state sites block some IPs) or temporarily down.
**Fix**:
- Check if the feed URL is accessible: `curl -I <feed_url>`
- Some Iranian sites require a proxy -- this is a known limitation
- Try again later if the site is temporarily down

### Bias scoring fails or is slow

**Cause**: LLM API key might be missing, expired, or rate-limited.
**Fix**:
- Check that `ANTHROPIC_API_KEY` is set in `.env`
- Check your Anthropic dashboard for usage limits
- The scoring processes one article at a time to avoid rate limits

### Frontend shows no data

**Cause**: Backend might not be running, or CORS might be misconfigured.
**Fix**:
- Verify backend is running: `curl http://localhost:8000/health`
- Check that `CORS_ORIGINS` in backend `.env` includes the frontend URL
- Check browser console for error messages (right-click > Inspect > Console)

### Docker containers won't start

**Cause**: Ports might be in use, or Docker might not be running.
**Fix**:
```bash
# Check if Docker is running
docker info

# Check what's using the ports
lsof -i :5432    # PostgreSQL
lsof -i :6379    # Redis
lsof -i :8000    # Backend
lsof -i :3000    # Frontend

# Kill conflicting processes or stop other Docker containers
docker compose down
docker compose up -d
```

### "Module not found" Python errors

**Cause**: Python dependencies not installed.
**Fix**:
```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
pip install -e ".[dev,nlp,llm]"
```

### Telegram ingestion fails

**Cause**: Telegram API credentials not configured or session expired.
**Fix**:
- Check `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env`
- You may need to re-authenticate the Telegram session
- Telegram rate-limits API access -- wait and try again

---

## 7. Adding New News Sources

To add a new Iranian news source:

1. **Find the RSS feed URL** for the news source. Common patterns:
   - `https://example.com/rss`
   - `https://example.com/feed`
   - `https://example.com/fa/rss`

2. **Test if the feed is accessible**:
   ```bash
   curl -I https://example.com/rss
   ```
   If you get a 200 response, it works. If 403 or timeout, it might be geo-blocked.

3. **Add the source to the seed file**. Ask Claude to add it to:
   `/Users/parham/Desktop/claude_door-bin/doornegar/backend/app/services/seed.py`

   You'll need to provide:
   - `name_fa`: Persian name (e.g., "خبرگزاری ایرنا")
   - `name_en`: English name (e.g., "IRNA")
   - `slug`: URL-friendly name (e.g., "irna")
   - `website_url`: Main website URL
   - `rss_url`: RSS feed URL
   - `state_alignment`: one of: state, semi_state, independent, diaspora
   - `factional_alignment`: one of: principlist, reformist, moderate, independent
   - `production_location`: one of: iran, abroad
   - `irgc_affiliated`: true or false
   - `language`: "fa" or "en"

4. **Run the seed command**:
   ```bash
   cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
   python manage.py seed
   ```

5. **Run ingestion to fetch articles**:
   ```bash
   python manage.py ingest
   ```

---

## 8. Adding New Telegram Channels

To track a new Telegram channel:

### Option 1: Via API

```bash
curl -X POST http://localhost:8000/api/v1/social/channels \
  -H "Content-Type: application/json" \
  -d '{
    "username": "channel_username",
    "name_fa": "نام کانال",
    "name_en": "Channel Name",
    "channel_type": "news",
    "political_leaning": "state"
  }'
```

### Option 2: Add to seed file

Ask Claude to add the channel to:
`/Users/parham/Desktop/claude_door-bin/doornegar/backend/app/services/seed_telegram.py`

Then run:
```bash
cd /Users/parham/Desktop/claude_door-bin/doornegar/backend
python manage.py seed
```

### Fetch posts from the new channel

```bash
python manage.py telegram
```

---

## 9. Environment Variables Reference

These are set in the `.env` file at `/Users/parham/Desktop/claude_door-bin/doornegar/backend/.env`

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/doornegar` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | Secret for JWT tokens | A long random string |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | `sk-ant-api03-...` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` or `production` | `development` |
| `DEBUG` | Enable debug mode | `true` |
| `PORT` | Backend port | `8000` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |
| `OPENAI_API_KEY` | OpenAI API key (alternative to Anthropic) | empty |
| `BIAS_SCORING_MODEL` | LLM model for bias analysis | `claude-haiku-4-5-20251001` |
| `EMBEDDING_MODEL` | Sentence transformer model | `paraphrase-multilingual-MiniLM-L12-v2` |
| `CLUSTERING_SIMILARITY_THRESHOLD` | Min similarity to cluster articles | `0.45` |
| `STORY_MERGE_THRESHOLD` | Min similarity to merge stories | `0.55` |
| `TELEGRAM_API_ID` | Telegram API application ID | `0` |
| `TELEGRAM_API_HASH` | Telegram API application hash | empty |
| `TELEGRAM_FETCH_INTERVAL_MINUTES` | How often to fetch Telegram posts | `30` |
| `INGESTION_INTERVAL_MINUTES` | How often to fetch RSS feeds | `15` |
| `INGESTION_TIMEOUT_SECONDS` | Timeout for RSS requests | `30` |
| `MAX_ARTICLES_PER_FEED` | Max articles to fetch per source | `50` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token lifetime | `10080` (1 week) |

### Frontend

Set in `/Users/parham/Desktop/claude_door-bin/doornegar/frontend/.env.local`:

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |
