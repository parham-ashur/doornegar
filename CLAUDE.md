# Doornegar (دورنگر) — Iranian Media Transparency Platform

## Project Overview

Doornegar is a free, bilingual (Persian/English) media transparency platform for Iranian news — similar to Ground News but tailored for the Iranian media landscape. It aggregates articles from ~12 outlets (state, diaspora, independent), groups them by story, and reveals bias, framing differences, blind spots, and social media reactions using AI-assisted analysis and community validation.

**Owner**: Parham (non-developer, relies on Claude for all technical implementation)
**Stack**: Python 3.12 / FastAPI / SQLAlchemy 2 / Celery+Redis / PostgreSQL+pgvector / Next.js 14 / Tailwind CSS

## Directory Structure

```
doornegar/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/             # REST API endpoints
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic (ingestion, clustering, bias scoring, social)
│   │   ├── nlp/                # Persian NLP, embeddings, text processing
│   │   ├── workers/            # Celery async tasks
│   │   └── utils/              # Persian text utils, date conversion
│   ├── alembic/                # Database migrations
│   ├── tests/                  # pytest test suite
│   └── manage.py               # CLI management commands
├── frontend/                   # Next.js bilingual frontend (Phase 3)
└── docker-compose.yml          # PostgreSQL, Redis, backend, workers
```

## Key Conventions

- **Async everywhere**: All DB operations use async SQLAlchemy + asyncpg
- **Persian text**: Always normalize with `app.nlp.persian.normalize()` before storage
- **Bilingual fields**: Models use `title_fa` / `title_en`, `description_fa` / `description_en`
- **UUID primary keys**: All models use UUID, not auto-increment integers
- **JSONB for lists**: Keywords, framing labels, entities stored as PostgreSQL JSONB
- **Embeddings**: 384-dim vectors from `paraphrase-multilingual-MiniLM-L12-v2`, stored in pgvector
- **Iranian media axes**: state_alignment (state/semi_state/independent/diaspora), irgc_affiliated, factional_alignment, production_location

## Running the Project

```bash
# Start infrastructure
cd doornegar && docker compose up -d db redis

# Install backend
cd backend && pip install -e ".[dev,nlp,llm]"

# Setup database
alembic revision --autogenerate -m "initial"
alembic upgrade head

# Seed sources
python manage.py seed

# Run the API
uvicorn app.main:app --reload

# Run the full pipeline (ingest → NLP → cluster → score)
python manage.py pipeline

# Or run individual steps
python manage.py ingest
python manage.py process
python manage.py cluster
python manage.py score
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /health | Health check |
| GET | /api/v1/sources | List all news sources |
| GET | /api/v1/sources/{slug} | Source detail |
| GET | /api/v1/articles | List articles (paginated) |
| GET | /api/v1/stories | List stories (paginated) |
| GET | /api/v1/stories/trending | Top trending stories |
| GET | /api/v1/stories/blindspots | Stories with one-sided coverage |
| GET | /api/v1/stories/{id} | Story detail with articles + bias |
| POST | /api/v1/admin/pipeline/run-all | Run full pipeline manually |
| POST | /api/v1/admin/ingest/trigger | Trigger RSS ingestion |
| POST | /api/v1/admin/nlp/trigger | Trigger NLP processing |
| POST | /api/v1/admin/cluster/trigger | Trigger story clustering |
| POST | /api/v1/admin/bias/trigger | Trigger bias scoring |
| GET | /api/v1/social/channels | List tracked Telegram channels |
| POST | /api/v1/social/channels | Add a Telegram channel to track |
| GET | /api/v1/social/stories/{id}/social | Telegram posts linked to a story |
| GET | /api/v1/social/stories/{id}/sentiment/history | Sentiment over time for a story |

## Data Pipeline Flow

```
RSS Feeds → Ingest → NLP (normalize, embed, translate) → Cluster into Stories → LLM Bias Score
                                                                    ↑
                                                    Telegram channels → Social posts linked to stories
```

## LLM Usage

- **Bias scoring**: Claude Haiku or GPT-4o-mini analyzes each article for political alignment, framing, tone, factuality
- **Prompt**: Located in `app/services/bias_scoring.py` — BIAS_ANALYSIS_PROMPT
- **Cost**: ~$75-100/month for 100 articles/day
- Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`

## Important Notes for Claude

- Parham is NOT a developer — provide simple instructions, explain what things do
- Always run full pipeline after schema changes: `alembic revision --autogenerate && alembic upgrade head`
- Test RSS feeds before adding: some Iranian state sites geo-block or go offline
- Persian text MUST be normalized before any comparison or storage
- The project uses UTC timestamps; Jalali conversion is frontend/display only

## Mobile Stories Experience

### Goal
Mobile-first stories interface (Instagram Stories / TikTok style) for the existing platform. 4 layout types in a 6-slot looping horizontal carousel. Bilingual: Farsi (RTL) + English (LTR).

### Pre-Build Audit
Before writing ANY code, audit the existing project:
1. List framework, router, folder structure
2. Identify CSS/styling approach
3. Find existing component patterns and naming conventions
4. Find existing TypeScript types for stories, telegram data, sources
5. Check if Farsi fonts (Vazirmatn, IRANSans, Shabnam) are loaded
6. Check for existing RTL/LTR handling
7. Check for swipe/gesture libraries in package.json
Adapt ALL new code to match existing conventions.

### Build Order
Sequential. Each step testable before moving on.
 1. Carousel shell         → 6 empty slots, swipe, loop. TEST: swipe all 6, wraps.
 2. StoryBackground        → video autoplay + image fallback. TEST: both paths.
 3. StoryLayout State A    → fixed bg + hero title. TEST: renders mock story.
 4. StickyTitle transition  → scroll-driven A→B. TEST: title shrinks on scroll.
 5. Content panel          → sections beneath sticky title. TEST: full page scrolls.
 6. SplitScreen base       → reusable two-half component. TEST: mock data renders.
 7. BlindspotLayout        → SplitScreen + two stories. TEST: both halves correct.
 8. MaxDisagreementLayout  → SplitScreen + one story + "در مقابل". TEST: renders.
 9. TelegramLayout         → dark bg, two sections, badges. TEST: predictions + claims.
10. StoryDetail + drilldown → tap from 2/3/4 → State B, swipe nav. TEST: full flow.
11. RTL/LTR pass           → all layouts both directions. Fix issues.
12. OnboardingHints        → overlay, localStorage. TEST: shows once, gone forever.
13. Polish                 → transitions, blur, video loading, typography, viewports.

### iOS Safari Gotchas
- Video: `playsinline` REQUIRED for autoplay. Without it → fullscreen player.
- Video: iOS reclaims memory off-screen. Consider clearing `src` when not visible.
- `position: fixed`: may need `will-change: transform` or separate fixed div.
- `backdrop-filter`: needs `-webkit-backdrop-filter` prefix.
- `100vh` wrong on iOS. Use `100dvh`.
- `animation-timeline: scroll()`: limited support. Fallback to JS + rAF.
