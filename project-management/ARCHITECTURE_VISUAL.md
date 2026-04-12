# Doornegar Architecture -- Visual Diagrams

This document provides visual Mermaid diagrams of the Doornegar system architecture.
Render these in any Markdown viewer that supports Mermaid (GitHub, VS Code with the Mermaid extension, Obsidian, etc.).

---

## 1. System Architecture -- High-Level Component Diagram

How the major pieces of Doornegar connect to each other.

```mermaid
graph TB
    subgraph Frontend["Frontend (Next.js 14 / Vercel)"]
        NextApp["Next.js App Router<br/>(bilingual: fa / en)"]
        Pages["Pages:<br/>Home, Stories, Sources,<br/>Blindspots, Rate, Improve,<br/>Suggest, Lab, Dashboard"]
    end

    subgraph Backend["Backend (FastAPI / Railway)"]
        API["FastAPI REST API<br/>/api/v1/*"]
        Auth["JWT Auth<br/>(invite-only raters)"]
        StaticFiles["Static Image Server<br/>/images/*"]
    end

    subgraph Workers["Background Workers"]
        AutoMaint["auto_maintenance.py<br/>(LaunchAgent, every 4h)<br/>30-step pipeline"]
        ManagePy["manage.py CLI<br/>(manual pipeline runs)"]
    end

    subgraph Data["Data Stores"]
        PG[("PostgreSQL<br/>+ pgvector<br/>(384-dim embeddings)")]
        Redis[("Redis<br/>(Celery broker,<br/>caching)")]
    end

    subgraph External["External Services"]
        RSS["30+ Iranian RSS Feeds<br/>(state, semi_state,<br/>independent, diaspora)"]
        TG["Telegram API<br/>(news + aggregator<br/>+ analyst channels)"]
        OpenAI["OpenAI 3-Tier LLM:<br/>gpt-5-mini (premium)<br/>gpt-4o-mini (baseline)<br/>gpt-4.1-nano (economy)"]
    end

    NextApp -->|"HTTP REST calls"| API
    API -->|"async SQLAlchemy"| PG
    API -->|"session cache"| Redis
    Auth -->|"JWT tokens"| API

    AutoMaint -->|"runs pipeline steps"| PG
    AutoMaint -->|"calls services"| OpenAI
    AutoMaint -->|"fetches posts"| TG
    ManagePy -->|"same pipeline"| PG

    Workers -->|"RSS fetch"| RSS
    Workers -->|"Telegram fetch"| TG
    Workers -->|"LLM calls"| OpenAI

    API -->|"serves"| StaticFiles
```

**Key points:**
- The frontend is a Next.js 14 app with bilingual routing (`/fa/...` and `/en/...`).
- The backend is a FastAPI application with fully async database operations.
- Background processing runs via `auto_maintenance.py` on a macOS LaunchAgent (every 4 hours) or manually via `manage.py`.
- PostgreSQL stores all data including 384-dimensional multilingual embeddings for article similarity.
- LLM calls use a **3-tier model strategy**: gpt-5-mini for premium analysis (top-N trending stories, clustering), gpt-4o-mini for baseline (bias scoring, long-tail stories), gpt-4.1-nano for economy tasks (translation, fact extraction).
- Estimated cost: **~$37/month at 300 articles/day**.

---

## 2. Data Pipeline Flow -- Two-Pass Analysis

The complete 30-step pipeline from news ingestion to the user's screen.

