# Doornegar - Project Status

**Last updated**: 2026-04-10 11:55 (auto-maintenance)

## What is Doornegar?

Doornegar (دورنگر) is a free, bilingual (Persian/English) media transparency platform for Iranian news. Think of it like Ground News, but specifically designed for the Iranian media landscape. It:

- Aggregates articles from ~18 Iranian news outlets (state, diaspora, independent)
- Groups related articles into "stories" so you can see how different outlets cover the same event
- Uses AI to score each article for political bias, framing, and tone
- Tracks Telegram channels to capture social media reactions
- Shows "blind spots" -- stories that only one type of outlet is covering

## Current State

### What works

- RSS feed ingestion from 18 news sources
- NLP processing pipeline (text normalization, embedding generation, keyword extraction)
- Story clustering using vector similarity (articles grouped into 132 stories)
- LLM-powered bias scoring (using Claude Haiku)
- AI-generated story summaries with per-perspective breakdowns (state vs diaspora vs independent)
- Telegram channel tracking and post ingestion
- Full bilingual Next.js frontend with RTL support
- Jalali (Persian) date display
- Story detail pages with bias visualization (radar charts, bar charts)
- Image downloading and local serving
- API with 17+ endpoints

### What needs work

- Only 86 out of 1094 articles have bias scores (need to run scoring on the rest)
- Production database (Neon) may have stale data -- need to re-run pipeline
- Celery workers not yet running in production (pipeline is manual)
- Some Iranian state news sites are geo-blocked and need proxy configuration
- No automated scheduling yet (pipeline runs manually via `python manage.py pipeline`)

## Data Metrics

These numbers are from the **local development database** as of April 7, 2026:

| Metric | Count |
|--------|-------|
| News sources | 18 |
| Articles ingested | 3,452 |
| Stories (clusters) | 432 |
| Stories with 5+ articles | 55 |
| Stories with AI summaries | 105 |
| Bias scores | 86 |
| Telegram channels tracked | 15 |
| Telegram posts collected | 2,067 |

## Infrastructure

| Service | Provider | Purpose | Status |
|---------|----------|---------|--------|
| Backend API | Railway | FastAPI server | Deployed |
| PostgreSQL | Neon | Primary database with pgvector | Connected |
| Redis | Upstash | Celery task queue, caching | Connected |
| Frontend | Vercel | Next.js web app | Deployed |
| Telegram API | Telegram | Social media monitoring | Configured (15 channels) |
| LLM (bias scoring) | Anthropic (Claude Haiku) | Article analysis | Working |
| Local Docker | Docker Compose | Development: PostgreSQL + Redis | Working |

### URLs

- **Frontend (production)**: Deployed on Vercel (check Vercel dashboard for URL)
- **Backend API (production)**: Deployed on Railway (check Railway dashboard for URL)
- **Local frontend**: http://localhost:3000
- **Local backend**: http://localhost:8000
- **API docs**: http://localhost:8000/docs (Swagger UI)

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), Celery, asyncpg
- **Database**: PostgreSQL 16 with pgvector extension
- **Cache/Queue**: Redis 7
- **Frontend**: Next.js 14, React 18, Tailwind CSS, next-intl (i18n), Radix UI
- **NLP**: sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2), 384-dim embeddings
- **AI**: Anthropic Claude Haiku for bias scoring and story summarization
- **Charts**: Recharts for bias visualization
- **Dates**: date-fns-jalali for Persian calendar

## Project Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Backend: models, ingestion, NLP pipeline | Done |
| Phase 2 | Backend: clustering, bias scoring, Telegram | Done |
| Phase 3 | Frontend: Next.js bilingual UI | Done |
| Phase 4 | Private rating system (invite-only) | Not started |
| Phase 5 | OVHcloud VPS migration | Not started |
