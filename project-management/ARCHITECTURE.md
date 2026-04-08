# Doornegar - System Architecture

## Component Diagram

```
                          +------------------+
                          |    Users         |
                          |  (Web Browser)   |
                          +--------+---------+
                                   |
                                   v
                    +-----------------------------+
                    |     Frontend (Next.js 14)   |
                    |     Vercel / localhost:3000  |
                    |  - Bilingual (FA/EN)        |
                    |  - RTL support              |
                    |  - Radix UI + Tailwind      |
                    |  - Recharts (bias charts)   |
                    +-------------+---------------+
                                  |
                                  | REST API calls
                                  v
                    +-----------------------------+
                    |    Backend (FastAPI)         |
                    |    Railway / localhost:8000  |
                    |  - REST API (17+ endpoints) |
                    |  - Async SQLAlchemy          |
                    |  - Pydantic schemas          |
                    +--+--------+--------+--------+
                       |        |        |
            +----------+    +---+---+    +----------+
            |               |       |               |
            v               v       v               v
  +-----------------+ +----------+ +----------+ +------------------+
  | PostgreSQL 16   | | Redis 7  | | Anthropic| | Telegram API     |
  | Neon / Docker   | | Upstash  | | Claude   | | (Telethon)       |
  |                 | | / Docker | | Haiku    | |                  |
  | - Articles      | |          | |          | | - 15 channels    |
  | - Stories       | | - Celery | | - Bias   | | - Post ingestion |
  | - Sources       | |   queue  | |   scoring| | - Sentiment      |
  | - Bias scores   | | - Cache  | | - Story  | |   analysis       |
  | - Telegram      | |          | |   summary| |                  |
  | - pgvector      | |          | |          | |                  |
  |   (embeddings)  | |          | |          | |                  |
  +-----------------+ +----------+ +----------+ +------------------+
```

## Data Flow

```
Step 1: INGEST
  RSS Feeds (18 sources)  ──>  Articles table
  Telegram (15 channels)  ──>  TelegramPosts table ──> converted to Articles

Step 2: NLP PROCESS
  Raw articles ──> Persian text normalization
                ──> Embedding generation (384-dim vectors)
                ──> Keyword extraction
                ──> Title translation (FA <-> EN)

Step 3: CLUSTER
  Processed articles ──> Vector similarity comparison (threshold: 0.45)
                     ──> Group into Stories
                     ──> Merge similar stories (threshold: 0.55)
                     ──> Detect blind spots (one-sided coverage)

Step 4: BIAS SCORE
  Articles ──> Send to Claude Haiku with analysis prompt
           ──> Returns: political alignment, framing, tone, factuality
           ──> Stored as BiasScore records

Step 5: SUMMARIZE
  Stories (with articles) ──> Send to Claude Haiku
                          ──> Returns: summary_fa, per-perspective summaries
                          ──> State perspective / Diaspora perspective / Independent perspective
                          ──> Bias explanation

Step 6: SERVE
  Frontend requests ──> API endpoints ──> JSON responses ──> UI rendering
```

## Directory Structure

```
doornegar/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app setup, CORS, routes
│   │   ├── config.py               # Settings (env vars, defaults)
│   │   ├── database.py             # Async SQLAlchemy engine + session
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── sources.py      # /api/v1/sources endpoints
│   │   │       ├── articles.py     # /api/v1/articles endpoints
│   │   │       ├── stories.py      # /api/v1/stories endpoints
│   │   │       ├── admin.py        # /api/v1/admin pipeline triggers
│   │   │       └── social.py       # /api/v1/social Telegram endpoints
│   │   ├── models/
│   │   │   ├── source.py           # NewsSource model (18 outlets)
│   │   │   ├── article.py          # Article model (1094 articles)
│   │   │   ├── story.py            # Story model (132 clusters)
│   │   │   ├── bias_score.py       # BiasScore model (86 scores)
│   │   │   └── social.py           # TelegramChannel + TelegramPost
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── ingestion.py        # RSS feed fetching
│   │   │   ├── nlp_pipeline.py     # Text processing, embeddings
│   │   │   ├── clustering.py       # Story grouping (vector similarity)
│   │   │   ├── bias_scoring.py     # LLM bias analysis
│   │   │   ├── story_analysis.py   # LLM story summarization
│   │   │   ├── telegram_service.py # Telegram channel monitoring
│   │   │   ├── image_downloader.py # Article image caching
│   │   │   ├── seed.py             # Initial source data
│   │   │   └── seed_telegram.py    # Initial Telegram channel data
│   │   ├── nlp/
│   │   │   └── persian.py          # Persian text normalization
│   │   ├── workers/
│   │   │   └── celery_app.py       # Celery worker configuration
│   │   └── utils/                  # Date conversion, text helpers
│   ├── alembic/                    # Database migration scripts
│   ├── tests/                      # pytest test suite
│   ├── manage.py                   # CLI: seed, ingest, process, cluster, score, etc.
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router pages
│   │   ├── components/             # React components
│   │   └── lib/                    # Utilities, API client
│   ├── messages/                   # i18n translation files (fa.json, en.json)
│   ├── public/                     # Static assets
│   ├── package.json
│   ├── tailwind.config.ts
│   └── next.config.js
├── project-management/             # This folder
├── docker-compose.yml              # Local dev: PostgreSQL + Redis + backend + frontend
└── CLAUDE.md                       # Project instructions for Claude
```