```mermaid
flowchart LR
    subgraph Ingest["Phase 1: Ingest"]
        RSS["RSS Feeds<br/>(30+ sources)"]
        TG["Telegram<br/>Channels"]
        AGG["Aggregator<br/>Channels<br/>(link extraction)"]
        Scraper["Web Scraper<br/>(full text)"]
        IngestSvc["ingestion.py<br/>+ telegram_service.py"]
    end

    subgraph NLP["Phase 2: NLP Process"]
        Normalize["Persian Text<br/>Normalization"]
        Translate["Translation<br/>(fa <-> en)<br/>gpt-4.1-nano"]
        Embed["Embeddings<br/>(MiniLM-L12-v2<br/>384-dim)"]
        EmbedDedup["Embedding<br/>Deduplication"]
        Keywords["Keyword &<br/>Entity Extraction"]
        Titles["Backfill<br/>Farsi Titles"]
    end

    subgraph Cluster["Phase 3: Cluster"]
        Cosine["Cosine Similarity<br/>+ LLM Verification<br/>(gpt-5-mini)"]
        Centroids["Recompute<br/>Story Centroids"]
        MergeSimilar["Merge Similar<br/>Visible Stories"]
    end

    subgraph Analyze["Phase 4: Two-Pass Analysis"]
        Pass1["Pass 1: Fact Extraction<br/>(gpt-4.1-nano)<br/>~$0.001/story"]
        Pass2["Pass 2: Framing Analysis<br/>(gpt-5-mini or gpt-4o-mini)<br/>facts + context → deep analysis"]
        BiasLLM["Bias Scoring<br/>(gpt-4o-mini)<br/>visible stories only"]
    end

    subgraph Intel["Phase 5: Intelligence"]
        Silence["Silence Detection<br/>(what's NOT covered)"]
        Coordination["Coordinated<br/>Messaging Detection"]
        Predictions["Verify Analyst<br/>Predictions"]
        AnalystTakes["Extract Analyst<br/>Takes from TG"]
    end

    subgraph QA["Phase 6: Quality & Serve"]
        FixImages["Fix Broken<br/>Images"]
        StoryQuality["Story Quality<br/>Checks"]
        Trending["Recalculate<br/>Trending Scores"]
        Dedup3["3-Layer<br/>Deduplication"]
        Fixes["Auto-Fix<br/>Common Issues"]
        FlagUnrelated["Flag Unrelated<br/>Articles"]
        ImageRelevance["Image Relevance<br/>Check"]
        QualityPost["Quality<br/>Post-Processing<br/>(LLM review)"]
        Digest["Weekly Digest"]
        APILayer["FastAPI<br/>REST API"]
        FrontendApp["Next.js<br/>Frontend"]
    end

    RSS --> IngestSvc
    TG --> IngestSvc
    AGG --> IngestSvc
    IngestSvc --> Scraper
    Scraper --> Normalize

    Normalize --> Translate
    Normalize --> Embed
    Embed --> EmbedDedup
    Normalize --> Keywords
    Keywords --> Titles

    EmbedDedup --> Cosine
    Cosine --> Centroids
    Centroids --> MergeSimilar

    MergeSimilar --> Pass1
    Pass1 -->|"structured facts"| Pass2
    Pass2 --> BiasLLM

    BiasLLM --> Silence
    BiasLLM --> Coordination
    BiasLLM --> AnalystTakes
    AnalystTakes --> Predictions

    Predictions --> FixImages
    FixImages --> StoryQuality
    StoryQuality --> Trending
    Trending --> Dedup3
    Dedup3 --> Fixes
    Fixes --> FlagUnrelated
    FlagUnrelated --> ImageRelevance
    ImageRelevance --> QualityPost
    QualityPost --> Digest
    Digest --> APILayer
    APILayer --> FrontendApp
```

**Two-Pass Analysis in detail:**

| Pass | Model | Cost | What It Does |
|------|-------|------|--------------|
| Pass 1 | gpt-4.1-nano | ~$0.001/story | Extracts structured facts from each article: who, what, where, numbers, claims. First 800 chars per article. |
| Pass 2 | gpt-5-mini (top 16) or gpt-4o-mini (rest) | ~$0.02-0.05/story | Receives Pass 1 facts + full articles + narrative context. Produces per-perspective analysis, bias explanation, dispute scores, loaded words, media neutrality scores. |

**Context injected into Pass 2 (no extra LLM cost):**
- Extracted facts from Pass 1
- Source metadata (alignment, faction, IRGC affiliation)
- Story priority and trending score
- Previous analysis delta (what changed)

