# Doornegar - Project Status

**Last updated**: 2026-04-10 16:29 (auto-maintenance)

## What is Doornegar?

Doornegar (دورنگر) is a free, bilingual (Persian/English) media transparency platform for Iranian news. Think of it like Ground News, but specifically designed for the Iranian media landscape. It:

- Aggregates articles from 28 Iranian news outlets (state, diaspora, independent)
- Groups related articles into "stories" so you can see how different outlets cover the same event
- Uses AI to score each article for political bias, framing, and tone
- Tracks 16 Telegram channels (including state media that geo-block RSS)
- Scores each source on 8 media dimensions (editorial independence, factional capture, etc.)
- Shows "blind spots" — stories that only one type of outlet is covering
- Has a "lab" feature for topic-based analysis with news and debate modes

## Current State

### What works

- RSS feed ingestion from 28 news sources
- Telegram ingestion from 16 channels (covers state media that geo-block RSS)
- NLP pipeline (text normalization, embedding generation, keyword extraction)
- Story clustering via LLM (GPT-4o-mini) with incremental matching
- LLM-powered bias scoring (Claude Haiku)
- AI-generated per-perspective summaries (state vs diaspora vs independent)
- 8-dimension media scoring system per source
- **Cloudflare R2 image storage** (permanent, CDN-backed, replaces expiring Telegram URLs)
- Bilingual Next.js frontend with RTL support, Jalali dates
- Homepage redesign with hero layout, DoornegarAnimation, welcome modal
- Story detail page with interactive DimensionPlot and scrollable article list
- Lab feature (topic-based analysis, news/debate modes, analyst perspectives)
- Error/loading/404 pages with themed SVG animations
- Admin token auth on all mutation endpoints
- Rate limiting (slowapi): 200/min default, 10/hour on LLM endpoints
- Request size limits (1 MB), security headers, CORS restrictions
- Automated `fill-images` and `check-images` commands in the pipeline

### What needs work

- Cloudflare CDN/WAF not yet in front of Railway backend (biggest security win remaining)
- UptimeRobot / monitoring not configured
- Custom domain not yet purchased
- OpenAI hard spending limit not yet set
- Celery workers not yet automated in production (pipeline is manual)
- Image quality threshold might need tuning (currently 120×80)
- State media RSS feeds geo-blocked — relying on Telegram as workaround

## Data Metrics

From local development DB, April 10, 2026:

| Metric | Count |
|--------|-------|
| News sources | 28 |
| Articles ingested | ~1,300+ |
| Stories (visible, ≥2 sources) | 294 |
| Stories with AI summaries | 132 |
| Images stored in R2 | 765 |
| Telegram channels tracked | 16 |
| Media dimension scores | 28 sources × 8 dimensions |

## Infrastructure

| Service | Provider | Purpose | Status |
|---------|----------|---------|--------|
| Backend API | Railway | FastAPI server | Deployed (502 as of 2026-04-10 — needs env vars + restart) |
| PostgreSQL | Neon | Primary database with pgvector | Connected |
| Redis | Upstash | Celery task queue | Connected |
| Frontend | Vercel | Next.js web app | Deployed |
| Image storage | **Cloudflare R2** | S3-compatible object storage for article images | **Live — 765 images uploaded** |
| LLM bias scoring | Anthropic (Claude Haiku) | Article analysis | Working |
| LLM analysis/clustering | OpenAI (GPT-4o-mini) | Story summaries, clustering | Working |
| Telegram API | Telethon | 16 channels monitored | Configured |

### URLs

- **Frontend (production)**: `https://frontend-tau-six-36.vercel.app`
- **Backend API (production)**: `https://doornegar-production.up.railway.app`
- **R2 public URL**: `https://pub-65f981ecf095486aaea3482ec613d9b1.r2.dev`
- **Local frontend**: http://localhost:3000
- **Local backend**: http://localhost:8000
- **API docs**: http://localhost:8000/docs

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg, slowapi, aioboto3
- **Database**: PostgreSQL 16 with pgvector extension
- **Cache/Queue**: Redis 7
- **Frontend**: Next.js 14, React 18, Tailwind CSS, next-intl
- **NLP**: sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2), 384-dim embeddings
- **AI**: Anthropic Claude Haiku, OpenAI GPT-4o-mini
- **Object storage**: Cloudflare R2 (S3-compatible)
- **Dates**: date-fns-jalali

## Security Posture

| Layer | Protection |
|-------|-----------|
| Secrets | `.env` gitignored, all credentials via env vars |
| Admin endpoints | Token-based auth (`ADMIN_TOKEN`) |
| LLM cost abuse | Admin-only + 10/hour rate limit + `max_tokens=4096` per call |
| Request flood | slowapi: 200/min, 2000/hour default (per IP via CF-Connecting-IP) |
| Memory exhaustion | 1 MB max request body |
| CORS | Restricted to specific frontend origins |
| Headers | X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| DDoS (edge) | **Not yet — needs Cloudflare proxy in front of Railway** |
| Bot protection | **Not yet — needs Cloudflare Bot Fight Mode** |
| WAF | **Not yet — needs Cloudflare managed ruleset** |
| Uptime monitoring | **Not yet — needs UptimeRobot** |
| OpenAI hard cap | **Not yet — needs to be set in OpenAI dashboard** |

## Project Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Backend: models, ingestion, NLP pipeline | Done |
| Phase 2 | Backend: clustering, bias scoring, Telegram | Done |
| Phase 3 | Frontend: Next.js bilingual UI | Done |
| Phase 4 | Private rating system (invite-only) | Code deployed, no raters yet |
| Phase 5 | R2 image storage + security hardening | **Done (2026-04-10)** |
| Phase 6 | Cloudflare CDN/WAF + UptimeRobot + OpenAI caps | **Next** |
| Phase 7 | OVHcloud VPS migration | Not started |
