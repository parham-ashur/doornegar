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
        Pages["Pages:<br/>Home, Stories, Sources,<br/>Blindspots, Rate, Dashboard"]
    end

    subgraph Backend["Backend (FastAPI / Railway)"]
        API["FastAPI REST API<br/>/api/v1/*"]
        Auth["JWT Auth<br/>(invite-only raters)"]
        StaticFiles["Static Image Server<br/>/images/*"]
    end

    subgraph Workers["Background Workers"]
        AutoMaint["auto_maintenance.py<br/>(LaunchAgent, every 4h)"]
        ManagePy["manage.py CLI<br/>(manual pipeline runs)"]
    end

    subgraph Data["Data Stores"]
        PG[("PostgreSQL<br/>+ pgvector<br/>(384-dim embeddings)")]
        Redis[("Redis<br/>(Celery broker,<br/>caching)")]
    end

    subgraph External["External Services"]
        RSS["~12 Iranian RSS Feeds<br/>(state, diaspora,<br/>independent)"]
        TG["Telegram API<br/>(public channels)"]
        OpenAI["OpenAI GPT-4o-mini<br/>(bias scoring,<br/>translation,<br/>summarization)"]
        Anthropic["Anthropic Claude Haiku<br/>(bias scoring fallback)"]
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
    Workers -->|"LLM fallback"| Anthropic

    API -->|"serves"| StaticFiles
```

**Key points:**
- The frontend is a Next.js 14 app with bilingual routing (`/fa/...` and `/en/...`).
- The backend is a FastAPI application with fully async database operations.
- Background processing runs via `auto_maintenance.py` on a macOS LaunchAgent (every 4 hours) or manually via `manage.py`.
- PostgreSQL stores all data including 384-dimensional multilingual embeddings for article similarity.
- LLM calls go primarily to OpenAI GPT-4o-mini, with Anthropic Claude Haiku as a fallback.

---

## 2. Data Pipeline Flow

The complete journey of a news article from RSS feed to the user's screen.

```mermaid
flowchart LR
    subgraph Ingest["Step 1: Ingest"]
        RSS["RSS Feeds<br/>(~12 sources)"]
        TG["Telegram<br/>Channels"]
        Scraper["Web Scraper<br/>(full text)"]
        IngestSvc["ingestion.py<br/>+ telegram_service.py"]
    end

    subgraph NLP["Step 2: NLP Process"]
        Normalize["Persian Text<br/>Normalization"]
        Translate["Translation<br/>(fa <-> en)"]
        Embed["Embeddings<br/>(MiniLM-L12-v2<br/>384-dim)"]
        Keywords["Keyword &<br/>Entity Extraction"]
    end

    subgraph Cluster["Step 3: Cluster"]
        Cosine["Cosine Similarity<br/>on Embeddings"]
        TopicLLM["LLM Topic<br/>Extraction<br/>(optional)"]
        StoryGroup["Group into<br/>Stories"]
        Blindspot["Detect<br/>Blind Spots"]
    end

    subgraph Analyze["Step 4: Analyze"]
        BiasLLM["LLM Bias Scoring<br/>(political alignment,<br/>tone, factuality)"]
        Summary["Story Summary<br/>Generation<br/>(per-perspective)"]
        Sentiment["Sentiment<br/>Analysis"]
    end

    subgraph Serve["Step 5: Serve"]
        APILayer["FastAPI<br/>REST API"]
        FrontendApp["Next.js<br/>Frontend"]
    end

    RSS --> IngestSvc
    TG --> IngestSvc
    IngestSvc --> Scraper
    Scraper --> Normalize

    Normalize --> Translate
    Normalize --> Embed
    Normalize --> Keywords

    Embed --> Cosine
    Keywords --> TopicLLM
    Cosine --> StoryGroup
    TopicLLM --> StoryGroup
    StoryGroup --> Blindspot

    Blindspot --> BiasLLM
    Blindspot --> Summary
    Blindspot --> Sentiment

    BiasLLM --> APILayer
    Summary --> APILayer
    Sentiment --> APILayer
    APILayer --> FrontendApp