**Full pipeline step list (30 steps + doc update):**

| # | Step | Key Service |
|---|------|-------------|
| 1 | Ingest RSS + Telegram + aggregators | `ingestion.py`, `telegram_service.py` |
| 2 | NLP process (embed, translate, extract) | `nlp_pipeline.py` |
| 3 | Backfill Farsi titles | `translation.py` |
| 4 | Cluster articles into stories | `clustering.py` |
| 5 | Recompute story centroid embeddings | centroid averaging |
| 6 | Merge similar visible stories | cosine threshold 0.55 |
| 7 | Summarize new stories (two-pass, priority top 15) | `story_analysis.py` |
| 8 | Bias scoring (visible stories only) | `bias_scoring.py` |
| 9 | Fix broken images | `image_downloader.py` |
| 10 | Story quality checks | quality heuristics |
| 11 | Silence detection | coverage gap analysis |
| 12 | Coordinated messaging detection | cross-source pattern matching |
| 13 | Source health | feed availability checks |
| 14 | Archive stale stories | age-based archiving |
| 15 | Recalculate trending scores | recency + volume + diversity |
| 16 | Deduplicate articles (3-layer) | URL + embedding + content dedup |
| 17 | Auto-fix common issues | field corrections, TG title cleanup |
| 18 | Flag unrelated articles | LLM-assisted relevance check |
| 19 | Image relevance check | image-story match scoring |
| 20 | Extract analyst takes from Telegram | `analyst_take.py` extraction |
| 21 | Verify analyst predictions | nano model claim verification |
| 22 | Apply rater feedback | `rating_aggregation.py` |
| 23 | Feedback system health | consistency checks |
| 24 | Telegram session health | connection + fetch validation |
| 25 | Visual check | rendering validation |
| 26 | Uptime check | endpoint availability |
| 27 | Disk monitoring | storage usage |
| 28 | LLM cost tracking | per-model cost logging |
| 29 | Database backup | pg_dump |
| 30 | Quality post-processing (LLM review) | nano model QA |
| 31 | Weekly digest | summary email/report |
| -- | Update project docs | `MAINTENANCE_LOG.md`, `PROJECT_STATUS.md` |

---

## 3. Database Schema -- Entity Relationship Diagram

All tables and their relationships.

