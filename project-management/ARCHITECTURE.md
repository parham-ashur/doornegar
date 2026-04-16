# Doornegar - System Architecture

## Component Diagram (Current + Planned)

```
                          +------------------+
                          |    Users         |
                          |  (Web Browser)   |
                          +--------+---------+
                                   |
                                   v
                   +-------------------------------+
                   |  Cloudflare (LIVE)            |
                   |  doornegar.org (free tier)    |
                   |  - DDoS protection (L3/L4/L7) |
                   |  - Bot Fight Mode             |
                   |  - SSL Full mode              |
                   |  - Global CDN (proxied CNAME) |
                   |  - Worker: api-proxy          |
                   +---------------+---------------+
                                   |
            +----------------------+------------------------+
            |                                               |
            v                                               v
  +-------------------+                      +------------------------+
  | Frontend          |                      | Backend API            |
  | Vercel            |                      | Railway (FastAPI)      |
  | doornegar.org     |                      | api.doornegar.org      |
  | Next.js 14        |                      | (via CF Worker proxy)  |
  | - Bilingual RTL   |                      | - slowapi rate limits  |
  | - next/image      |                      |   (200/min, 2000/hr)   |
  | - Tailwind        |   REST JSON          | - 1 MB req body limit  |
  | - SafeImage       | ---(SSR direct)----> | - Admin token auth     |
  | - ISR 30min/1hr   |                      | - Security headers     |
  | - DoornegarAnim   |                      | - 60+ endpoints        |
  +---------+---------+                      +--+--------+--------+---+
            |                                   |        |        |
            |                                   |        |        |
            | Image <img src>                   |        |        |
            v                                   v        v        v
  +-----------------+        +-------------+ +-------+ +-----+ +-------+
  | Cloudflare R2   |        | PostgreSQL  | | Redis | | LLM | | Tele- |
  | (S3-compatible) | <----- | 16+pgvector | |       | | APIs| | gram  |
  |                 | upload | Neon        | |Upstash| |     | | API   |
  | pub-*.r2.dev    |  765   |             | |       | |     | |       |
  | - Article imgs  | images | Articles    | |Celery | |OAI  | |16 ch. |
  | - CDN cached    |        | Stories     | | queue | |Anth.| |       |
  | - Permanent     |        | Sources     | |       | |     | |       |
  | - Cheap egress  |        | BiasScores  | |       | |     | |       |
  +-----------------+        | Topics      | |       | |     | |       |
                             | Media dims  | |       | |     | |       |
                             | Telegram    | |       | |     | |       |
                             | pgvector    | |       | |     | |       |
                             +-------------+ +-------+ +-----+ +-------+

                   +-------------------------------+
                   |  UptimeRobot (PLANNED)        |
                   |  - Pings /health every 5 min  |
                   |  - Email alerts on failure    |
                   +-------------------------------+
```

**Security defense-in-depth layers (current → planned):**

1. **Edge (Cloudflare — planned)**: DDoS, bot detection, WAF, edge rate limiting
2. **App (slowapi — done)**: 200/min default, per-endpoint overrides, 10/hour on LLM
3. **Auth (admin token — done)**: All mutation endpoints require `ADMIN_TOKEN`
4. **Cost caps (done + planned)**:
   - `max_tokens=4096` per LLM call (done)
   - 10/hour rate limit on LLM endpoints (done)
   - Hard spending cap on OpenAI dashboard (**TODO**)
5. **Data (done)**: Neon PostgreSQL, R2 for images, all secrets in env vars
6. **Monitoring (planned)**: UptimeRobot for outages, Sentry for errors

## Data Flow