## Key Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Backend framework | FastAPI | latest | REST API server |
| Python | Python | 3.12 | Backend language |
| ORM | SQLAlchemy | 2.x | Async database access |
| DB driver | asyncpg | latest | PostgreSQL async driver |
| Database | PostgreSQL | 16 | Primary data store |
| Vector search | pgvector | latest | Embedding similarity search |
| Task queue | Celery | latest | Background job processing |
| Cache/broker | Redis | 7 | Celery broker + caching |
| Frontend framework | Next.js | 14.2 | React SSR/SSG |
| UI library | React | 18.3 | Component rendering |
| CSS | Tailwind CSS | 3.4 | Utility-first styling |
| RTL support | tailwindcss-rtl | 0.9 | Right-to-left layout |
| i18n | next-intl | 3.15 | Persian/English translations |
| UI components | Radix UI | latest | Accessible primitives |
| Charts | Recharts | 2.12 | Bias visualization |
| Icons | Lucide React | 0.380 | Icon library |
| Dates | date-fns-jalali | 3.6 | Persian (Jalali) calendar |
| Embeddings | sentence-transformers | latest | paraphrase-multilingual-MiniLM-L12-v2 |
| LLM | Claude Haiku | claude-haiku-4-5 | Bias scoring + summarization |
| Telegram | Telethon | latest | Channel monitoring |

## API Endpoints

### Public endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/sources` | List all 18 news sources |
| GET | `/api/v1/sources/{slug}` | Single source details |
| GET | `/api/v1/articles` | List articles (paginated, filterable) |
| GET | `/api/v1/stories` | List stories (paginated) |
| GET | `/api/v1/stories/trending` | Top trending stories |
| GET | `/api/v1/stories/blindspots` | Stories with one-sided coverage |
| GET | `/api/v1/stories/{id}` | Story detail with all articles + bias |

### Admin endpoints (pipeline control)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/pipeline/run-all` | Run entire pipeline |
| POST | `/api/v1/admin/ingest/trigger` | Trigger RSS ingestion only |
| POST | `/api/v1/admin/nlp/trigger` | Trigger NLP processing only |
| POST | `/api/v1/admin/cluster/trigger` | Trigger clustering only |
| POST | `/api/v1/admin/bias/trigger` | Trigger bias scoring only |

### Social/Telegram endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/social/channels` | List tracked Telegram channels |
| POST | `/api/v1/social/channels` | Add a new Telegram channel |
| GET | `/api/v1/social/stories/{id}/social` | Telegram posts for a story |
| GET | `/api/v1/social/stories/{id}/sentiment/history` | Sentiment over time |

## Database Models

### Core models (UUID primary keys, JSONB fields)

- **Source**: News outlet metadata (name_fa/en, rss_url, state_alignment, factional_alignment, etc.)
- **Article**: Individual news article (title, content, embedding vector, keywords, publication date)
- **Story**: Cluster of related articles (title, summary, article_count, is_blindspot, bias scores)
- **BiasScore**: LLM-generated bias analysis for an article (political_alignment, framing, tone, factuality)
- **TelegramChannel**: Tracked Telegram channel metadata
- **TelegramPost**: Individual Telegram post with sentiment analysis

### Iranian media classification axes

Each news source is classified on these dimensions:

- **state_alignment**: state / semi_state / independent / diaspora
- **irgc_affiliated**: boolean (affiliated with IRGC or not)
- **factional_alignment**: principlist / reformist / moderate / independent
- **production_location**: iran / abroad