```mermaid
erDiagram
    SOURCE {
        uuid id PK
        string name_en
        string name_fa
        string slug UK
        text website_url
        jsonb rss_urls
        text logo_url
        string state_alignment "state | semi_state | independent | diaspora"
        boolean irgc_affiliated
        string production_location "inside_iran | outside_iran"
        string factional_alignment "hardline | principlist | reformist | moderate | opposition | monarchist | left"
        jsonb media_dimensions "8-axis editorial scoring (1-5 each)"
        float credibility_score
        boolean is_active
    }

    ARTICLE {
        uuid id PK
        uuid source_id FK
        uuid story_id FK
        text title_original
        text title_en
        text title_fa
        text url UK
        text content_text
        text summary
        text image_url
        string language
        jsonb categories
        jsonb embedding "384-dim vector"
        jsonb keywords
        jsonb named_entities
        float sentiment_score
        timestamp published_at
        timestamp processed_at
    }

    STORY {
        uuid id PK
        text title_en
        text title_fa
        string slug UK
        text summary_en "JSON: per-perspective analysis"
        text summary_fa
        int article_count
        int source_count
        boolean covered_by_state
        boolean covered_by_diaspora
        float coverage_diversity_score
        boolean is_blindspot
        string blindspot_type "state_only | diaspora_only | single_source"
        jsonb topics
        float trending_score
        int priority "Manual: higher = more prominent"
        jsonb centroid_embedding "Mean of article embeddings"
        timestamp llm_failed_at "Retry backoff: skip 24h"
    }

    ANALYST {
        uuid id PK
        string name_en
        string name_fa
        string slug UK
        string political_leaning "reformist | conservative | independent | opposition | academic"
        string location "inside_iran | outside_iran"
        string affiliation
        jsonb focus_areas
        text bio_en
        text bio_fa
        boolean is_active
        boolean is_imprisoned
    }

    ANALYST_TAKE {
        uuid id PK
        uuid analyst_id FK
        uuid story_id FK
        uuid telegram_post_id FK
        text raw_text
        string summary_fa
        string key_claim
        string take_type "prediction | reasoning | insider_signal | fact_check | historical_parallel | commentary"
        string confidence_direction "bullish | bearish | neutral"
        boolean verified_later
        text verification_note
        timestamp published_at
    }

    BIAS_SCORE {
        uuid id PK
        uuid article_id FK
        float political_alignment "-1 pro-regime to +1 opposition"
        float pro_regime_score
        float reformist_score
        float opposition_score
        jsonb framing_labels
        float tone_score "-1 negative to +1 positive"
        float emotional_language_score "0 factual to 1 loaded"
        float factuality_score
        int source_citation_count
        boolean uses_loaded_language
        string scoring_method "llm_initial | llm_refined | crowd_validated"
        string llm_model
        float confidence
        text reasoning_en
        text reasoning_fa
    }

    USER {
        uuid id PK
        string email UK
        string username UK
        text hashed_password
        string display_name
        boolean is_rater
        string rater_level "novice | trained | expert | admin"
        float rater_reliability_score
        int total_ratings
        boolean is_active
    }

    COMMUNITY_RATING {
        uuid id PK
        uuid user_id FK
        uuid article_id FK
        float political_alignment_rating "-2 to +2"
        float factuality_rating "1-5"
        jsonb framing_labels
        float tone_rating "-2 to +2"
        float emotional_language_rating "1-5"
        text notes
        boolean was_blind
        int time_spent_seconds
    }

    IMPROVEMENT_FEEDBACK {
        uuid id PK
        string target_type "story | story_title | story_image | article | source | layout | homepage | other"
        string target_id
        text target_url
        string issue_type "wrong_title | bad_image | wrong_clustering | bad_summary | layout_issue | bug | feature_request | other"
        text current_value
        text suggested_value
        text reason
        string rater_name
        string status "open | in_progress | done | wont_do | duplicate"
        string priority "low | medium | high"
    }

    TELEGRAM_CHANNEL {
        uuid id PK
        string username UK
        string title
        string channel_type "news | commentary | activist | political_party | citizen | aggregator"
        string political_leaning "pro_regime | reformist | opposition | monarchist | left | neutral"
        boolean is_aggregator "True for link-aggregation channels"
        int subscriber_count
        boolean is_active
        int last_message_id
    }

    TELEGRAM_POST {
        uuid id PK
        uuid channel_id FK
        uuid story_id FK
        int message_id
        text text
        timestamp date
        int views
        int forwards
        int reply_count
        jsonb urls
        float sentiment_score
        jsonb framing_labels
        jsonb keywords
        boolean shares_news_link
        boolean is_commentary
    }

    SOCIAL_SENTIMENT_SNAPSHOT {
        uuid id PK
        uuid story_id FK
        int total_posts
        int total_views
        int total_forwards
        int unique_channels
        float avg_sentiment
        int positive_count
        int negative_count
        int neutral_count
        jsonb framing_distribution
        text dominant_narrative
        float narrative_divergence
    }

    INGESTION_LOG {
        uuid id PK
        uuid source_id FK
        text feed_url
        string status "success | error | partial"
        int articles_found
        int articles_new
        text error_message
        timestamp started_at
    }

    SOURCE ||--o{ ARTICLE : "publishes"
    STORY ||--o{ ARTICLE : "groups"
    ARTICLE ||--o{ BIAS_SCORE : "scored by LLM"
    ARTICLE ||--o{ COMMUNITY_RATING : "rated by humans"
    USER ||--o{ COMMUNITY_RATING : "submits"
    ANALYST ||--o{ ANALYST_TAKE : "authors"
    STORY ||--o{ ANALYST_TAKE : "about"
    TELEGRAM_POST ||--o{ ANALYST_TAKE : "extracted from"
    TELEGRAM_CHANNEL ||--o{ TELEGRAM_POST : "contains"
    STORY ||--o{ TELEGRAM_POST : "linked to"
    STORY ||--o{ SOCIAL_SENTIMENT_SNAPSHOT : "tracked over time"
    SOURCE ||--o{ INGESTION_LOG : "logged"
```

