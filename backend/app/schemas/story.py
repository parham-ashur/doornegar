import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.article import ArticleBrief
from app.schemas.bias import BiasScoreResponse
from app.schemas.source import SourceResponse


class NarrativeGroupPercentages(BaseModel):
    """Share of this story's articles coming from each of the 4 narrative subgroups.

    Sums to 100 unless the story has zero articles (all fields 0).
    """
    principlist: int = 0          # درون‌مرزی — اصول‌گرا
    reformist: int = 0            # درون‌مرزی — اصلاح‌طلب
    moderate_diaspora: int = 0    # برون‌مرزی — میانه‌رو
    radical_diaspora: int = 0     # برون‌مرزی — رادیکال


class StoryBrief(BaseModel):
    id: uuid.UUID
    title_en: str
    title_fa: str
    slug: str
    article_count: int
    source_count: int
    covered_by_state: bool
    covered_by_diaspora: bool
    is_blindspot: bool
    blindspot_type: str | None = None
    coverage_diversity_score: float | None = None
    topics: list[str]
    first_published_at: datetime | None = None
    # `last_updated_at` is set by the clustering layer every time a new article
    # joins the cluster — so it's the best stateless proxy for "when did this
    # story last gain fresh content". Used by the homepage freshness filter
    # (hero/blindspot rotation, Telegram predictions) to avoid surfacing the
    # same story for more than a day unless new articles arrive.
    last_updated_at: datetime | None = None
    updated_at: datetime | None = None
    trending_score: float
    view_count: int = 0
    priority: int = 0
    image_url: str | None = None
    # True when image_url was resolved from a real article image or a
    # curator-pinned manual override; false when it came from a source
    # logo fallback or is missing entirely. Frontend filters homepage
    # and related-stories lists on this so cards don't show with just
    # a logo as the cover. See /admin/hitl/stories-without-image for
    # the priority-sorted HITL queue.
    has_real_image: bool = False
    # Legacy 2-axis percentages (kept for backwards compat; remove after frontend migrates)
    state_pct: int = 0
    diaspora_pct: int = 0
    independent_pct: int = 0
    # New 4-subgroup taxonomy — see NarrativeGroupPercentages.
    narrative_groups: NarrativeGroupPercentages = NarrativeGroupPercentages()
    inside_border_pct: int = 0     # = principlist + reformist
    outside_border_pct: int = 0    # = moderate_diaspora + radical_diaspora
    # Daily-change signal computed from Story.analysis_snapshot_24h.
    # { has_update: bool, kind: "dispute"|"coverage_shift"|"new_articles"|null,
    #   reason_fa: str | null }
    # None when the column isn't populated yet (first-day behavior).
    update_signal: dict | None = None

    model_config = {"from_attributes": True}


class StoryArticleWithBias(ArticleBrief):
    source_name_en: str | None = None
    source_name_fa: str | None = None
    source_slug: str | None = None
    source_state_alignment: str | None = None
    bias_scores: list[BiasScoreResponse] = []


class ArcChapterBrief(BaseModel):
    story_id: str
    title_fa: str | None = None
    order: int


class StoryArcBrief(BaseModel):
    id: str
    title_fa: str
    slug: str
    chapters: list[ArcChapterBrief] = []


class StoryDetail(StoryBrief):
    summary_en: str | None = None
    summary_fa: str | None = None
    editorial_context_fa: dict | None = None
    articles: list[StoryArticleWithBias] = []
    arc: StoryArcBrief | None = None
    # Sources whose articles appear in this story. Embedded so the
    # frontend can render the political-spectrum + JSON-LD citations
    # without a second round trip to /api/v1/sources.
    covering_sources: list[SourceResponse] = []


class StoryListResponse(BaseModel):
    stories: list[StoryBrief]
    total: int
    page: int
    page_size: int


class BiasScores(BaseModel):
    tone: float | None = None
    factuality: float | None = None
    emotional_language: float | None = None
    framing: str | list[str] | None = None

class StoryAnalysisResponse(BaseModel):
    story_id: uuid.UUID
    summary_fa: str | None = None
    state_summary_fa: str | None = None
    diaspora_summary_fa: str | None = None
    independent_summary_fa: str | None = None
    bias_explanation_fa: str | None = None
    scores: dict[str, BiasScores | None] | None = None
    # Per-source neutrality scores (mean of per-article scores) for 2D spectrum (-1.0 to +1.0)
    source_neutrality: dict[str, float] | None = None
    # Per-article LLM neutrality scores, keyed by article_id
    article_neutrality: dict[str, float] | None = None
    # Per-article deterministic evidence — loaded-word hits, quote count,
    # word count, and the LLM score alongside. Keyed by article_id.
    article_evidence: dict[str, dict] | None = None
    # When analysis was frozen (story matured past 48h past last_updated_at).
    # Present as ISO-8601 string when set; absent otherwise.
    analysis_locked_at: str | None = None
    # Dispute score (0-1) for "most disputed" homepage section
    dispute_score: float | None = None
    # Loaded words per side for "words of the week"
    loaded_words: dict | None = None
    # Narrative arc — how the story evolved from related stories
    narrative_arc: dict | None = None
    # Delta — what's new since the last analysis
    delta: str | None = None
    # Deep analyst factors — populated only for premium-tier stories
    analyst: dict | None = None
    # Silence detection — which side is ignoring this story
    silence_analysis: dict | None = None
    # Coordinated messaging — same-side sources publishing near-identical content
    coordinated_messaging: dict | None = None
    # دورنما — flowing-prose narrative synthesis (4-8 sentences) that
    # weaves the per-side summaries + bias + silence into a single
    # coherent explanation. Generated by app/services/doornama.py for
    # the top `settings.doornama_top_n` trending stories per pass.
    briefing_fa: str | None = None
