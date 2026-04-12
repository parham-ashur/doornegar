export interface Source {
  id: string;
  name_en: string;
  name_fa: string;
  slug: string;
  website_url: string;
  rss_urls: string[];
  logo_url: string | null;
  state_alignment: "state" | "semi_state" | "independent" | "diaspora";
  irgc_affiliated: boolean;
  production_location: "inside_iran" | "outside_iran";
  factional_alignment: string | null;
  language: string;
  is_active: boolean;
  credibility_score: number | null;
  media_dimensions: Record<string, number> | null;
  description_en: string | null;
  description_fa: string | null;
  created_at: string;
}

export interface ArticleBrief {
  id: string;
  source_id: string;
  story_id: string | null;
  title_original: string;
  title_en: string | null;
  title_fa: string | null;
  url: string;
  summary: string | null;
  image_url: string | null;
  author: string | null;
  language: string;
  published_at: string | null;
  ingested_at: string;
}

export interface BiasScore {
  id: string;
  article_id: string;
  political_alignment: number | null;
  pro_regime_score: number | null;
  reformist_score: number | null;
  opposition_score: number | null;
  framing_labels: string[];
  tone_score: number | null;
  emotional_language_score: number | null;
  factuality_score: number | null;
  source_citation_count: number | null;
  anonymous_source_count: number | null;
  uses_loaded_language: boolean | null;
  scoring_method: string;
  confidence: number | null;
  reasoning_en: string | null;
  reasoning_fa: string | null;
  created_at: string;
}

export interface StoryBrief {
  id: string;
  title_en: string;
  title_fa: string;
  slug: string;
  article_count: number;
  source_count: number;
  covered_by_state: boolean;
  covered_by_diaspora: boolean;
  is_blindspot: boolean;
  blindspot_type: string | null;
  coverage_diversity_score: number | null;
  topics: string[];
  first_published_at: string | null;
  updated_at: string | null;
  trending_score: number;
  priority: number;
  image_url: string | null;
  state_pct: number;
  diaspora_pct: number;
  independent_pct: number;
}

export interface StoryArticleWithBias extends ArticleBrief {
  source_name_en: string | null;
  source_name_fa: string | null;
  source_slug: string | null;
  source_state_alignment: string | null;
  bias_scores: BiasScore[];
}

export interface StoryDetail extends StoryBrief {
  summary_en: string | null;
  summary_fa: string | null;
  articles: StoryArticleWithBias[];
}

export interface SocialSentiment {
  story_id: string;
  total_posts: number;
  total_views: number;
  total_forwards: number;
  unique_channels: number;
  avg_sentiment: number | null;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  framing_distribution: Record<string, number>;
  snapshot_at: string;
}

export type StateAlignment = "state" | "semi_state" | "independent" | "diaspora";

export interface SideBiasScores {
  tone: number | null;
  factuality: number | null;
  emotional_language: number | null;
  framing: string | string[] | null;
}

export interface NarrativeArc {
  evolution: string | null;
  vocabulary_shift: string[];
  direction: "escalating" | "de-escalating" | "shifting" | "stable" | null;
}

export interface StoryAnalysis {
  summary_fa: string | null;
  state_summary_fa: string | null;
  diaspora_summary_fa: string | null;
  independent_summary_fa: string | null;
  bias_explanation_fa: string | null;
  scores: {
    state: SideBiasScores | null;
    diaspora: SideBiasScores | null;
    independent: SideBiasScores | null;
  } | null;
  source_neutrality: Record<string, number> | null;
  dispute_score: number | null;
  loaded_words: { conservative: string[]; opposition: string[] } | null;
  narrative_arc: NarrativeArc | null;
  delta: string | null;
  silence_analysis: {
    silent_side: string;
    loud_side: string;
    loud_count: number;
    loud_sources: string[];
    hypothesis_fa?: string;
  } | null;
  coordinated_messaging: {
    side: string;
    sources: string[];
    similarity: number;
    time_window_hours: number;
  } | null;
}

// ─── Lab / Topics ──────────────────────────────

export interface TopicBrief {
  id: string;
  title_fa: string;
  title_en: string | null;
  slug: string;
  mode: "news" | "debate";
  is_auto: boolean;
  article_count: number;
  is_active: boolean;
  image_url: string | null;
  has_articles: boolean;
  has_analysts: boolean;
  analysis_fa: string | null;
  analyzed_at: string | null;
  created_at: string;
}

export interface AnalystPerspective {
  name_fa: string;
  platform: string;
  followers: string;
  political_leaning: string;
  quote_fa: string;
}

export interface TopicArticleInfo {
  id: string;
  title_fa: string | null;
  title_en: string | null;
  url: string | null;
  source_name_fa: string | null;
  source_state_alignment: string | null;
  match_confidence: number | null;
  match_method: string | null;
  published_at: string | null;
}

export interface DebatePosition {
  position_fa: string;
  argument_fa: string;
  supporting_sources: string[];
  strength: number;
}

export interface TopicAnalysis {
  // News mode
  summary_fa?: string | null;
  state_summary_fa?: string | null;
  diaspora_summary_fa?: string | null;
  independent_summary_fa?: string | null;
  bias_explanation_fa?: string | null;
  scores?: Record<string, SideBiasScores | null> | null;
  // Debate mode
  topic_summary_fa?: string | null;
  positions?: DebatePosition[];
  key_disagreements_fa?: string[];
  conclusion_fa?: string | null;
}

export interface TopicDetail extends TopicBrief {
  description_fa: string | null;
  analysis: TopicAnalysis | null;
  analysts: AnalystPerspective[];
  articles: TopicArticleInfo[];
}