**Key design decisions:**
- All primary keys are UUIDs (not auto-increment integers).
- Bilingual fields use `_fa` / `_en` suffixes throughout.
- Embeddings and variable-length lists (keywords, entities, framing labels) are stored as PostgreSQL JSONB.
- The `story.summary_en` field stores the full per-perspective analysis as a JSON blob (state view, diaspora view, independent view, bias explanation, dispute scores, loaded words, media neutrality scores).
- `story.centroid_embedding` stores the mean of all article embeddings, used for fast cosine pre-filtering during clustering.
- `analyst_take.take_type` classifies insights: predictions (verifiable later), reasoning, insider signals, fact checks, historical parallels, and commentary.
- `telegram_channel.is_aggregator` flags channels that post links to articles from many sources (used for article extraction pipeline).

---

## 4. Intelligence Features

Doornegar goes beyond simple aggregation with several intelligence capabilities.

```mermaid
graph TD
    subgraph Detection["Detection Systems"]
        Silence["Silence Detection<br/>What topics does one side<br/>NOT cover?"]
        Coord["Coordinated Messaging<br/>Same framing across<br/>multiple outlets simultaneously"]
    end

    subgraph Tracking["Narrative Tracking"]
        Arc["Narrative Arc<br/>How a story's framing<br/>evolves over time"]
        Delta["What-Changed Delta<br/>New facts/sources/angles<br/>since last analysis"]
    end

    subgraph Verification["Analyst Verification"]
        Takes["16 Analysts Tracked<br/>Predictions, claims,<br/>insider signals extracted<br/>from Telegram channels"]
        Verify["Prediction Verification<br/>nano model compares<br/>old claims to new facts"]
        TrackRecord["Source Track Records<br/>Which analysts/outlets<br/>got it right?"]
    end

    subgraph Output["User-Facing Output"]
        BlindSpots["Blind Spot Alerts<br/>(state_only | diaspora_only<br/>| single_source)"]
        DisputeScore["Dispute Score<br/>0.0 = agrees on facts<br/>1.0 = total contradiction"]
        LoadedWords["Loaded Words<br/>per-side vocabulary<br/>(Words of the Week)"]
    end

    Silence --> BlindSpots
    Coord --> DisputeScore
    Arc --> Delta
    Takes --> Verify
    Verify --> TrackRecord
    TrackRecord --> Output
```

**Intelligence features explained:**
- **Silence Detection**: Identifies topics covered by one political side but ignored by the other, surfaced as blind spots on the homepage.
- **Coordinated Messaging**: Detects when multiple outlets use identical framing or talking points within a short timeframe, suggesting coordinated narrative campaigns.
- **Narrative Arc Tracking**: Tracks how a story's framing evolves over days/weeks across different media outlets.
- **What-Changed Delta**: Injected into Pass 2 analysis -- tells the LLM what facts/sources/angles are new since the last analysis run.
- **Prediction Verification**: Uses the nano model to compare analysts' past predictions against newly emerged facts, building track records.
- **Source Track Records**: Over time, builds reliability profiles for both analysts and news outlets based on prediction accuracy and factual consistency.

---

## 5. LLM Model Strategy & Cost Structure

Three-tier model selection optimized for quality-per-dollar.

