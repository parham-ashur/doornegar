# Doornegar - Changelog

All notable changes to the Doornegar project are documented here, organized by work session date.

---

## April 7, 2026 (Evening Session)

### Features Added
- **Editable story titles**: Raters can click a pencil icon on story titles to edit them inline. Saves via PATCH `/api/v1/admin/stories/{id}`
- **Rater feedback system**: Thumbs up/down on articles, summary rating, source categorization suggestions
- **Telegram integration**: 9 channels, 654 posts, converted to articles for clustering
- **LLM incremental clustering**: New articles match existing stories first, then cluster into new ones
- **OpenAI story analysis**: Per-side summaries (حکومتی/مستقل/برون‌مرزی), bias comparison, based on full article content
- **Pre-generated summaries**: All visible stories have cached summaries (instant load)
- **Local image storage**: Downloaded 522 images locally to prevent expired URLs
- **Rater accounts**: API for creating invite-only rater accounts with bcrypt auth
- **Auto-translation**: English article titles translated to Farsi via OpenAI

### Design
- NYTimes-style homepage: 3-column hero, 4-image row, text-only rows, varied layouts
- No rounded corners, thin borders, clean typography
- System-based dark/light mode
- All text in Farsi, RTL layout
- Summaries with "ادامه ←" on large story boxes
- One-line title truncation with ellipsis on compact sections

### Infrastructure
- Docker (PostgreSQL + Redis) running locally
- Pushed to GitHub, deployed to Railway (backend) + Vercel (frontend)
- Project management folder created with 7 standard documents

### Data
- 1,309 articles from 18 sources
- 168 stories (20+ visible with 5+ articles)
- 654 Telegram posts from 9 channels
- 106 bias scores

---

## April 7, 2026 (Initial Session)

### Project Management

- Created the `project-management/` folder with comprehensive documentation
- Added `PROJECT_STATUS.md` with current data metrics and infrastructure overview
- Added `ARCHITECTURE.md` with system diagrams, data flow, directory structure, and API reference
- Added `MIGRATION_PLAN.md` with step-by-step OVHcloud VPS migration checklist
- Added `BACKLOG.md` with prioritized remaining work (Must Have / Should Have / Nice to Have)
- Added `RUNBOOK.md` with operational procedures for running, deploying, and troubleshooting
- Added `CHANGELOG.md` (this file) for tracking changes across sessions

### System Status Snapshot

Current data in local development database:
- 18 news sources configured
- 1,094 articles ingested
- 132 stories clustered (20 with 5+ articles)
- 132 stories have AI-generated summaries
- 86 articles have bias scores (~8% coverage)
- 15 Telegram channels tracked
- 484 Telegram posts collected

---

## Prior Work (Before This Changelog)

### Phase 1 -- Backend Foundation
- Set up FastAPI backend with async SQLAlchemy
- Created data models: Source, Article, Story, BiasScore, TelegramChannel, TelegramPost
- Built RSS feed ingestion service for Iranian media outlets
- Implemented Persian text normalization (NLP pipeline)
- Set up embedding generation with sentence-transformers
- Created management CLI (`manage.py`) with pipeline commands
- Set up Docker Compose for local development (PostgreSQL + pgvector, Redis)
- Database migrations with Alembic

### Phase 2 -- Analysis Pipeline
- Built story clustering using vector similarity (pgvector)
- Implemented LLM-powered bias scoring (Claude Haiku)
- Built Telegram channel monitoring with Telethon
- Added blind spot detection (stories covered by only one media type)
- Created story summarization with per-perspective analysis
- Added image downloading service
- Seeded 18 news sources and 15 Telegram channels

### Phase 3 -- Frontend
- Built Next.js 14 bilingual frontend (Persian/English)
- Implemented RTL support with tailwindcss-rtl
- Added internationalization with next-intl
- Created story listing and detail pages
- Built bias visualization with Recharts (radar charts, bar charts)
- Implemented Jalali (Persian) date display
- Added source listing and filtering
- Deployed frontend to Vercel
- Deployed backend to Railway
- Connected to Neon PostgreSQL and Upstash Redis