```
Step 1: INGEST
  RSS Feeds (28 sources)  ──>  Articles table
  Telegram (16 channels)  ──>  TelegramPosts ──> converted to Articles

Step 2: NLP PROCESS
  Unprocessed articles ──> Persian text normalization
                       ──> Embedding generation (384-dim vectors)
                       ──> Keyword extraction
                       ──> Title translation FA ↔ EN (gpt-4.1-nano, economy tier)

Step 2b: BACKFILL FARSI TITLES (new)
  Articles where title_fa IS NULL (regardless of processed_at)
    ──> Translate up to 300/run via gpt-4.1-nano
    ──> Fixes the "stuck translation" trap where a previous run
        marked processed_at but translation actually failed

Step 3: CLUSTER (two-phase: embedding pre-filter → LLM confirmation)
  New unclustered articles (last 30 days)
    │
    ├──> Build articles block: title + source + article content
    │    (6000 chars for premium-tier stories, 400 for baseline)
    │
    ├──> PHASE 1 — Embedding pre-filter:
    │    Compute cosine similarity between article embedding and
    │    story centroid embedding. Only stories with similarity ≥ 0.30
    │    are sent to the LLM (loose threshold — LLM makes final call)
    │
    ├──> PHASE 2 — LLM confirmation:
    │    For each batch of 50 existing OPEN stories (passing pre-filter):
    │      (open = article_count < 30 AND last_updated_at within 7 days)
    │
    │    Send to gpt-5-mini with strict MATCHING_PROMPT
    │    ("REJECTION IS THE DEFAULT") + double-match guard
    │    └──> article_idx → story_idx or null
    │
    ├──> Remaining unmatched articles → _cluster_new_articles
    │    (CLUSTERING_PROMPT asks LLM to group remaining by exact event)
    │
    ├──> Merge very-similar hidden stories (MERGE_PROMPT)
    │
    ├──> _keepalive(db) pings before each LLM call (prevents Neon timeout)
    │
    └──> Update trending_score = article_count × recency_factor
         (recency decays linearly 1.0 → 0.1 over 30 days)

Step 3b: RECOMPUTE CENTROIDS
  For each story: centroid = mean(article embeddings), L2-normalized
  Stored in Story.centroid_embedding (JSONB)

Step 4: SUMMARIZE (tiered)
  Stories with summary_fa IS NULL AND article_count ≥ 5
    │
    ├──> Pre-compute top-N trending story IDs (N=16)
    │
    ├──> Load only 10 most-recent articles per story (memory-safe on 512MB)
    │
    ├──> For each story:
    │      if story.id in top_N:
    │        model = gpt-5-mini (premium — homepage visible)
    │        include_analyst_factors = true (15 analytical categories)
    │        article content = 6000 chars
    │      else:
    │        model = gpt-4o-mini (baseline — long tail)
    │        include_analyst_factors = false
    │        article content = 1500 chars
    │
    ├──> _keepalive(db) pings before each LLM call
    │
    └──> generate_story_analysis → JSON:
         summary_fa, state_summary_fa, diaspora_summary_fa,
         independent_summary_fa, bias_explanation_fa, scores,
         llm_model_used (audit trail),
         analyst: {15 factor categories} (premium only)

Step 5: BIAS SCORE
  Articles with story_id IS NOT NULL AND no existing BiasScore
    ──> Send to gpt-4o-mini with rich BIAS_ANALYSIS_PROMPT
        (~2,200-token static prefix, cache-eligible, Persian glossary,
         3 few-shot examples)
    ──> Returns: political_alignment, framing_labels, tone_score,
        factuality_score, reasoning_en, reasoning_fa
    ──> Up to 150 articles/run

Step 6: FIX IMAGES
  Pass 1: HEAD-check 300 articles/run; null out any localhost or broken URLs
          Skip articles with image_checked_at within 24h
  (Note: story image selection now happens at response time in
   _story_brief_with_extras via title-word-overlap heuristic)

Step 7..22: maintenance housekeeping
  story_quality, source_health, archive_stale, recalc_trending,
  dedup_articles, fix_issues, rater_feedback_apply, feedback_health,
  telegram_health, visual_check, uptime_check, disk_monitoring,
  cost_tracking, backup, weekly_digest, docs update

Step 23: SERVE
  Frontend requests ──> API endpoints ──> JSON ──> UI rendering
  Dashboard polls /admin/maintenance/status every 3s for live progress
```

## LLM 3-tier strategy

| Task | Model | Tier | Cost/month |
|---|---|---|---|
| Headline translation | `gpt-4.1-nano` | Economy | ~$0.40 |
| Bias scoring (all articles) | `gpt-4o-mini` | Baseline | ~$4-5 |
| Story analysis (long-tail) | `gpt-4o-mini` | Baseline | ~$1-2 |
| Story analysis (top-16 trending + analyst factors) | `gpt-5-mini` | Premium | ~$2-4 |
| Clustering (embedding pre-filter → LLM confirm) | `gpt-5-mini` | Premium* | ~$0.50 |
| Embeddings (articles + centroids) | `text-embedding-3-small` | — | ~$0.05 |

*Clustering uses the premium model because it's a reasoning task (deciding whether two events are the same) and the cost is tiny.

All configured via `app/config.py` fields and overridable via env vars:
`BIAS_SCORING_MODEL`, `STORY_ANALYSIS_MODEL`, `STORY_ANALYSIS_PREMIUM_MODEL`,
`TRANSLATION_MODEL`, `CLUSTERING_MODEL`, `PREMIUM_STORY_TOP_N` (default 16).

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
| Embeddings | OpenAI text-embedding-3-small | — | 384-dim article + centroid embeddings |
| LLM | Claude Haiku | claude-haiku-4-5 | Bias scoring + summarization |
| Telegram | Telethon | latest | Channel monitoring |

## API Endpoints

### Public endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/sources` | List all 24 news sources |
| GET | `/api/v1/sources/{slug}` | Single source details |
| GET | `/api/v1/articles` | List articles (paginated, filterable) |
| GET | `/api/v1/stories` | List stories (paginated) |
| GET | `/api/v1/stories/trending` | Top trending stories (filters: score >0.5, not blindspot) |
| GET | `/api/v1/stories/blindspots` | Stories with one-sided coverage |
| GET | `/api/v1/stories/analyses?ids=a,b,c` | Batch-fetch story analyses (up to 60, replaces N parallel calls) |
| GET | `/api/v1/stories/{id}` | Story detail with all articles + bias |
| GET | `/api/v1/stories/{id}/analysis` | Single story analysis (cached in summary_en JSON blob) |
| GET | `/api/v1/stories/weekly-digest` | Latest weekly editorial digest |
| GET | `/api/v1/stories/insights/loaded-words` | Aggregated loaded vocabulary across trending stories |
| GET | `/api/v1/social/stories/{id}/telegram-analysis` | Deep Telegram discourse analysis (two-pass) |

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