```mermaid
graph LR
    subgraph Premium["Premium Tier: gpt-5-mini"]
        P1["Story analysis<br/>(top 16 trending)"]
        P2["Story clustering<br/>(reasoning-heavy)"]
    end

    subgraph Baseline["Baseline Tier: gpt-4o-mini"]
        B1["Bias scoring<br/>(all visible stories)"]
        B2["Story analysis<br/>(non-trending)"]
    end

    subgraph Economy["Economy Tier: gpt-4.1-nano"]
        E1["Title translation<br/>(fa ↔ en)"]
        E2["Pass 1: Fact extraction"]
        E3["Prediction verification"]
        E4["Quality post-processing"]
        E5["Silence detection"]
    end

    subgraph Cost["Monthly Cost at 300 articles/day"]
        Total["~$37/month total"]
    end

    Premium --> Total
    Baseline --> Total
    Economy --> Total
```

---

## 6. API Endpoints Map

All REST endpoints grouped by function.

```mermaid
graph LR
    subgraph Public["Public Endpoints"]
        Health["/health<br/>GET -- health check"]

        subgraph StoriesAPI["Stories"]
            S1["GET /api/v1/stories<br/>List stories (paginated)"]
            S2["GET /api/v1/stories/trending<br/>Top trending stories"]
            S3["GET /api/v1/stories/blindspots<br/>One-sided coverage"]
            S4["GET /api/v1/stories/{id}<br/>Story detail + articles + bias"]
            S5["GET /api/v1/stories/{id}/analysis<br/>AI-generated analysis"]
        end

        subgraph SourcesAPI["Sources"]
            So1["GET /api/v1/sources<br/>List all news sources"]
            So2["GET /api/v1/sources/{slug}<br/>Source detail"]
        end

        subgraph ArticlesAPI["Articles"]
            A1["GET /api/v1/articles<br/>List articles (paginated)"]
            A2["GET /api/v1/articles/{id}<br/>Article detail"]
        end

        subgraph SocialAPI["Social / Telegram"]
            T1["GET /api/v1/social/channels<br/>List tracked channels"]
            T2["POST /api/v1/social/channels<br/>Add a channel"]
            T3["GET /api/v1/social/stories/{id}/social<br/>Posts linked to story"]
            T4["GET /api/v1/social/stories/{id}/sentiment/history<br/>Sentiment over time"]
        end

        subgraph StatsAPI["Public Stats"]
            St1["GET /api/v1/rate/stats<br/>Rating statistics"]
            St2["GET /api/v1/feedback/stats<br/>Feedback statistics"]
        end
    end

    subgraph AuthEndpoints["Auth (Raters)"]
        Au1["POST /api/v1/auth/login<br/>JWT login for raters"]
        Au2["GET /api/v1/auth/me<br/>Current user info"]
    end

    subgraph RaterEndpoints["Rating (Invite-Only)"]
        R1["GET /api/v1/rate/next<br/>Next article to rate (blind)"]
        R2["POST /api/v1/rate/{article_id}<br/>Submit a rating"]
        R3["GET /api/v1/rate/history<br/>Rater's rating history"]
    end

    subgraph FeedbackEndpoints["Feedback (Raters)"]
        F1["POST /api/v1/feedback/article-relevance<br/>Flag article relevance"]
        F2["POST /api/v1/feedback/summary-rating<br/>Rate summary accuracy"]
        F3["POST /api/v1/feedback/source-categorization<br/>Suggest source re-categorization"]
    end

    subgraph AdminEndpoints["Admin"]
        Ad1["GET /api/v1/admin/dashboard<br/>System metrics + issues"]
        Ad2["POST /api/v1/admin/pipeline/run-all<br/>Full pipeline"]
        Ad3["POST /api/v1/admin/maintenance/run<br/>Full maintenance cycle"]
        Ad4["POST /api/v1/admin/ingest/trigger<br/>RSS ingestion"]
        Ad5["POST /api/v1/admin/nlp/trigger<br/>NLP processing"]
        Ad6["POST /api/v1/admin/cluster/trigger<br/>Story clustering"]
        Ad7["POST /api/v1/admin/cluster-llm/trigger<br/>LLM-based clustering"]
        Ad8["POST /api/v1/admin/bias/trigger<br/>Bias scoring"]
        Ad9["GET /api/v1/admin/ingest/log<br/>Ingestion history"]
        Ad10["GET /api/v1/admin/costs<br/>LLM cost tracking"]
        Ad11["GET /api/v1/admin/debug/llm<br/>Test API keys"]
        Ad12["POST /api/v1/admin/raters/create<br/>Create rater account"]
        Ad13["GET /api/v1/admin/raters<br/>List raters"]
        Ad14["POST /api/v1/admin/raters/{username}/deactivate<br/>Deactivate rater"]
        Ad15["PATCH /api/v1/admin/stories/{id}<br/>Edit story title/summary"]
        Ad16["POST /api/v1/stories/{id}/summarize<br/>Force re-summarize"]
    end
```

