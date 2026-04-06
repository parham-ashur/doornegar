# Doornegar Development Log

## 2026-04-06 — Project Kickoff

### Phase 1: Core Infrastructure (Complete)

**What was built:**

1. **Project structure** — Full monorepo with `backend/` (FastAPI) and `frontend/` (Next.js) directories, Docker Compose for PostgreSQL+pgvector, Redis, backend, Celery worker/beat, and frontend services.

2. **Database models** (7 tables):
   - `sources` — 10 Iranian news outlets with state_alignment, irgc_affiliated, factional_alignment, production_location
   - `articles` — Ingested articles with pgvector embeddings (384-dim), keywords, named entities
   - `stories` — Article clusters with blind spot detection, coverage diversity scores, trending
   - `bias_scores` — LLM-generated per-article bias analysis (political alignment, framing, tone, factuality)
   - `users` — Accounts with rater level and Bayesian reliability scores
   - `community_ratings` — Crowd ratings with blind rating support
   - `ingestion_log` — Feed fetch tracking

3. **RSS ingestion service** — Async fetcher using httpx + feedparser + trafilatura. Supports all 10 MVP sources. Deduplicates by URL. Runs every 15 minutes via Celery beat.

4. **API endpoints** — Sources CRUD, articles listing with pagination, stories with trending/blindspots, admin triggers for pipeline steps.

5. **Seed data** — All 10 sources pre-configured:
   - Diaspora: BBC Persian, Iran International, IranWire, Radio Zamaneh, DW Persian
   - State: Tasnim (IRGC), Press TV, Fars News (IRGC)
   - Semi-state: Mehr News, ISNA

6. **Utilities** — Persian text normalization (Arabic→Persian char mapping), Jalali date conversion, management CLI.

**Files created:** 47

---

### Phase 2: AI/NLP Pipeline (Complete)

**What was built:**

1. **Persian NLP module** (`app/nlp/persian.py`):
   - Text normalization via hazm library (with fallback)
   - Sentence/word tokenization
   - Lemmatization
   - Keyword extraction with Persian stopword filtering
   - Text preparation for embedding generation

2. **Embedding service** (`app/nlp/embeddings.py`):
   - Uses `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
   - Cross-lingual: Persian and English articles produce comparable embeddings
   - Batch processing with lazy model loading
   - Cosine similarity utilities for clustering

3. **Story clustering** (`app/services/clustering.py`):
   - Connected-component clustering on cosine similarity graph (threshold: 0.7)
   - Merges new articles into existing stories (threshold: 0.75)
   - Computes coverage flags: covered_by_state, covered_by_diaspora
   - Blind spot detection: stories only covered by one side
   - Coverage diversity scoring (0-1)
   - Trending score with 72-hour time decay

4. **LLM bias scoring** (`app/services/bias_scoring.py`):
   - Structured prompt with Iranian-context guidelines
   - Scores: political_alignment (-1 to +1), framing labels (15 Iranian-specific frames), tone, emotional language, factuality, source citations
   - Supports both Anthropic (Claude) and OpenAI (GPT) backends
   - JSON parsing with validation and clamping
   - Confidence estimation
   - Bilingual reasoning (EN + FA) for transparency

5. **Translation service** (`app/services/translation.py`):
   - Self-hosted Helsinki-NLP opus-mt models (free)
   - FA→EN and EN→FA title translation
   - Batch translation support
   - Graceful fallback if models not installed

6. **NLP orchestration** (`app/services/nlp_pipeline.py`):
   - Full pipeline: normalize → content extract → keywords → embed → translate
   - Processes articles in batches of 50
   - Marks articles as processed to avoid re-processing

7. **Celery tasks + beat schedule**:
   - `ingest_all_feeds_task` — every 15 min
   - `process_nlp_batch_task` — every 15 min
   - `cluster_stories_task` — every 30 min
   - `score_bias_batch_task` — every 60 min

8. **Admin API** (`app/api/v1/admin.py`):
   - Manual triggers for each pipeline step
   - `/admin/pipeline/run-all` — runs everything in sequence
   - Ingestion log viewer

**Files created/modified:** 10

---

### In Progress: Social Media Integration + Phase 3

- Adding Telegram public channel tracking
- Linking social posts to news stories
- Sentiment analysis on social discussion
- Narrative spread tracking

---

## Architecture Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Embedding model | multilingual-MiniLM (384d) | Cross-lingual clustering, smaller than ParsBERT |
| Clustering | Cosine similarity + connected components | Simple, tunable, good for small scale |
| LLM for bias | Claude Haiku / GPT-4o-mini | Cost-effective (~$75-100/mo) |
| Translation | Helsinki-NLP opus-mt (self-hosted) | Free, decent quality for titles |
| Task queue | Celery + Redis | Battle-tested, periodic scheduling |
| Database | PostgreSQL + pgvector | Single DB for relational + vector search |
| Auth | JWT + bcrypt | Simple, stateless |

## Cost Estimate (Monthly)

| Item | Cost |
|------|------|
| Hetzner VPS (CX31) | $15 |
| LLM bias scoring | $75-100 |
| Translation models | $0 (self-hosted) |
| Domain + Cloudflare | ~$1 |
| **Total** | **~$90-120** |

---

## 2026-04-06 — Social Media Integration

### Telegram Integration (Complete)

**What was built:**

1. **Data models** (`app/models/social.py`, 3 tables):
   - `telegram_channels` — Tracked public channels with political_leaning, channel_type, subscriber count
   - `telegram_posts` — Individual posts with text, views, forwards, reply counts, extracted URLs, sentiment, keywords
   - `social_sentiment_snapshots` — Periodic aggregate sentiment per story (total posts, views, avg sentiment, framing distribution, narrative divergence)

2. **Telegram service** (`app/services/telegram_service.py`):
   - Uses Telethon library (Telegram API client)
   - Fetches posts from public channels
   - Extracts URLs and matches them to known news articles → links posts to stories
   - URL normalization for reliable matching
   - `link_unlinked_posts()` — retro-links posts when new articles arrive
   - `compute_story_social_sentiment()` — aggregates sentiment snapshots

3. **API endpoints** (`app/api/v1/social.py`):
   - `GET /social/channels` — list tracked channels
   - `POST /social/channels` — add a channel
   - `GET /social/stories/{id}/social` — get Telegram posts + sentiment for a story
   - `GET /social/stories/{id}/sentiment/history` — sentiment timeline

4. **Celery tasks** (`app/workers/social_task.py`):
   - `ingest_telegram_task` — every 30 min
   - `link_posts_task` — every 30 min
   - `compute_sentiment_task` — every 60 min

5. **Seed data** — 6 initial Telegram channels (BBC Persian, Iran International, Tasnim, Fars, IranWire, Radio Zamaneh)

6. **Management CLI** — `python manage.py telegram`, `python manage.py status`

**How it works:**
```
Telegram Channels → Fetch posts → Extract URLs → Match to articles → Link to stories
                                                                          ↓
                                                              Sentiment snapshots
                                                              (positive/negative/neutral)
                                                              Framing distribution
                                                              Narrative divergence
```

**Key insight:** By linking Telegram posts to news stories, users can see not just how outlets cover a story, but how the public reacts — which frames get amplified, whether social media sentiment aligns with or diverges from media framing.

### Also created:
- **CLAUDE.md** — Project guide for Claude with conventions, setup, API reference
- **DEVLOG.md** — This file, tracking all development progress