```

**Pipeline steps in detail:**

| Step | Service File | What It Does |
|------|-------------|--------------|
| Ingest | `ingestion.py`, `telegram_service.py` | Fetches RSS feeds and Telegram posts, deduplicates by URL |
| NLP | `nlp_pipeline.py`, `translation.py` | Normalizes Persian text, generates embeddings, translates titles, extracts keywords |
| Cluster | `clustering.py`, `topic_clustering.py` | Groups articles into stories using cosine similarity on embeddings |
| Analyze | `bias_scoring.py`, `story_analysis.py` | LLM scores each article for bias; generates per-perspective summaries |
| Serve | `api/v1/*.py` | REST endpoints deliver data to the frontend |

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
        string state_alignment "state | semi_state | independent | diaspora"
        boolean irgc_affiliated
        string production_location "inside_iran | outside_iran"
        string factional_alignment "hardline | principlist | reformist | moderate | opposition | monarchist | left"
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

    RATER_FEEDBACK {
        uuid id PK
        uuid user_id FK
        string feedback_type "article_relevance | summary_accuracy | source_categorization"
        uuid story_id FK
        uuid article_id FK
        boolean is_relevant
        int summary_rating "1-5"
        text summary_correction
        uuid source_id FK
        string suggested_alignment
        string suggested_factional
    }

    TELEGRAM_CHANNEL {
        uuid id PK
        string username UK
        string title
        string channel_type "news | commentary | activist | political_party | citizen | aggregator"
        string political_leaning "pro_regime | reformist | opposition | monarchist | left | neutral"
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
        jsonb urls
        float sentiment_score
        jsonb framing_labels
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
    USER ||--o{ RATER_FEEDBACK : "submits"
    STORY ||--o{ RATER_FEEDBACK : "about"
    ARTICLE ||--o{ RATER_FEEDBACK : "about"
    SOURCE ||--o{ RATER_FEEDBACK : "about"
    TELEGRAM_CHANNEL ||--o{ TELEGRAM_POST : "contains"
    STORY ||--o{ TELEGRAM_POST : "linked to"
    STORY ||--o{ SOCIAL_SENTIMENT_SNAPSHOT : "tracked over time"
    SOURCE ||--o{ INGESTION_LOG : "logged"
```

**Key design decisions:**
- All primary keys are UUIDs (not auto-increment integers).
- Bilingual fields use `_fa` / `_en` suffixes throughout.
- Embeddings and variable-length lists (keywords, entities, framing labels) are stored as PostgreSQL JSONB.
- The `story.summary_en` field stores the full per-perspective analysis as a JSON blob (state view, diaspora view, independent view, bias explanation, scores).

---

## 4. API Endpoints Map

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

## 5. Frontend Page Structure

The Next.js app uses locale-based routing for bilingual support.

```mermaid
graph TD
    Root["/ (root)"]
    Root --> Locale["/{locale}<br/>(fa or en)"]

    Locale --> Home["/ (Home Page)<br/>Trending stories,<br/>latest articles,<br/>blind spot alerts"]

    Locale --> StoriesPage["/stories<br/>All stories list<br/>(paginated, filterable)"]
    StoriesPage --> StoryDetail["/stories/{id}<br/>Story detail:<br/>articles from all sides,<br/>bias comparison,<br/>AI summary,<br/>Telegram reactions"]

    Locale --> SourcesPage["/sources<br/>All news sources<br/>(filterable by alignment)"]
    SourcesPage --> SourceDetail["/sources/{slug}<br/>Source profile:<br/>alignment, articles,<br/>credibility"]

    Locale --> BlindspotsPage["/blindspots<br/>Stories with<br/>one-sided coverage"]

    Locale --> RatePage["/rate<br/>Blind rating interface<br/>(raters only)"]

    Locale --> AuthPages["/auth"]
    AuthPages --> Login["/auth/login<br/>Rater login"]
    AuthPages --> Register["/auth/register<br/>Rater registration<br/>(invite-only)"]

    Locale --> Dashboard["/dashboard<br/>Admin dashboard:<br/>system metrics,<br/>pipeline controls,<br/>issue alerts"]

    style Home fill:#e8f5e9
    style StoryDetail fill:#e3f2fd
    style BlindspotsPage fill:#fff3e0
    style RatePage fill:#fce4ec
    style Dashboard fill:#f3e5f5
```

**Navigation flow:**
- The home page shows trending stories and blind spot alerts.
- Users can drill into any story to see how different outlets (state, diaspora, independent) cover it.
- The `/rate` page is restricted to authenticated, invited raters who see articles without source attribution (blind rating).
- The `/dashboard` is for admin use: system health, pipeline triggers, and issue tracking.

---

## 6. Maintenance and Automation Flow

How the system stays up-to-date automatically.

```mermaid
flowchart TD
    subgraph Trigger["Trigger (macOS LaunchAgent)"]
        LA["com.doornegar.maintenance.plist<br/>StartInterval: 14400s (4 hours)<br/>RunAtLoad: true"]
    end

    subgraph MainScript["auto_maintenance.py"]
        Start(["Maintenance Starts"])

        Step1["Step 1: Ingest<br/>- Fetch RSS feeds (~12 sources)<br/>- Fetch Telegram channels<br/>- Convert TG posts to articles"]

        Step2["Step 2: NLP Process<br/>- Normalize Persian text<br/>- Generate embeddings (MiniLM)<br/>- Translate titles (fa/en)<br/>- Extract keywords & entities<br/>- Processes in batches of 50"]

        Step3["Step 3: Cluster<br/>- Cosine similarity grouping<br/>- Update story article counts<br/>- Detect blind spots"]

        Step4["Step 4: Summarize<br/>- Generate AI summaries<br/>  for stories with 5+ articles<br/>  that lack summaries<br/>- Per-perspective analysis<br/>  (state / diaspora / independent)"]

        Step5["Step 5: Auto-Fix<br/>- Fix English text in Farsi fields<br/>  (batch translate via GPT-4o-mini)<br/>- Clean source names from<br/>  Telegram post titles"]

        Step6["Step 6: Update Docs<br/>- Append to MAINTENANCE_LOG.md<br/>- Update PROJECT_STATUS.md metrics<br/>- Update REMINDERS.md timestamp"]

        Done(["Maintenance Complete<br/>Results logged to maintenance.log"])
    end

    subgraph ManualOps["Manual Operations (manage.py)"]
        Seed["python manage.py seed<br/>Initialize sources + TG channels"]
        Pipeline["python manage.py pipeline<br/>Full 6-step pipeline"]
        Individual["python manage.py ingest|process|cluster|score|telegram<br/>Individual steps"]
        Summarize["python manage.py summarize<br/>Generate missing summaries"]
        DownloadImg["python manage.py download-images<br/>Cache article images locally"]
        Status["python manage.py status<br/>Show system metrics"]
    end

    subgraph AdminAPI["Admin API Triggers"]
        APIDash["GET /admin/dashboard<br/>View metrics + issues"]
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
    Step6 --> Done

    Done -->|"logs to"| LogFile["maintenance.log<br/>maintenance_error.log"]

    style LA fill:#fff9c4
    style Start fill:#c8e6c9
    style Done fill:#c8e6c9
    style Step4 fill:#e3f2fd
    style Step5 fill:#fff3e0
```

**Automation details:**
- The macOS LaunchAgent (`com.doornegar.maintenance.plist`) triggers `auto_maintenance.py` every 4 hours and on boot.
- Each step is wrapped in try/except so a failure in one step does not block subsequent steps.
- The NLP processing step runs in a loop, processing batches of 50 articles until all are done.
- The summarization step only targets stories with 5+ articles that do not yet have a summary.
- The auto-fix step uses GPT-4o-mini to batch-translate any English text that ended up in Farsi fields.
- All results are logged to `maintenance.log` (stdout) and `maintenance_error.log` (stderr).
- The admin dashboard at `/admin/dashboard` reads `maintenance.log` to display the last run time and status.
- Manual operations via `manage.py` or the Admin API can trigger the same steps on demand.













---

## Auto-detected changes (2026-04-11 17:20)

**New service files**: topic_service.py

**New API files**: improvements.py, suggestions.py

**New model files**: improvement.py, suggestion.py

**New frontend pages**: improve

> These files were detected but not yet documented in the diagrams above. Update the diagrams to include them.