**Access control:**
- **Public** endpoints require no authentication.
- **Auth/Rating/Feedback** endpoints require a JWT token from an invited rater.
- **Admin** endpoints are currently unprotected (admin auth is on the roadmap).

---

## 7. Frontend Page Structure & Homepage Layout

The Next.js app uses locale-based routing for bilingual support.

```mermaid
graph TD
    Root["/ (root)"]
    Root --> Locale["/{locale}<br/>(fa or en)"]

    Locale --> Home["/ (Home Page)"]
    Locale --> StoriesPage["/stories<br/>All stories list"]
    Locale --> SourcesPage["/sources<br/>All news sources"]
    Locale --> BlindspotsPage["/blindspots<br/>One-sided coverage"]
    Locale --> RatePage["/rate<br/>Blind rating (raters only)"]
    Locale --> ImprovePage["/improve<br/>Submit improvement feedback"]
    Locale --> SuggestPage["/suggest<br/>Suggest new sources"]
    Locale --> LabPage["/lab<br/>Experimental features"]
    Locale --> Dashboard["/dashboard<br/>Admin dashboard"]

    StoriesPage --> StoryDetail["/stories/{id}<br/>Story detail page"]
    SourcesPage --> SourceDetail["/sources/{slug}<br/>Source profile"]
    LabPage --> LabDetail["/lab/{id}<br/>Lab experiment detail"]
    Dashboard --> DashImprovements["/dashboard/improvements"]
    Dashboard --> DashSuggestions["/dashboard/suggestions"]
    Dashboard --> DashArch["/dashboard/architecture"]

    style Home fill:#e8f5e9
    style StoryDetail fill:#e3f2fd
    style BlindspotsPage fill:#fff3e0
    style RatePage fill:#fce4ec
    style Dashboard fill:#f3e5f5
```

### Homepage Section Layout

```mermaid
graph TD
    subgraph HP["Homepage (top to bottom)"]
        Row1["Row 1: Telegram Feed | Hero Story | Blind Spot Alerts"]
        Row2["Row 2: Weekly Briefing | Most Read Stories"]
        Row3["Row 3: Most Disputed Stories | Numbers in the News"]
        Row4["Row 4: Narrative Map (visual story connections)"]
        Row5["Row 5: Words of the Week (loaded vocabulary per side)"]
    end

    Row1 --> Row2 --> Row3 --> Row4 --> Row5
```

### Story Detail Page Layout

```mermaid
graph LR
    subgraph StoryPage["Story Detail Page"]
        subgraph MainCol["Main Column"]
            Tabs["Tabbed Analysis:<br/>Bias Comparison |<br/>Conservative View |<br/>Opposition View"]
            Articles["Article List<br/>(grouped by alignment)"]
        end

        subgraph Sidebar["Sidebar"]
            Stats["Story Stats:<br/>sources, articles,<br/>coverage diversity,<br/>dispute score"]
            Analysts["Analyst Takes:<br/>predictions, commentary<br/>from 16 tracked analysts"]
            Spectrum["Political Spectrum:<br/>media positioning<br/>diagram for this story"]
        end
    end
```

---

## 8. Maintenance and Automation Flow

How the system stays up-to-date automatically.

