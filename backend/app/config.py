from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Doornegar"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    port: int = 8000

    # Database — supports both local and cloud (Neon) URLs
    # Neon gives postgresql:// URLs; we convert to postgresql+asyncpg://
    database_url: str = "postgresql+asyncpg://doornegar:doornegar_dev@localhost:5432/doornegar"

    # Redis — supports both local and cloud (Upstash) URLs
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = ""  # MUST be set via SECRET_KEY env var
    admin_token: str = ""  # Set ADMIN_TOKEN env var for admin API access
    access_token_expire_minutes: int = 60 * 24 * 7  # 1 week

    # CORS — allowed frontend origins
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # Ingestion
    ingestion_interval_minutes: int = 15
    ingestion_timeout_seconds: int = 30
    max_articles_per_feed: int = 50

    # LLM — 3-tier model strategy:
    #   Premium (gpt-5-mini): story analysis for top-N trending stories
    #     (homepage visible). Best quality where it counts.
    #   Baseline (gpt-4o-mini): bias scoring + long-tail story analysis.
    #     Good quality at ~1/3 the cost of premium.
    #   Economy (gpt-4.1-nano): title translation. Simple task where
    #     nano-tier models are indistinguishable in output quality.
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    bias_scoring_model: str = "gpt-4o-mini"        # baseline
    story_analysis_model: str = "gpt-4o-mini"       # baseline (non-trending)
    story_analysis_premium_model: str = "gpt-5-mini"  # premium (top-N)
    translation_model: str = "gpt-4.1-nano"         # economy
    content_type_model: str = "gpt-4.1-nano"        # economy — drop-noise classifier
    # Only the top-N trending stories get gpt-5-mini for story analysis;
    # the rest use gpt-4o-mini. Kept at 5 to mirror the telegram Pass 2
    # tiering — together they keep premium-tier spend tight on the hero
    # band while still giving cheaper analysis to the long tail.
    premium_story_top_n: int = 5
    # Top-N trending stories that get a دورنما briefing (gpt-5-mini prose
    # synthesis on top of the structured analysis). Independent of
    # premium_story_top_n so we can broaden the briefing tier without
    # also broadening the premium-analysis tier.
    doornama_top_n: int = 10
    doornama_model: str = "gpt-5-mini"

    # NLP
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    clustering_similarity_threshold: float = 0.45
    story_merge_threshold: float = 0.55
    # Clustering safety limits
    max_cluster_size: int = 30           # refuse to grow a story past this
    clustering_time_window_days: int = 7  # only match within this window
    # Clustering is a "does article A belong in story B?" decision —
    # baseline is plenty. Was gpt-5-mini until 2026-04-18 when the
    # delta grew beyond the original $0.20/month estimate (Phase-2
    # matching prompt now includes ~500 tokens of context per candidate
    # story × 50 candidates per batch). Override via CLUSTERING_MODEL.
    clustering_model: str = "gpt-4o-mini"

    # Telegram
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_fetch_interval_minutes: int = 30
    telegram_channel_username: str = ""  # Your Doornegar public channel
    # Serialized Telethon session (StringSession.save output). Used on Railway
    # where a file-based session doesn't persist across deploys. Generate it
    # locally once with `python scripts/export_telegram_session.py` and set it
    # as the TELEGRAM_SESSION_STRING env var in Railway.
    telegram_session_string: str = ""

    # Twitter/X
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""

    # Instagram (Meta Business API)
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""

    # WhatsApp Business API
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""

    # Bluesky
    bluesky_handle: str = ""
    bluesky_app_password: str = ""

    # LinkedIn
    linkedin_access_token: str = ""
    linkedin_org_id: str = ""

    # Cloudflare R2 (S3-compatible object storage for images)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "doornegar-images"
    r2_public_url: str = ""  # e.g. https://pub-xxx.r2.dev

    # Unsplash API (stock-image picker in admin dashboard)
    unsplash_access_key: str = ""  # get one free at unsplash.com/developers

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def async_database_url(self) -> str:
        """Convert database URL to async driver format for SQLAlchemy."""
        url = self.database_url
        # Neon/Supabase give postgresql:// — convert to asyncpg
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)

        # asyncpg doesn't understand sslmode/channel_binding (those are libpq params)
        # Strip them and enforce SSL via ssl=require for cloud DBs
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(url)
        query_params = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in ("sslmode", "channel_binding")
        ]
        is_cloud = "neon.tech" in parts.netloc or "supabase" in parts.netloc
        if is_cloud and not any(k == "ssl" for k, _ in query_params):
            query_params.append(("ssl", "require"))
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_params), parts.fragment))
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