```mermaid
flowchart TD
    subgraph Trigger["Trigger (macOS LaunchAgent)"]
        LA["com.doornegar.maintenance.plist<br/>StartInterval: 14400s (4 hours)<br/>RunAtLoad: true"]
    end

    subgraph MainScript["auto_maintenance.py (30 steps)"]
        Start(["Maintenance Starts"])

        Step1["1. Ingest<br/>RSS (30+ sources) + Telegram +<br/>aggregator link extraction"]

        Step2["2-3. NLP Process<br/>Normalize → embed → translate →<br/>extract keywords → backfill titles<br/>Embedding dedup + batches of 50"]

        Step3["4-6. Cluster<br/>Cosine similarity + LLM verification →<br/>recompute centroids →<br/>merge similar stories (threshold 0.55)"]

        Step4["7-8. Two-Pass Analysis + Bias<br/>Pass 1: gpt-4.1-nano fact extraction<br/>Pass 2: gpt-5-mini/gpt-4o-mini framing<br/>+ Bias scoring (visible stories only)<br/>Priority: top 15 stories per run"]

        Step5["9-12. Quality + Intelligence<br/>Fix images → story quality →<br/>silence detection →<br/>coordinated messaging detection"]

        Step6["13-19. Maintenance<br/>Source health → archive stale →<br/>trending → 3-layer dedup →<br/>auto-fixes → flag unrelated →<br/>image relevance"]

        Step7["20-24. Analysts + Feedback<br/>Extract analyst takes →<br/>verify predictions →<br/>apply rater feedback →<br/>feedback health → TG health"]

        Step8["25-31. Health + Reporting<br/>Visual check → uptime →<br/>disk monitoring → cost tracking →<br/>DB backup → quality post-processing →<br/>weekly digest → update docs"]

        Done(["Maintenance Complete<br/>Results logged to maintenance.log"])
    end

    subgraph ManualOps["Manual Operations (manage.py)"]
        Seed["python manage.py seed<br/>Initialize sources + TG channels"]
        Pipeline["python manage.py pipeline<br/>Full pipeline"]
        Individual["python manage.py ingest|process|cluster|score|telegram<br/>Individual steps"]
        Summarize["python manage.py summarize<br/>Generate missing summaries"]
        Status["python manage.py status<br/>Show system metrics"]
    end

    subgraph AdminAPI["Admin API Triggers"]
        APIDash["GET /admin/dashboard<br/>View metrics + issues + progress"]
        APIMaint["POST /admin/maintenance/run<br/>Trigger full maintenance"]
        APIPipe["POST /admin/pipeline/run-all<br/>Trigger full pipeline"]
        APIIndiv["POST /admin/ingest|nlp|cluster|bias/trigger<br/>Individual steps"]
    end

    LA -->|"every 4 hours"| Start
    Start --> Step1
    Step1 --> Step2
    Step2 --> Step3
    Step3 --> Step4
    Step4 --> Step5
    Step5 --> Step6
    Step6 --> Step7
    Step7 --> Step8
    Step8 --> Done

    Done -->|"logs to"| LogFile["maintenance.log<br/>maintenance_error.log"]

    style LA fill:#fff9c4
    style Start fill:#c8e6c9
    style Done fill:#c8e6c9
    style Step4 fill:#e3f2fd
    style Step5 fill:#fff3e0
```

**Automation details:**
- The macOS LaunchAgent triggers `auto_maintenance.py` every 4 hours and on boot.
- Each of the 30 steps is wrapped in try/except so a failure in one step does not block subsequent steps.
- Per-step progress is tracked via `maintenance_state.py` and visible in the admin dashboard.
- The NLP processing step runs in a loop, processing batches of 50 articles until all are done.
- Summarization uses analysis priority ranking (coverage diversity, both-sides coverage, source count, recency) to pick the top 15 stories per run.
- The two-pass analysis injects Pass 1 facts into Pass 2, achieving deeper analysis without doubling prompt cost.
- The 3-layer deduplication checks URL duplicates, embedding similarity, and content overlap.
- All results are logged to `maintenance.log` (stdout) and `maintenance_error.log` (stderr).
- Manual operations via `manage.py` or the Admin API can trigger the same steps on demand.
