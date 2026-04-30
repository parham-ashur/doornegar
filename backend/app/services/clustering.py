"""Story clustering service — Incremental LLM-based.

Groups articles about the same event/topic into "stories" using
OpenAI GPT-4o-mini. Uses an incremental approach:

1. Match new unclustered articles to EXISTING stories first
2. Cluster remaining unmatched articles into NEW stories
3. Promote hidden stories that now have 5+ articles
4. Merge similar hidden stories to reduce duplicates
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from openai import OpenAI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload


# Stories with fewer than this many articles use an absolute-count blindspot
# rule instead of a percentage threshold — because a single voice out of 3
# is clearly one-sided even though 33% > 20%.
_SMALL_CLUSTER_THRESHOLD = 6

# Minority-share threshold for large clusters. Bumped from 10% → 20% so that
# stories like "10 state + 2 diaspora" (17% minority) are flagged. The higher
# threshold is intentionally conservative — if we're wrong about a story
# being balanced, we'd rather err toward "we may have missed diaspora
# coverage" than confidently claim balance we don't have.
_MINORITY_PCT_THRESHOLD = 20


def _compute_blindspot(
    *,
    state_count: int,
    diaspora_count: int,
    covered_by_state: bool,
    covered_by_diaspora: bool,
) -> tuple[bool, str | None]:
    """Decide whether a story is a blindspot and, if so, which side.

    Returns (is_blindspot, blindspot_type). `blindspot_type` is:
      - "diaspora_only" → diaspora covers, state is silent/near-silent
      - "state_only"    → state covers, diaspora is silent/near-silent
      - None            → balanced

    Rules, in order:
      1. One side completely missing → blindspot for the present side.
      2. Small cluster (total < _SMALL_CLUSTER_THRESHOLD): a lone voice on
         one side against ≥2 on the other is a blindspot. A 2-1 story
         reads one-sided even at 33%.
      3. Otherwise, percentage rule: minority share < _MINORITY_PCT_THRESHOLD
         → blindspot.
    """
    total = state_count + diaspora_count
    if total == 0:
        return False, None

    if covered_by_diaspora and not covered_by_state:
        return True, "diaspora_only"
    if covered_by_state and not covered_by_diaspora:
        return True, "state_only"

    if total < _SMALL_CLUSTER_THRESHOLD:
        if state_count == 1 and diaspora_count >= 2:
            return True, "diaspora_only"
        if diaspora_count == 1 and state_count >= 2:
            return True, "state_only"

    state_pct = state_count / total * 100
    diaspora_pct = diaspora_count / total * 100
    if state_pct < _MINORITY_PCT_THRESHOLD and covered_by_diaspora:
        return True, "diaspora_only"
    if diaspora_pct < _MINORITY_PCT_THRESHOLD and covered_by_state:
        return True, "state_only"

    return False, None


async def _keepalive(db: AsyncSession) -> None:
    """Ping the DB connection with SELECT 1 to reset Neon's idle timer.

    Neon closes connections after ~5 minutes of idleness. Long-running
    clustering (many LLM calls per session) would otherwise kill the
    held connection mid-work. Call this before every long-running LLM
    batch so the session's underlying connection stays warm.

    On ping failure we LOG ONLY — earlier versions called `db.rollback()`
    here to recover from "current transaction is aborted" errors, but
    that cure was worse than the disease. SQLAlchemy 2's rollback expires
    every in-session ORM object per spec, and any subsequent attribute
    access (e.g. `article.id`, `article.title_fa`) on those objects
    triggers a sync lazy-refresh from inside an async context →
    `MissingGreenlet: greenlet_spawn has not been called`. That bug
    cascaded across ALL of cluster's match_existing and cluster_new
    phases between 2026-04-28 and 2026-04-30. Without the rollback the
    next db.execute will raise "transaction aborted" cleanly, which the
    cluster_articles phase wrappers catch and surface with a clear
    traceback — much better than expired-ORM-object lazy-load surprises.
    """
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"Keepalive ping failed (no rollback — see comment): {e}")

from app.config import settings
from app.models.article import Article
from app.models.source import Source
from app.models.story import Story

logger = logging.getLogger(__name__)

# Maximum articles per LLM request for clustering
BATCH_SIZE = 100
# Maximum existing story titles per LLM request for matching
STORY_BATCH_SIZE = 50

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

MATCHING_PROMPT = """\
You are a strict news editor specializing in Iranian media. Your job is to decide \
whether each new article is a direct continuation of an EXISTING story in the list \
below, or whether it is a SEPARATE story that needs its own entry.

**REJECTION IS THE DEFAULT.** Most articles will NOT match any existing story. \
Only match when you are highly confident that the new article is reporting the \
EXACT SAME specific event/announcement/development as the existing story.

Existing stories — each entry shows the headline plus (when available) the \
most recent article titles in that cluster and a short summary. Match against \
the cluster as a whole, not just the original headline, because a mature \
cluster often covers the event from multiple angles. You may still reject if \
the new article covers a DIFFERENT specific event, even when the topic overlaps:

{stories_block}

New articles (title + source):
{articles_block}

Return valid JSON:
{{
  "matches": [
    {{"article_idx": 1, "story_idx": 2}},
    {{"article_idx": 3, "story_idx": null}}
  ]
}}

STRICT RULES (follow all):
1. Match ONLY if the article is about the EXACT SAME specific event named in the story title.
2. "Iran-related" is NOT enough. "Same general topic" is NOT enough. "Same politician mentioned" is NOT enough.
3. Examples of what to REJECT (use story_idx: null):
   - Article about a different attack → separate story
   - Article about a follow-up days/weeks later → separate story
   - Article about a related but distinct event → separate story
   - Article mentioning Iran but primarily about another country → separate story
4. Examples of what to ACCEPT:
   - Same specific speech by the same official → match
   - Different outlets covering the exact same announcement → match
   - Same exact attack on the same target → match
5. Every article MUST get an entry in matches (either with a story_idx or with null).
6. If unsure, OUTPUT NULL. There is no penalty for nulls — there is a big penalty for wrong matches.
7. Return ONLY the JSON object, no commentary.
"""

CLUSTERING_PROMPT = """\
You are a news editor specializing in Iranian media. Given these article headlines \
from various Iranian news sources, group them by the specific news story they cover.

Articles:
{articles_block}

Return valid JSON with this exact structure:
{{
  "groups": [
    {{
      "article_ids": [1, 3, 7],
      "title_fa": "عنوان فارسی خبر",
      "title_en": "English news title",
      "topics": ["سیاسی"]
    }}
  ]
}}

Rules:
- ONLY include articles directly related to Iran
- EXCLUDE articles about other countries with no Iran connection
- CRITICAL: Each group must be about ONE SINGLE specific event. Do NOT combine different events even if they are related. For example:
  - "Attack on Sharif University" and "Killing of IRGC Quds Force commander" are TWO SEPARATE stories, not one
  - "Missile attack on Tel Aviv" and "Missile attack on Isfahan" are TWO SEPARATE stories
  - "Dollar price today" and "Stock market crash" are TWO SEPARATE stories
  - Multiple articles about the SAME attack on the SAME target = one group
- Be very precise: only group articles describing the exact same incident/event/announcement
- Titles must be specific and descriptive of the single event, NOT vague summaries
- Titles should be informative statements, NOT questions
- title_fa must be in Farsi, title_en must be in English
- Each article ID can appear in at most one group
- Articles that don't match any group should be excluded (don't force them)
- Minimum 2 articles per group
- Topics: سیاسی، نظامی، اقتصادی، اجتماعی، فرهنگی، ورزشی، حقوق بشر، هسته‌ای، فناوری، محیط زیست
- Return ONLY the JSON object, no extra text
"""

VISIBLE_MERGE_PROMPT = """\
You are a strict news editor. These are titles of VISIBLE news stories on the homepage. \
Some may be about the same event and should be merged to avoid repetition.

Stories:
{stories_block}

Return valid JSON:
{{
  "merge_groups": [
    {{
      "story_idxs": [1, 3],
      "reason": "both about the same ceasefire deal"
    }}
  ]
}}

Rules:
- Merge stories that are clearly about the SAME specific event or topic
- "Ceasefire agreement" and "Reactions to ceasefire" ARE the same story — merge them
- "Ceasefire agreement" and "Islamabad talks failure" are DIFFERENT events — do NOT merge
- Merge follow-up stories into the main story (e.g., "X happened" + "reactions to X" = merge)
- If unsure, do NOT merge
- Each story index can appear in at most one group
- Minimum 2 stories per group
- Return ONLY the JSON object
"""

MERGE_PROMPT = """\
You are a news editor. These are titles of small news stories. \
Which of them are about the EXACT SAME specific event and should be merged?

Stories:
{stories_block}

Return valid JSON:
{{
  "merge_groups": [
    {{
      "story_idxs": [1, 3]
    }}
  ]
}}

Rules:
- Only group stories about the EXACT SAME specific event
- If unsure, do NOT merge — keep them separate
- Each story index can appear in at most one group
- Minimum 2 stories per group
- Return ONLY the JSON object, no extra text
"""

# ---------------------------------------------------------------------------
# Helpers (kept from previous version)
# ---------------------------------------------------------------------------


def generate_slug(title: str) -> str:
    """Generate a URL-friendly slug from a title."""
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    if not slug or len(slug) < 3:
        slug = f"story-{uuid.uuid4().hex[:8]}"
    # Truncate and add uniqueness
    slug = slug[:150] + "-" + uuid.uuid4().hex[:6]
    return slug


def _compute_trending_score(
    article_count: int,
    first_published: datetime | None,
    source_count: int | None = None,
) -> float:
    """Compute a trending score based on article count, recency, and
    plurality of sources.

    Score = article_count * recency_factor * plurality_factor

    Plurality: a "story" with only one source is by definition not
    plural coverage — it's a single outlet's feed. We zero it out of
    the trending ranking so it can't ride to the top of the homepage
    on volume alone. The story still exists and is reachable by direct
    link, and it's also flagged in the HITL review queue for merge /
    freeze decisions.

    Recency uses exponential decay with half-life of 2 days:
    - 0 hours ago: 1.0x
    - 24 hours:    0.71x
    - 48 hours:    0.50x
    - 72 hours:    0.35x
    - 7 days:      0.09x
    - 14 days:     0.008x (essentially gone)
    """
    import math
    if first_published:
        hours_ago = (datetime.now(timezone.utc) - first_published).total_seconds() / 3600
        half_life_hours = 48  # 2 days
        recency_factor = max(0.01, math.pow(0.5, hours_ago / half_life_hours))
    else:
        recency_factor = 0.1

    # Single-source demotion: hard zero for trending. Visible stories
    # always have article_count >= 5, so single-source means a large
    # bulletin dump from one outlet — never pluralism.
    if source_count is not None and source_count <= 1 and article_count >= 5:
        return 0.0

    return article_count * recency_factor


def _parse_llm_response(response_text: str) -> dict:
    """Parse JSON response from the LLM, handling markdown code blocks."""
    text = response_text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse LLM response: {e}\nResponse: {response_text[:500]}"
        )
        return {}

    return result


def _build_articles_block(articles: list, source_names: dict[str, str] | None = None) -> str:
    """Build the numbered article list for the clustering prompt.

    Title + first ~150 chars of content is enough for the LLM to group
    by specific event. 400 chars was overkill for a grouping task and
    doubled token cost with no measurable quality win.

    source_names: optional pre-extracted mapping of article.id -> source name
    """
    lines = []
    for i, article in enumerate(articles, 1):
        title = article.title_original or article.title_fa or article.title_en or "(no title)"
        if source_names:
            sname = source_names.get(str(article.id), "Unknown")
        else:
            sname = "Unknown"
        body = (article.content_text or article.summary or "").strip()
        # Collapse whitespace so token usage is predictable
        body = " ".join(body.split())[:150]
        if body:
            lines.append(f"{i}. [{sname}] {title}\n    {body}")
        else:
            lines.append(f"{i}. [{sname}] {title}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call helpers (sync OpenAI in run_in_executor to avoid greenlet issues)
# ---------------------------------------------------------------------------


async def _call_openai(prompt: str, max_tokens: int = 4096, *, purpose: str = "clustering.cluster_new") -> dict:
    """Send a prompt to the configured clustering LLM and return parsed JSON."""
    from app.services.llm_helper import build_openai_params
    from app.services.llm_usage import log_llm_usage

    def _sync_call():
        client = OpenAI(api_key=settings.openai_api_key)
        try:
            params = build_openai_params(
                model=settings.clustering_model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0,
            )
            response = client.chat.completions.create(**params)
            response_text = response.choices[0].message.content
            logger.debug(f"OpenAI response: {response_text[:300]}")
            return _parse_llm_response(response_text), response.usage
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {}, None

    parsed, usage = await asyncio.get_event_loop().run_in_executor(None, _sync_call)
    if usage is not None:
        await log_llm_usage(
            model=settings.clustering_model,
            purpose=purpose,
            usage=usage,
        )
    return parsed


# ---------------------------------------------------------------------------
# Step 2: Match new articles to existing stories
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase-1/2 helpers: multi-signal match gating
# ---------------------------------------------------------------------------

_STOPWORDS_FA = {
    "از", "در", "به", "با", "و", "که", "را", "این", "آن", "های", "یک",
    "برای", "بر", "تا", "هم", "اما", "نیز", "یا", "چه", "همه", "باید",
    "شد", "است", "شود", "کرد", "می", "پس", "بین", "طی",
}


def _title_tokens(text: str | None) -> set[str]:
    """Extract comparable tokens from a Persian title. Drops stopwords,
    punctuation, short tokens, and ZWNJ noise. Used for the Jaccard
    overlap signal in multi-signal match gating.
    """
    if not text:
        return set()
    import re as _re

    t = text.replace("\u200c", " ")
    t = _re.sub(r"[،؛.؟!«»()\[\]\-—–:/\\\"'`]", " ", t)
    tokens = {w for w in t.split() if len(w) >= 3 and w not in _STOPWORDS_FA}
    return tokens


def _quoted_phrases(text: str | None) -> set[str]:
    """Return the set of phrases inside «…» — these are almost always
    entities, claims, or loaded words worth matching on."""
    if not text:
        return set()
    import re as _re

    return {m.strip() for m in _re.findall(r"«([^«»]+)»", text) if m.strip()}


def _number_tokens(text: str | None) -> set[str]:
    """Extract Latin + Persian digit runs (≥ 2 chars) from text. Same
    event usually shares casualty counts, dates, monetary figures —
    these are strong identity signals independent of wording."""
    if not text:
        return set()
    import re as _re

    latin = _re.findall(r"\d{2,}", text)
    fa = _re.findall(r"[۰-۹]{2,}", text)
    return set(latin) | set(fa)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _find_new_story_subclusters(
    articles: list["Article"],
    *,
    min_cluster_size: int = 2,
    cosine_threshold: float = 0.65,
) -> set:
    """Spot coherent sub-clusters inside the batch of unmatched articles.

    Why: two existing "attractor" stories can absorb every new article
    that's topically adjacent (e.g. "Pakistan ceasefire role" + "ceasefire
    itself" absorbing articles about a distinct "Pakistan security
    concerns" angle). Left alone, no third story ever forms — the
    matcher only looks at unmatched-so-far articles, but by then each
    one looks like a plausible extension of an existing cluster in
    isolation.

    Defense: before running the matcher, build a similarity graph over
    THIS run's incoming articles. Any connected component of ≥
    min_cluster_size articles that share a concrete identity signal
    (title-token Jaccard ≥ 0.35, a quoted phrase, or a numeric token)
    is a "forming new story" — reserve those articles, skip the matcher
    entirely, and let them flow into new-cluster creation.

    Returns the set of Article.id values that should be reserved. Empty
    set when nothing coherent forms (normal case — most runs).
    """
    from app.nlp.embeddings import cosine_similarity as _cosine_sim

    # Only consider articles that actually have embeddings; the rest
    # fall through to the matcher's normal conservative path.
    embedded = [a for a in articles if a.embedding and any(v != 0.0 for v in a.embedding[:5])]
    if len(embedded) < min_cluster_size:
        return set()

    # Precompute identity signals per article so the graph pass is cheap.
    sigs: dict = {}
    for a in embedded:
        title = a.title_fa or a.title_original or ""
        sigs[a.id] = {
            "tokens": _title_tokens(title),
            "quotes": _quoted_phrases(title),
            "numbers": _number_tokens(title),
        }

    # Union-find over articles connected by cosine ≥ threshold.
    parent: dict = {a.id: a.id for a in embedded}

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x, y):
        rx, ry = _find(x), _find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(len(embedded)):
        for j in range(i + 1, len(embedded)):
            a_i, a_j = embedded[i], embedded[j]
            try:
                sim = _cosine_sim(a_i.embedding, a_j.embedding)
            except Exception:
                continue
            if sim < cosine_threshold:
                continue
            _union(a_i.id, a_j.id)

    # Group by component, then keep only components ≥ min_cluster_size
    # that ALSO share a concrete identity signal across ≥ 2 members. A
    # cosine-only cluster of generic country-news articles (e.g. 3
    # "Pakistan …" pieces with no overlapping named token) isn't worth
    # reserving — those legitimately might belong to different stories.
    groups: dict = {}
    for aid in parent:
        groups.setdefault(_find(aid), []).append(aid)

    reserved: set = set()
    for members in groups.values():
        if len(members) < min_cluster_size:
            continue
        # Pairwise check: at least one pair in the cluster must share a
        # token beyond stopwords, a quote, or a number.
        has_shared_signal = False
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                si, sj = sigs[members[i]], sigs[members[j]]
                if (
                    _jaccard(si["tokens"], sj["tokens"]) >= 0.35
                    or bool(si["quotes"] & sj["quotes"])
                    or bool(si["numbers"] & sj["numbers"])
                ):
                    has_shared_signal = True
                    break
            if has_shared_signal:
                break
        if has_shared_signal:
            reserved.update(members)
    return reserved


async def _match_to_existing_stories(
    db: AsyncSession,
    articles: list[Article],
    source_names: dict[str, str],
    *,
    deadline_ts: float | None = None,
) -> list[uuid.UUID]:
    """Try to match new articles to existing visible stories.

    Multi-signal matching (Phases 1 + 2 of the clustering upgrade):

    1. EMBEDDING PRE-FILTER: cosine against the story centroid.
    2. SIGNAL GATING BEFORE THE LLM. For each (article, candidate_story)
       pair we compute:
          - cosine: embedding sim (already computed)
          - token_jaccard: Jaccard overlap of Persian title tokens
            between the article and the story's title + most recent
            article titles
          - quote_overlap: shared «…» phrases
          - number_overlap: shared numeric tokens (casualty counts,
            dates, $ figures)
          - time_delta_days
       Two fast-paths around the LLM:
          AUTO-MATCH  when cosine ≥ 0.85 AND (token_jaccard ≥ 0.35 OR
                      quote_overlap ≥ 1 OR number_overlap ≥ 1) AND
                      time_delta ≤ 2. Deterministic — no LLM call.
          AUTO-REJECT when cosine < 0.60 OR time_delta > 7. No LLM.
       Only the ambiguous middle band lands at the LLM.
    3. LLM CONFIRMATION. The prompt now sees a richer story block
       (title + top-3 article titles + short summary) so matching
       against mature clusters doesn't hinge on a single 8-word
       headline.

    Safety constraints (unchanged):
    - Story must have article_count < settings.max_cluster_size
    - Story must have been active within clustering_time_window_days
    - article_count must be >= 5 (visibility threshold)

    Returns the list of UUIDs that were NOT matched (not Article objects).
    The caller must re-fetch fresh articles by ID before using them in
    subsequent phases — passing potentially-expired ORM objects across
    phase boundaries was the root cause of the 2026-04-29 greenlet bugs.
    """
    from datetime import timedelta as _timedelta
    from app.nlp.embeddings import cosine_similarity as _cosine_sim

    # Capture article identities eagerly into plain Python tuples BEFORE
    # any DB operation that could expire the in-session ORM objects.
    # Background (2026-04-29 incident): `_keepalive` rolls back the session
    # on Neon-killed-connection. SQLAlchemy 2's rollback expires ALL
    # in-session ORM objects per spec. Then any subsequent attribute
    # access (including `a.id` in our final list comprehension) triggers
    # a lazy refresh — but we're in a sync code path, so it raises
    # `MissingGreenlet: greenlet_spawn has not been called`. The full
    # traceback is in maintenance_logs run_at=2026-04-29 17:36:30 UTC.
    # By caching ids upfront, the final filter uses primitives only and
    # never touches ORM state.
    article_ids_eager: list = [a.id for a in articles]

    # Pre-filter to LLM. Was 0.30 — too loose: articles with cosine
    # 0.30-0.40 to a candidate were sending the LLM to read pairs that
    # almost never matched, polluting cost and occasionally producing
    # wrong matches when the LLM rubber-stamped a borderline pair. The
    # 2026-04-26 embedder comparison showed almost no LLM-confirmed
    # matches below cosine 0.40; raising the floor saves clustering
    # tokens and cuts the false-positive rate without losing real
    # signal. Articles below this threshold to ALL candidates fall
    # through to _cluster_new_articles to seed a fresh story.
    EMBEDDING_SIM_THRESHOLD = 0.40
    # Past 2 days, raise the embedding floor — fresh stories deserve
    # easier accretion; older candidates need stronger evidence to keep
    # absorbing borderline articles. Sits between the existing 0.40
    # baseline and the 0.60 AUTO_REJECT cliff. Borderline articles in
    # the 2-7d band now seed their own story instead of getting glued
    # onto a 4-day-old cluster on weak cosine alone.
    EMBEDDING_SIM_THRESHOLD_AGED = 0.55
    AGED_CANDIDATE_DAYS = 2
    AUTO_MATCH_COSINE = 0.85
    AUTO_REJECT_COSINE = 0.60
    AUTO_MATCH_JACCARD = 0.35
    AUTO_MATCH_MAX_AGE_DAYS = 2
    AUTO_REJECT_MAX_AGE_DAYS = 7

    # F4 — never attach a new article to a story that hasn't been
    # touched in 10 days. The site's editorial intent: anything older
    # is dead context. Resurrecting a 2-week-old thread with one
    # straggler creates "thread-zombie" stories that look fresh but
    # carry stale narratives. The new article seeds its own story
    # instead. Tighter than `settings.clustering_time_window_days`
    # (which existed for legacy reasons); we pick the stricter of
    # the two.
    AGE_CAP_DAYS = 10
    legacy_cutoff = datetime.now(timezone.utc) - _timedelta(days=settings.clustering_time_window_days)
    fresh_cutoff = datetime.now(timezone.utc) - _timedelta(days=AGE_CAP_DAYS)
    time_cutoff = max(legacy_cutoff, fresh_cutoff)

    # Umbrella-story cap: even when last_updated_at is fresh (because
    # someone keeps adding articles every day), refuse to keep
    # extending a story whose first_published_at is older than 14d.
    # The pattern this kills: a single "Iran-US negotiations" cluster
    # that started 30 days ago and has absorbed 200+ articles by
    # being the obvious cosine match for every adjacent topic. New
    # articles should seed a fresh sub-story instead.
    UMBRELLA_FIRST_PUB_CAP_DAYS = 14
    umbrella_cutoff = datetime.now(timezone.utc) - _timedelta(days=UMBRELLA_FIRST_PUB_CAP_DAYS)

    # Get existing visible stories with their centroid embeddings +
    # last_updated_at (for time-delta gating) and summary_fa (for the
    # Phase-2 richer story block).
    result = await db.execute(
        select(
            Story.id, Story.title_fa, Story.title_en, Story.article_count,
            Story.centroid_embedding, Story.last_updated_at, Story.summary_fa,
        )
        .where(
            Story.article_count >= 5,
            Story.article_count < settings.max_cluster_size,
            Story.last_updated_at >= time_cutoff,
            Story.frozen_at.is_(None),
            # F3 — archived stories are never resurrected.
            Story.archived_at.is_(None),
            # Umbrella cap: drop stories whose first article is >14d
            # old. Their continued growth signals editorial sprawl,
            # not a coherent thread. Treats NULL first_published_at
            # as eligible (legacy data) so we don't accidentally
            # close every old-but-untimestamped story.
            (Story.first_published_at.is_(None)) | (Story.first_published_at >= umbrella_cutoff),
        )
        .order_by(Story.last_updated_at.desc().nullslast())
    )
    existing_stories = result.all()  # (id, title_fa, title_en, article_count, centroid, last_updated_at, summary_fa)
    logger.info(
        f"Matching against {len(existing_stories)} open stories "
        f"(article_count 5 .. {settings.max_cluster_size - 1}, "
        f"active within {settings.clustering_time_window_days}d)"
    )

    if not existing_stories:
        logger.info("No existing visible stories to match against")
        return articles

    # ── Phase 1: Embedding pre-filter ─────────────────────────────
    story_by_id = {row[0]: row for row in existing_stories}
    stories_with_centroids = {
        row[0]: row[4]  # story_id → centroid_embedding
        for row in existing_stories
        if row[4]
    }

    # Preload the 3 most-recent article titles per candidate story once,
    # so we can compute token/quote/number signals against a story's
    # actual vocabulary (not just the original headline). Also seeds the
    # Phase-2 richer story block sent to the LLM.
    story_recent_titles: dict[uuid.UUID, list[str]] = {}
    if story_by_id:
        recent_q = await db.execute(
            select(Article.story_id, Article.title_fa, Article.published_at)
            .where(Article.story_id.in_(list(story_by_id.keys())))
            .order_by(Article.published_at.desc().nullslast())
        )
        for sid, t_fa, _ in recent_q.all():
            if not t_fa:
                continue
            story_recent_titles.setdefault(sid, [])
            if len(story_recent_titles[sid]) < 3:
                story_recent_titles[sid].append(t_fa)

    # Negative-pair memory: (article_id, story_id) pairs that readers
    # have explicitly flagged as wrong over the last 90 days. Used below
    # to refuse re-attaching the same article to the same wrong story —
    # otherwise «نامرتبط» votes are toothless against the matcher.
    from app.models.feedback import RaterFeedback as _RF
    from app.models.improvement import ImprovementFeedback as _IF
    rejection_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    rater_rej_q = await db.execute(
        select(_RF.article_id, _RF.story_id).where(
            _RF.feedback_type == "article_relevance",
            _RF.is_relevant.is_(False),
            _RF.created_at >= rejection_cutoff,
        )
    )
    anon_rej_q = await db.execute(
        select(_IF.target_id, _IF.orphaned_from_story_id).where(
            _IF.target_type == "article",
            _IF.issue_type == "wrong_clustering",
            _IF.orphaned_from_story_id.isnot(None),
            _IF.created_at >= rejection_cutoff,
        )
    )
    rejected_pairs: set[tuple[str, str]] = set()
    for art_id, sid in rater_rej_q.all():
        if art_id and sid:
            rejected_pairs.add((str(art_id), str(sid)))
    for art_id_str, sid in anon_rej_q.all():
        if art_id_str and sid:
            rejected_pairs.add((str(art_id_str), str(sid)))
    if rejected_pairs:
        logger.info(f"Negative-pair memory: {len(rejected_pairs)} (article, story) rejections in window")

    # Source trust scores — higher-error sources need stronger cosine
    # evidence to attach to existing stories. Score 1.0 = baseline; 0.5
    # = effective threshold doubles. Updated by step_source_trust_recompute.
    #
    # #3 — cold-start probation. New sources have created_at < 14d ago
    # and zero history; the median-based recompute can't catch a bad
    # one until weeks of clustering damage are done. We treat their
    # score as min(score, 0.85) for the first 14 days regardless of
    # what the recompute produced. This raises their cosine bar from
    # 0.45 to ~0.53 — enough to cool the worst false-positive matches
    # without blocking legitimate ones.
    source_trust_q = await db.execute(
        select(Source.id, Source.cluster_quality_score, Source.created_at)
    )
    PROBATION_DAYS = 14
    PROBATION_CEILING = 0.85
    probation_cutoff = datetime.now(timezone.utc) - timedelta(days=PROBATION_DAYS)
    source_trust: dict[uuid.UUID, float] = {}
    probation_count = 0
    for sid, score, created_at in source_trust_q.all():
        s = float(score or 1.0)
        if created_at and created_at >= probation_cutoff and s > PROBATION_CEILING:
            s = PROBATION_CEILING
            probation_count += 1
        source_trust[sid] = s
    if probation_count:
        logger.info(f"Cold-start probation applied to {probation_count} source(s) (<14d old, capped trust at {PROBATION_CEILING})")

    # Per-story token/quote/number sets (story title + top-3 titles + summary).
    # Also track article_count — small stories have thin centroids that drift
    # easily when an off-topic article matches on generic vocabulary alone,
    # so we demand stronger evidence before sending them to the LLM.
    story_sig: dict[uuid.UUID, dict[str, set]] = {}
    for sid, row in story_by_id.items():
        title_fa = row[1]
        summary_fa = row[6]
        titles = [title_fa or ""] + story_recent_titles.get(sid, [])
        corpus = " ".join([t for t in titles if t] + ([summary_fa] if summary_fa else []))
        story_sig[sid] = {
            "tokens": _title_tokens(corpus),
            "quotes": _quoted_phrases(corpus),
            "numbers": _number_tokens(corpus),
            "last_updated_at": row[5],
            "article_count": row[3],
        }

    # Reserve coherent sub-clusters of this run's own unmatched articles
    # BEFORE running the matcher. Protects emergent third stories from
    # being absorbed one-by-one into adjacent attractor clusters. See
    # _find_new_story_subclusters for the full rationale.
    reserved_ids = _find_new_story_subclusters(articles)
    if reserved_ids:
        logger.info(
            f"Reserving {len(reserved_ids)} articles as an emerging new-story sub-cluster "
            f"(skipping the matcher for them)"
        )

    # Build per-article candidate story sets + auto-match / auto-reject
    article_candidates: dict[uuid.UUID, set[uuid.UUID]] = {}
    articles_without_embedding: list[Article] = []
    auto_match_pairs: list[tuple[Article, uuid.UUID]] = []

    auto_match_count = 0
    auto_reject_count = 0
    negative_block_count = 0
    low_trust_block_count = 0
    negative_blocks: list[tuple[uuid.UUID, uuid.UUID]] = []  # (article_id, story_id)
    low_trust_blocks: list[tuple[uuid.UUID, uuid.UUID, float, float]] = []  # (article_id, story_id, sim, threshold)

    now_utc = datetime.now(timezone.utc)

    import asyncio as _async_yield
    for _outer_idx, article in enumerate(articles):
        # Yield to the event loop every 25 articles. Each iteration runs
        # hundreds of synchronous cosine ops + Python checks, and at
        # several hundred articles × several hundred candidate stories
        # the cumulative CPU work starves uvicorn for 30-60+ seconds —
        # the dashboard's status polling can't refresh and /health
        # times out (observed 2026-04-28 during the dashboard-triggered
        # full run). `await asyncio.sleep(0)` is the cheapest yield —
        # it lets pending coroutines run a tick, then resumes here.
        if _outer_idx and _outer_idx % 25 == 0:
            await _async_yield.sleep(0)
        # Reserved articles skip matching entirely — they'll flow into
        # new-cluster creation along with the unmatched remainder.
        if article.id in reserved_ids:
            continue
        if not article.embedding or not any(v != 0.0 for v in (article.embedding or [])[:5]):
            articles_without_embedding.append(article)
            continue

        a_title = article.title_fa or article.title_original or ""
        a_tokens = _title_tokens(a_title)
        a_quotes = _quoted_phrases(a_title)
        a_numbers = _number_tokens(a_title)

        # Source-specific cosine multiplier — high-error sources have
        # cluster_quality_score < 1.0, which raises the effective
        # threshold this article needs to clear before being a match
        # candidate. trust_factor = 1/score, so 0.5-trust source needs
        # 2× the threshold (e.g. 0.45 → 0.90).
        source_score = source_trust.get(article.source_id, 1.0) if article.source_id else 1.0
        trust_factor = 1.0 / max(source_score, 0.5)

        candidates = set()
        for story_id, centroid in stories_with_centroids.items():
            # Negative-pair memory: refuse to even consider re-attaching
            # an article to a story it was explicitly flagged out of.
            if (str(article.id), str(story_id)) in rejected_pairs:
                negative_block_count += 1
                negative_blocks.append((article.id, story_id))
                continue

            sim = _cosine_sim(article.embedding, centroid)
            sig = story_sig.get(story_id, {})
            last_upd = sig.get("last_updated_at")
            age_days = 0.0
            if last_upd:
                age_days = abs((now_utc - last_upd).total_seconds()) / 86400.0

            # AUTO-REJECT: low cosine OR too old. Skip this pair entirely.
            if sim < AUTO_REJECT_COSINE or age_days > AUTO_REJECT_MAX_AGE_DAYS:
                auto_reject_count += 1
                continue

            # AUTO-MATCH: very high cosine AND a concrete shared signal
            # (token overlap, shared quote, or shared number) AND fresh.
            # Trust factor still applies — a low-trust source needs to
            # clear (AUTO_MATCH_COSINE × trust_factor).
            auto_match_threshold = min(AUTO_MATCH_COSINE * trust_factor, 0.99)
            if (
                sim >= auto_match_threshold
                and age_days <= AUTO_MATCH_MAX_AGE_DAYS
                and (
                    _jaccard(a_tokens, sig.get("tokens") or set()) >= AUTO_MATCH_JACCARD
                    or bool(a_quotes & (sig.get("quotes") or set()))
                    or bool(a_numbers & (sig.get("numbers") or set()))
                )
            ):
                auto_match_pairs.append((article, story_id))
                auto_match_count += 1
                break  # one story is enough; stop scanning

            # Otherwise — ambiguous middle band, send to LLM. Small
            # target stories (article_count < 10) get a tighter gate:
            # raise the cosine floor to 0.45 AND require at least one
            # concrete signal overlap (token jaccard ≥ 0.15, shared
            # quote, or shared number). This is the fix for the drift
            # pattern where off-topic articles matched a small story
            # on generic vocabulary and the LLM rubber-stamped.
            target_ac = sig.get("article_count") or 0
            target_small = target_ac and target_ac < 10
            if target_small:
                # Small-story rule wins — already a stricter gate.
                base_threshold = 0.45
            elif age_days > AGED_CANDIDATE_DAYS:
                base_threshold = EMBEDDING_SIM_THRESHOLD_AGED
            else:
                base_threshold = EMBEDDING_SIM_THRESHOLD
            effective_threshold = min(base_threshold * trust_factor, 0.95)
            if sim >= effective_threshold:
                if target_small:
                    has_signal = (
                        _jaccard(a_tokens, sig.get("tokens") or set()) >= 0.15
                        or bool(a_quotes & (sig.get("quotes") or set()))
                        or bool(a_numbers & (sig.get("numbers") or set()))
                    )
                    if not has_signal:
                        continue
                candidates.add(story_id)
            elif sim >= base_threshold and trust_factor > 1.0:
                # Would have qualified at baseline but source's penalty
                # made the threshold too high — record so the dashboard
                # shows feedback actually moved the needle.
                low_trust_block_count += 1
                low_trust_blocks.append((article.id, story_id, sim, effective_threshold))

        # Record LLM candidates only for articles NOT auto-matched
        if candidates and not any(a is article for a, _ in auto_match_pairs):
            article_candidates[article.id] = candidates

    # Stats
    pre_filtered_articles = len(article_candidates) + len(articles_without_embedding)
    total_candidate_pairs = sum(len(c) for c in article_candidates.values())
    logger.info(
        f"Match gating — auto-match: {auto_match_count}, auto-reject: {auto_reject_count}, "
        f"negative-blocked: {negative_block_count}, low-trust-blocked: {low_trust_block_count}, "
        f"to LLM: {len(article_candidates)} articles × {total_candidate_pairs} pairs "
        f"(+{len(articles_without_embedding)} without embedding), "
        f"{len(articles) - pre_filtered_articles - auto_match_count} articles → new cluster"
    )

    # Apply deterministic auto-matches first.
    from app.services.events import log_event as _log_event

    # Log negative-pair + low-trust blocks so the dashboard can show
    # which feedback signals actually changed clustering decisions.
    # Cap event count per run to avoid story_events bloat — these are
    # diagnostic, not actionable. One row per (article, story) pair.
    for art_id, sid in negative_blocks[:50]:
        await _log_event(
            db,
            event_type="cluster_block_negative",
            actor="clustering",
            story_id=sid,
            article_id=art_id,
            signals={"reason": "rejected_pair_within_90d"},
        )
    for art_id, sid, sim, thr in low_trust_blocks[:50]:
        await _log_event(
            db,
            event_type="cluster_block_low_trust",
            actor="clustering",
            story_id=sid,
            article_id=art_id,
            confidence=float(sim),
            signals={
                "cosine": round(sim, 3),
                "effective_threshold": round(thr, 3),
            },
        )

    matched_article_ids: set[uuid.UUID] = set()
    # Track (article_id, story_id) pairs to drive metadata refresh later,
    # WITHOUT having to read article.story_id from the ORM at the end of
    # this function. After a mid-function keepalive rollback, ORM
    # attribute reads on expired objects raise greenlet_spawn — see the
    # comment block at the top of this function.
    matched_pairs: list[tuple] = []  # (article_id, story_id)
    for article, story_id in auto_match_pairs:
        if article.story_id is not None:
            continue
        article.story_id = story_id
        matched_article_ids.add(article.id)
        matched_pairs.append((article.id, story_id))
        await _log_event(
            db,
            event_type="match_accept",
            actor="pipeline",
            story_id=story_id,
            article_id=article.id,
            confidence=1.0,
            signals={"path": "auto_match", "via": "cosine+signal"},
        )

    # ── Phase 2: LLM confirmation for the ambiguous middle band ───
    articles_to_check = [
        a for a in articles
        if (a.id in article_candidates or a in articles_without_embedding)
        and a.id not in matched_article_ids
    ]

    if not articles_to_check:
        logger.info("No articles to send to LLM for matching (all filtered out by embeddings)")
        return articles

    # Collect the union of candidate story IDs across all articles
    candidate_story_ids = set()
    for cands in article_candidates.values():
        candidate_story_ids.update(cands)
    # For articles without embeddings, consider ALL stories (conservative)
    if articles_without_embedding:
        candidate_story_ids.update(row[0] for row in existing_stories)

    # Filter existing_stories to only the candidates
    filtered_stories = [row for row in existing_stories if row[0] in candidate_story_ids]

    logger.info(
        f"Sending {len(articles_to_check)} articles × {len(filtered_stories)} candidate stories to LLM"
    )

    import time as _time_match
    for story_batch_start in range(0, len(filtered_stories), STORY_BATCH_SIZE):
        # Deadline check — same pattern as _cluster_new_articles. If the
        # caller gave us a budget and we're past it, stop dispatching new
        # LLM batches; whatever already matched is preserved by the
        # intermediate commit in cluster_articles.
        if deadline_ts is not None and _time_match.time() >= deadline_ts:
            remaining_batches = (len(filtered_stories) - story_batch_start + STORY_BATCH_SIZE - 1) // STORY_BATCH_SIZE
            logger.warning(
                f"Match-existing deadline hit — stopping after "
                f"{story_batch_start // STORY_BATCH_SIZE} batches, "
                f"skipping {remaining_batches} remaining"
            )
            break
        story_batch = filtered_stories[story_batch_start: story_batch_start + STORY_BATCH_SIZE]

        # Phase-2 richer story block: title + top-3 recent article titles
        # + short summary (first ~200 chars). Matching against mature
        # clusters now hinges on the cluster's actual vocabulary, not
        # the single-sentence headline frozen at creation time.
        stories_lines = []
        for i, row in enumerate(story_batch, 1):
            sid, title_fa, title_en = row[0], row[1], row[2]
            summary_fa = row[6]
            display = title_fa or title_en or "(no title)"
            line = f"S{i}. {display}"
            recent = story_recent_titles.get(sid) or []
            # Drop the original title from the recent list if duplicated
            recent_unique = [t for t in recent if t and t != title_fa][:2]
            if recent_unique:
                line += "\n    recent titles: " + " / ".join(t[:80] for t in recent_unique)
            if summary_fa:
                line += "\n    summary: " + summary_fa[:200]
            stories_lines.append(line)
        stories_block = "\n".join(stories_lines)

        # Only send unmatched articles that have candidates in THIS batch
        batch_story_ids = {row[0] for row in story_batch}
        remaining = [
            a for a in articles_to_check
            if a.id not in matched_article_ids
            and (
                a.id in article_candidates and article_candidates[a.id] & batch_story_ids
                or a in articles_without_embedding  # conservative fallback
            )
        ]
        if not remaining:
            continue

        articles_block = _build_articles_block(remaining, source_names)

        prompt = MATCHING_PROMPT.format(
            stories_block=stories_block,
            articles_block=articles_block,
        )

        await _keepalive(db)
        result_json = await _call_openai(prompt, max_tokens=4096, purpose="clustering.match_existing")
        matches = result_json.get("matches", [])

        # Process matches
        for match in matches:
            article_idx = match.get("article_idx")
            story_idx = match.get("story_idx")

            if story_idx is None or article_idx is None:
                continue

            # Validate indices (1-based)
            if not (1 <= article_idx <= len(remaining)):
                logger.warning(f"Match article_idx out of range: {article_idx}")
                continue
            if not (1 <= story_idx <= len(story_batch)):
                logger.warning(f"Match story_idx out of range: {story_idx}")
                continue

            article = remaining[article_idx - 1]
            story_id = story_batch[story_idx - 1][0]  # UUID from the tuple

            # Guard: never double-assign. If the article was already matched
            # to a story in a previous batch of this run, or was already
            # assigned in the DB before this run, skip re-assigning.
            if article.id in matched_article_ids:
                logger.debug(
                    f"Skipping re-match: article {article.id} was already "
                    f"matched in an earlier batch of this run."
                )
                continue
            if article.story_id is not None:
                # Pre-existing assignment (defensive — the initial query
                # filters these out, but some path could still get here).
                continue

            # Assign article to story
            article.story_id = story_id
            matched_article_ids.add(article.id)
            matched_pairs.append((article.id, story_id))
            await _log_event(
                db,
                event_type="match_accept",
                actor="pipeline",
                story_id=story_id,
                article_id=article.id,
                signals={"path": "llm_confirm"},
            )
            logger.debug(f"Matched article {article.id} to story {story_id}")

    # Flush article assignments
    if matched_article_ids:
        await db.flush()

        # Collect affected story IDs from the matched_pairs we tracked
        # during the loops — never read article.story_id from the ORM
        # at this point. If a mid-function keepalive rollback expired
        # the in-session articles, that read raises greenlet_spawn.
        affected_story_ids = {sid for _, sid in matched_pairs}

        if affected_story_ids:
            await _refresh_stories_metadata_batch(db, affected_story_ids)

    logger.info(f"Matched {len(matched_article_ids)} articles to existing stories")

    # Return unmatched UUIDs (not Article objects). The caller is
    # responsible for re-fetching fresh ORM objects by ID before using
    # them in subsequent phases. After a mid-function keepalive
    # rollback, the input `articles` ORM objects are expired and
    # passing them downstream causes greenlet_spawn elsewhere
    # (observed in _cluster_new_articles at _dedup_signature on
    # 2026-04-30 01:27 / 05:29 UTC).
    return [aid for aid in article_ids_eager if aid not in matched_article_ids]


async def _refresh_story_metadata(db: AsyncSession, story_id: uuid.UUID) -> None:
    """Recalculate a story's article_count, source_count, coverage flags, etc."""
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if not story:
        return

    # Save old count for summary regeneration throttle
    old_article_count = story.article_count or 0

    # Recount articles
    count_result = await db.execute(
        select(func.count(Article.id)).where(Article.story_id == story_id)
    )
    story.article_count = count_result.scalar() or 0

    # Recount unique sources
    source_result = await db.execute(
        select(func.count(func.distinct(Article.source_id)))
        .where(Article.story_id == story_id)
    )
    story.source_count = source_result.scalar() or 0

    # Partition articles by the 4-subgroup narrative taxonomy.
    from app.services.narrative_groups import narrative_group as _ng_ref, side_of as _side_of_ref
    per_source_result = await db.execute(
        select(
            Source.production_location,
            Source.factional_alignment,
            Source.state_alignment,
            func.count(Article.id),
        )
        .join(Article, Article.source_id == Source.id)
        .where(Article.story_id == story_id)
        .group_by(Source.id)
    )
    state_count = 0
    diaspora_count = 0
    groups_present: set[str] = set()
    for prod_loc, fa_align, st_align, cnt in per_source_result.all():
        shim = type("S", (), {
            "production_location": prod_loc,
            "factional_alignment": fa_align,
            "state_alignment": st_align,
        })()
        grp = _ng_ref(shim)
        groups_present.add(grp)
        if _side_of_ref(grp) == "inside":
            state_count += cnt
        else:
            diaspora_count += cnt

    story.covered_by_state = state_count > 0
    story.covered_by_diaspora = diaspora_count > 0

    is_blindspot, blindspot_type = _compute_blindspot(
        state_count=state_count,
        diaspora_count=diaspora_count,
        covered_by_state=story.covered_by_state,
        covered_by_diaspora=story.covered_by_diaspora,
    )
    story.is_blindspot = is_blindspot
    story.blindspot_type = blindspot_type

    # coverage_diversity_score is now (subgroups observed) / 4 total subgroups
    story.coverage_diversity_score = len(groups_present) / 4.0
    story.last_updated_at = datetime.now(timezone.utc)

    # Recompute first_published_at from current articles. Without this,
    # stories that absorb articles via merge/HITL/cosine-pre-merge keep
    # whatever value the keeper had at creation — often null when the
    # keeper started empty (HITL scaffold) or with no published-dated
    # articles. Trending decay depends on this field.
    min_pub_result = await db.execute(
        select(func.min(Article.published_at))
        .where(Article.story_id == story_id, Article.published_at.isnot(None))
    )
    story.first_published_at = min_pub_result.scalar()

    story.trending_score = _compute_trending_score(
        story.article_count, story.first_published_at, story.source_count
    )

    # Recompute centroid embedding from DB (avoid stale lazy-loaded relationship)
    emb_result = await db.execute(
        select(Article.embedding)
        .where(Article.story_id == story_id, Article.embedding.isnot(None))
    )
    embeddings = [row[0] for row in emb_result.all() if row[0]]
    story.centroid_embedding = _compute_centroid(embeddings)

    # Only clear summary if article count changed by 3+ (throttle saves ~60%
    # of summary regeneration cost — each regeneration costs ~$0.01).
    # Hand-edited stories (is_edited=true) are NEVER cleared.
    count_delta = abs(story.article_count - old_article_count)
    if not story.is_edited and (count_delta >= 3 or story.summary_fa is None):
        story.summary_fa = None
        story.summary_en = None


async def _refresh_stories_metadata_batch(
    db: AsyncSession, story_ids: set
) -> None:
    """Batched version of _refresh_story_metadata for N stories.

    Instead of N × 4 queries (one per story), runs 3 aggregate queries
    that cover all stories at once, then updates the ORM objects in a
    single pass. Equivalent output, dramatically fewer DB round-trips.
    """
    if not story_ids:
        return

    id_list = list(story_ids)

    # 1. Load all affected Story ORM objects in one query
    story_result = await db.execute(
        select(Story).where(Story.id.in_(id_list))
    )
    stories_by_id = {s.id: s for s in story_result.scalars().all()}

    # 2. Count articles per story (GROUP BY)
    count_result = await db.execute(
        select(Article.story_id, func.count(Article.id))
        .where(Article.story_id.in_(id_list))
        .group_by(Article.story_id)
    )
    article_counts = {row[0]: row[1] for row in count_result.all()}

    # 3. Distinct source per story + subgroup counts. We pull full Source
    # classification columns and apply the narrative_group() helper.
    from app.services.narrative_groups import narrative_group as _ng_bulk, side_of as _side_of_bulk
    source_result = await db.execute(
        select(
            Article.story_id,
            Source.id,
            Source.production_location,
            Source.factional_alignment,
            Source.state_alignment,
            func.count(Article.id),
        )
        .join(Source, Source.id == Article.source_id)
        .where(Article.story_id.in_(id_list))
        .group_by(Article.story_id, Source.id)
    )
    groups_by_story: dict = {}
    source_counts_by_story: dict = {}
    side_counts_by_story: dict = {}  # {story_id: {"inside": int, "outside": int}}
    for sid, _src_id, prod_loc, fa_align, st_align, cnt in source_result.all():
        shim = type("S", (), {
            "production_location": prod_loc,
            "factional_alignment": fa_align,
            "state_alignment": st_align,
        })()
        grp = _ng_bulk(shim)
        groups_by_story.setdefault(sid, set()).add(grp)
        source_counts_by_story[sid] = source_counts_by_story.get(sid, 0) + 1
        side = _side_of_bulk(grp)
        bucket = side_counts_by_story.setdefault(sid, {"inside": 0, "outside": 0})
        bucket[side] = bucket[side] + cnt

    # 4. Apply updates in memory
    now = datetime.now(timezone.utc)
    for sid, story in stories_by_id.items():
        story.article_count = article_counts.get(sid, 0)
        story.source_count = source_counts_by_story.get(sid, 0)
        groups_present = groups_by_story.get(sid, set())
        sides = side_counts_by_story.get(sid, {"inside": 0, "outside": 0})
        story.covered_by_state = sides["inside"] > 0
        story.covered_by_diaspora = sides["outside"] > 0

        story.is_blindspot, story.blindspot_type = _compute_blindspot(
            state_count=sides["inside"],
            diaspora_count=sides["outside"],
            covered_by_state=story.covered_by_state,
            covered_by_diaspora=story.covered_by_diaspora,
        )
        story.coverage_diversity_score = len(groups_present) / 4.0
        story.last_updated_at = now
        story.trending_score = _compute_trending_score(
            story.article_count, story.first_published_at, story.source_count
        )
        # Clear summary so it gets regenerated by step_summarize — UNLESS the
        # story has been hand-edited by an admin, in which case we preserve
        # the manual content.
        if not story.is_edited:
            story.summary_fa = None
            story.summary_en = None

    # 5. Recompute centroid embeddings for affected stories (batch query)
    for sid in id_list:
        story = stories_by_id.get(sid)
        if not story:
            continue
        emb_result = await db.execute(
            select(Article.embedding)
            .where(Article.story_id == sid, Article.embedding.isnot(None))
        )
        embeddings = [row[0] for row in emb_result.all() if row[0]]
        story.centroid_embedding = _compute_centroid(embeddings)


def _compute_centroid(embeddings: list[list[float] | None]) -> list[float] | None:
    """Compute the mean (centroid) of a list of embedding vectors.

    Returns None if no valid embeddings are provided.
    """
    valid = [e for e in embeddings if e and any(v != 0.0 for v in e[:5])]
    if not valid:
        return None
    import numpy as np
    matrix = np.array(valid)
    centroid = matrix.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm  # L2-normalize the centroid
    return centroid.tolist()


# ---------------------------------------------------------------------------
# Step 3: Cluster unmatched articles into new stories
# ---------------------------------------------------------------------------

# Minimum articles required to create a new story from cluster_new.
# Matches the visibility floor (article_count >= 5) — stories below this
# would be hidden anyway, and each hidden story is an LLM call whose
# output will be merged or deleted by maintenance.
CLUSTER_NEW_GROUP_FLOOR = 5

# Articles that have been sent to cluster_new this many times without
# joining a viable group become orphans — skipped on future runs.
MAX_CLUSTER_ATTEMPTS = 3


def _dedup_signature(article: Article) -> str:
    """Compute a content signature for dedup bucketing.

    Articles with identical signatures are near-duplicates (same wire
    story picked up by multiple feeds, or same feed delivering content
    twice under different URLs). The LLM only needs to see one
    representative per bucket; sibling articles attach to whichever
    story the representative lands in.
    """
    import hashlib

    title = (article.title_original or article.title_fa or article.title_en or "").strip()
    title_norm = " ".join(title.lower().split())[:80]

    body = (article.content_text or article.summary or "").strip()
    body_norm = " ".join(body.split())[:400]

    raw = f"{title_norm}||{body_norm}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _cluster_new_articles(
    db: AsyncSession,
    articles: list[Article],
    source_names: dict[str, str],
    source_alignments_map: dict[str, str | None],
    *,
    deadline_ts: float | None = None,
) -> tuple[int, int]:
    """Cluster unmatched articles into new stories via LLM.

    Pipeline:
    1. Bucket articles by content signature — only one representative
       per bucket goes to the LLM, siblings attach to the same story.
    2. LLM groups representatives into candidate stories.
    3. After sibling expansion, groups below CLUSTER_NEW_GROUP_FLOOR
       (5 articles) are rejected. Their articles get cluster_attempts++.
    4. Articles that reach MAX_CLUSTER_ATTEMPTS are no longer returned
       by the step 1 query, so they won't be sent here again.

    `deadline_ts` (monotonic time.time()) is checked before each LLM
    batch — if we're past the deadline we stop dispatching new batches
    and let the caller commit whatever groups landed so far. This keeps
    `asyncio.wait_for` from having to cancel a stuck batch (which it
    can't do cleanly when the OpenAI client is mid-request and not
    yielding).

    Returns (new_stories_published, new_stories_hidden).
    """
    import time as _time
    if len(articles) < CLUSTER_NEW_GROUP_FLOOR:
        logger.info(
            f"Only {len(articles)} unmatched articles "
            f"(floor={CLUSTER_NEW_GROUP_FLOOR}) — skipping new clustering"
        )
        return 0, 0

    # --- Dedup: bucket articles by content signature ---
    buckets: dict[str, list[Article]] = {}
    for a in articles:
        sig = _dedup_signature(a)
        buckets.setdefault(sig, []).append(a)

    representatives: list[Article] = [bucket[0] for bucket in buckets.values()]
    dupes_saved = len(articles) - len(representatives)
    if dupes_saved > 0:
        logger.info(
            f"Dedup: {len(articles)} articles → {len(representatives)} "
            f"representatives ({dupes_saved} near-duplicates attached to siblings)"
        )

    logger.info(
        f"Clustering {len(representatives)} representatives into new stories"
    )

    all_groups: list[dict] = []

    deadline_skipped_batches = 0
    for batch_start in range(0, len(representatives), BATCH_SIZE):
        # Deadline check — if the caller passed a deadline and we're past
        # it, stop dispatching. Whatever already landed in `all_groups`
        # is preserved and committed by the caller.
        if deadline_ts is not None and _time.time() >= deadline_ts:
            remaining = (len(representatives) - batch_start + BATCH_SIZE - 1) // BATCH_SIZE
            deadline_skipped_batches = remaining
            logger.warning(
                f"Cluster deadline hit — stopping after {batch_start // BATCH_SIZE} batches, "
                f"skipping {remaining} remaining batches"
            )
            break
        batch = representatives[batch_start: batch_start + BATCH_SIZE]
        logger.info(
            f"Sending batch {batch_start // BATCH_SIZE + 1} "
            f"({len(batch)} representatives) to OpenAI for clustering"
        )
        articles_block = _build_articles_block(batch, source_names)
        prompt = CLUSTERING_PROMPT.format(articles_block=articles_block)
        await _keepalive(db)
        result_json = await _call_openai(prompt, max_tokens=4096, purpose="clustering.cluster_new")

        for group in result_json.get("groups", []):
            article_ids_in_prompt = group.get("article_ids", [])
            group_articles: list[Article] = []
            for idx in article_ids_in_prompt:
                actual_index = idx - 1
                if 0 <= actual_index < len(batch):
                    rep = batch[actual_index]
                    # Expand the representative back to all its dupe siblings
                    rep_sig = _dedup_signature(rep)
                    group_articles.extend(buckets.get(rep_sig, [rep]))
                else:
                    logger.warning(f"LLM returned out-of-range article ID: {idx}")

            if len(group_articles) >= CLUSTER_NEW_GROUP_FLOOR:
                all_groups.append({
                    "articles": group_articles,
                    "title_fa": group.get("title_fa", ""),
                    "title_en": group.get("title_en", ""),
                    "topics": group.get("topics", []),
                })

    # Collect IDs of articles that made it into a viable group
    grouped_ids: set = set()
    for g in all_groups:
        for a in g["articles"]:
            grouped_ids.add(a.id)

    # Everything we sent to the LLM that didn't end up in a viable group
    # gets its attempt counter bumped. Next run, articles at
    # MAX_CLUSTER_ATTEMPTS are filtered out of the unmatched pool.
    ungrouped_ids = [a.id for a in articles if a.id not in grouped_ids]
    if ungrouped_ids:
        # Commit the bump immediately in its own transaction so it
        # survives any later failure in step 5 (merge_tiny_by_cosine
        # / merge_hidden). Previously the bump was persisted by the
        # outer db.commit() in cluster_articles — but a partial merge
        # failure would roll the whole thing back, leaving every
        # article stuck at cluster_attempts=0 forever.
        # synchronize_session=False skips the SQLAlchemy attempt to
        # reflect the change into in-memory objects; it's a bulk
        # update on a column nothing else in this function reads.
        result = await db.execute(
            update(Article)
            .where(Article.id.in_(ungrouped_ids))
            .values(cluster_attempts=Article.cluster_attempts + 1)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        rowcount = getattr(result, "rowcount", None)
        logger.info(
            f"Bumped cluster_attempts on {len(ungrouped_ids)} ungrouped articles "
            f"(rows_affected={rowcount})"
        )

    logger.info(f"LLM returned {len(all_groups)} viable groups (≥{CLUSTER_NEW_GROUP_FLOOR} articles)")

    published = 0
    hidden = 0

    for group in all_groups:
        story = await _create_story(
            db,
            group["articles"],
            title_fa=group["title_fa"],
            title_en=group["title_en"],
            topics=group["topics"],
            source_alignments_map=source_alignments_map,
        )
        if story.article_count >= 5:
            published += 1
            logger.info(
                f"Created published story '{story.slug}' with {story.article_count} articles"
            )
        else:
            # Should not happen given the floor, but keep the log for safety
            hidden += 1
            logger.info(
                f"Created hidden story '{story.slug}' with {story.article_count} articles"
            )

    return published, hidden


# ---------------------------------------------------------------------------
# Step 5: Merge similar hidden stories
# ---------------------------------------------------------------------------


async def _merge_tiny_by_cosine(db: AsyncSession, threshold: float = 0.60) -> int:
    """Deterministic pre-merge for near-duplicate tiny stories.

    Finds pairs of stories with article_count ≤ 4 whose centroid
    embeddings have cosine similarity ≥ threshold (default 0.60) and
    merges them. Pure math, zero LLM cost — pairs the LLM would
    obviously merge get handled here first, shrinking the candidate
    pool for the subsequent LLM merge pass.

    A 2-article + 3-article merge often crosses the article_count ≥ 5
    visibility floor, so this directly surfaces stories that were
    stuck in the hidden pool. Conservative on threshold so we don't
    bad-merge different events that happen to share vocabulary.

    Returns number of stories absorbed.
    """
    from app.nlp.embeddings import cosine_similarity as _cs
    from app.models.social import TelegramPost, SocialSentimentSnapshot
    from app.models.feedback import RaterFeedback

    rows = (await db.execute(
        select(Story).where(
            Story.article_count <= 4,
            Story.centroid_embedding.isnot(None),
            Story.is_edited.is_(False),
            Story.frozen_at.is_(None),
        )
    )).scalars().all()
    stories = list(rows)
    if len(stories) < 2:
        return 0

    # Union-find for transitive merges across a group of 3+ tiny stories
    parent: dict[str, str] = {str(s.id): str(s.id) for s in stories}
    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # O(n²) cosine; with ≤ few thousand tiny stories that's fine for a
    # nightly pass. If it ever gets slow, bucket by leading embedding
    # dim.
    for i in range(len(stories)):
        for j in range(i + 1, len(stories)):
            try:
                sim = _cs(stories[i].centroid_embedding, stories[j].centroid_embedding)
            except Exception:
                continue
            if sim >= threshold:
                union(str(stories[i].id), str(stories[j].id))

    # Group by root
    groups: dict[str, list[Story]] = {}
    for s in stories:
        root = find(str(s.id))
        groups.setdefault(root, []).append(s)

    total_merged = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        # Keep the biggest; tie-break on last_updated_at newest
        group.sort(
            key=lambda s: (s.article_count, s.last_updated_at or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        keeper = group[0]
        from app.services.events import log_event as _log_event_tiny
        for victim in group[1:]:
            await db.execute(update(Article).where(Article.story_id == victim.id).values(story_id=keeper.id))
            await db.execute(update(TelegramPost).where(TelegramPost.story_id == victim.id).values(story_id=keeper.id))
            await db.execute(update(RaterFeedback).where(RaterFeedback.story_id == victim.id).values(story_id=keeper.id))
            from sqlalchemy import delete as _del
            await db.execute(_del(SocialSentimentSnapshot).where(SocialSentimentSnapshot.story_id == victim.id))
            await _log_event_tiny(
                db,
                event_type="merge",
                actor="pipeline",
                story_id=keeper.id,
                signals={
                    "path": "merge_tiny_cosine",
                    "victim_id": str(victim.id),
                    "victim_title_fa": (victim.title_fa or "")[:120],
                    "victim_article_count": victim.article_count or 0,
                },
            )
            await db.delete(victim)
            total_merged += 1
        await db.flush()
        await _refresh_story_metadata(db, keeper.id)

    if total_merged:
        logger.info(f"Cosine pre-merge: absorbed {total_merged} tiny stories at ≥{threshold} cosine")
    return total_merged


async def _merge_hidden_stories(db: AsyncSession) -> int:
    """Find and merge hidden stories (article_count < 5) that are about the same event.

    Returns number of stories that were merged (absorbed into others).
    """
    result = await db.execute(
        select(Story)
        .where(Story.article_count < 5, Story.frozen_at.is_(None))
        .order_by(Story.article_count.desc())
    )
    hidden_stories = list(result.scalars().all())

    if len(hidden_stories) < 3:
        logger.info(
            f"Only {len(hidden_stories)} hidden stories — skipping merge step (need 3+)"
        )
        return 0

    logger.info(f"Checking {len(hidden_stories)} hidden stories for merge candidates")

    # Build stories block
    stories_lines = []
    for i, story in enumerate(hidden_stories, 1):
        display = story.title_fa or story.title_en or "(no title)"
        stories_lines.append(f"S{i}. {display}")
    stories_block = "\n".join(stories_lines)

    prompt = MERGE_PROMPT.format(stories_block=stories_block)
    await _keepalive(db)
    result_json = await _call_openai(prompt, max_tokens=2048, purpose="clustering.merge_hidden")
    merge_groups = result_json.get("merge_groups", [])

    if not merge_groups:
        logger.info("No hidden stories to merge")
        return 0

    total_merged = 0

    for mgroup in merge_groups:
        idxs = mgroup.get("story_idxs", [])
        # Validate indices
        valid_stories = []
        for idx in idxs:
            if 1 <= idx <= len(hidden_stories):
                valid_stories.append(hidden_stories[idx - 1])
            else:
                logger.warning(f"Merge story_idx out of range: {idx}")

        if len(valid_stories) < 2:
            continue

        # Keep the story with the most articles
        valid_stories.sort(key=lambda s: s.article_count, reverse=True)
        keeper = valid_stories[0]
        to_absorb = valid_stories[1:]

        for victim in to_absorb:
            # Move all articles from victim to keeper
            await db.execute(
                update(Article)
                .where(Article.story_id == victim.id)
                .values(story_id=keeper.id)
            )
            # Move telegram posts and feedback to keeper, clear snapshots
            from app.models.social import TelegramPost, SocialSentimentSnapshot
            from app.models.feedback import RaterFeedback
            await db.execute(
                update(TelegramPost)
                .where(TelegramPost.story_id == victim.id)
                .values(story_id=keeper.id)
            )
            await db.execute(
                update(RaterFeedback)
                .where(RaterFeedback.story_id == victim.id)
                .values(story_id=keeper.id)
            )
            from sqlalchemy import delete
            await db.execute(
                delete(SocialSentimentSnapshot)
                .where(SocialSentimentSnapshot.story_id == victim.id)
            )
            from app.services.events import log_event as _le
            await _le(
                db,
                event_type="merge",
                actor="pipeline",
                story_id=keeper.id,
                signals={
                    "path": "merge_hidden_llm",
                    "victim_id": str(victim.id),
                    "victim_title_fa": (victim.title_fa or "")[:120],
                    "victim_article_count": victim.article_count or 0,
                },
            )
            # Delete the victim story
            await db.delete(victim)
            total_merged += 1
            logger.info(
                f"Merged story '{victim.slug}' into '{keeper.slug}'"
            )

        # Refresh keeper metadata
        await db.flush()
        await _refresh_story_metadata(db, keeper.id)

    logger.info(f"Merged {total_merged} duplicate hidden stories")
    return total_merged


async def merge_similar_visible_stories(db: AsyncSession) -> int:
    """Find and merge visible stories that look like duplicates.

    Unlike _merge_hidden_stories (which only looks at small stories),
    this checks ALL visible stories (article_count >= 5) for sibling
    clusters that should consolidate.

    Two candidate signals — either triggers a pair:
    1. Title word overlap >= 0.4 (lexical signal — was 0.5; loosened
       2026-04-26 after observing 4-5 sibling clusters about the same
       Iran-US event that all had similar but not 50%-overlapping
       titles).
    2. Centroid cosine >= 0.78 (semantic signal — catches sibling
       clusters that use different vocabulary for the same event,
       which the title-overlap rule alone missed).

    LLM then confirms which should actually merge. Candidate pool
    expanded 50 → 80 stories so longer-tail dupes also get a chance.
    LLM input is still capped at 30 stories to keep the prompt bounded.
    """
    from app.nlp.embeddings import cosine_similarity as _cosine_sim

    OVERLAP_THRESHOLD = 0.4
    CENTROID_COSINE_THRESHOLD = 0.78
    MAX_CANDIDATES_TO_LLM = 30

    result = await db.execute(
        select(Story)
        .where(Story.article_count >= 5, Story.frozen_at.is_(None))
        .order_by(Story.trending_score.desc())
        .limit(80)
    )
    stories = list(result.scalars().all())

    if len(stories) < 2:
        return 0

    def _words(s: str | None) -> set[str]:
        return {w for w in (s or "").split() if len(w) >= 3}

    candidates: list[Story] = []
    candidate_ids: set = set()
    title_pairs = 0
    centroid_pairs = 0

    for i, a in enumerate(stories):
        a_words = _words(a.title_fa)
        a_centroid = a.centroid_embedding if isinstance(a.centroid_embedding, list) else None
        for b in stories[i + 1:]:
            b_words = _words(b.title_fa)
            triggered = False

            # Signal 1: title-word overlap
            if a_words and b_words:
                overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
                if overlap >= OVERLAP_THRESHOLD:
                    triggered = True
                    title_pairs += 1

            # Signal 2: centroid cosine. Skip if either centroid is
            # missing — those stories haven't been through the
            # recompute step yet and we'd need to round-trip the LLM
            # without a real semantic signal anyway.
            if not triggered:
                b_centroid = b.centroid_embedding if isinstance(b.centroid_embedding, list) else None
                if a_centroid and b_centroid:
                    sim = _cosine_sim(a_centroid, b_centroid)
                    if sim >= CENTROID_COSINE_THRESHOLD:
                        triggered = True
                        centroid_pairs += 1

            if triggered:
                if a.id not in candidate_ids:
                    candidates.append(a)
                    candidate_ids.add(a.id)
                if b.id not in candidate_ids:
                    candidates.append(b)
                    candidate_ids.add(b.id)

    if len(candidates) < 2:
        logger.info(
            "No visible story pairs flagged "
            "(title_overlap >= %.2f or centroid_cosine >= %.2f)",
            OVERLAP_THRESHOLD,
            CENTROID_COSINE_THRESHOLD,
        )
        return 0

    if len(candidates) > MAX_CANDIDATES_TO_LLM:
        # Sort by trending_score and take the top to keep the LLM
        # prompt bounded. Hot stories matter more than long-tail dupes
        # for any single run; the latter will still surface on later
        # ticks as their centroids drift into range.
        candidates.sort(key=lambda s: s.trending_score or 0, reverse=True)
        candidates = candidates[:MAX_CANDIDATES_TO_LLM]

    logger.info(
        "Found %d visible stories to evaluate for merges (title=%d, centroid=%d) — calling LLM",
        len(candidates),
        title_pairs,
        centroid_pairs,
    )

    # Build stories block for LLM
    stories_lines = []
    for i, s in enumerate(candidates, 1):
        display = s.title_fa or s.title_en or "(no title)"
        stories_lines.append(f"S{i}. {display} ({s.article_count} articles)")
    stories_block = "\n".join(stories_lines)

    prompt = VISIBLE_MERGE_PROMPT.format(stories_block=stories_block)
    await _keepalive(db)
    result_json = await _call_openai(prompt, max_tokens=2048, purpose="clustering.merge_visible")
    merge_groups = result_json.get("merge_groups", [])

    if not merge_groups:
        logger.info("LLM confirmed no visible stories should merge")
        return 0

    total_merged = 0
    for mgroup in merge_groups:
        idxs = mgroup.get("story_idxs", [])
        valid_stories = []
        for idx in idxs:
            if 1 <= idx <= len(candidates):
                valid_stories.append(candidates[idx - 1])

        if len(valid_stories) < 2:
            continue

        # Keep the story with the most articles
        valid_stories.sort(key=lambda s: s.article_count, reverse=True)
        keeper = valid_stories[0]
        to_absorb = valid_stories[1:]

        for victim in to_absorb:
            # Move articles
            await db.execute(
                update(Article)
                .where(Article.story_id == victim.id)
                .values(story_id=keeper.id)
            )
            # Re-point any telegram posts that were linked to the victim story
            # so the DELETE doesn't fail on the FK constraint.
            from app.models.social import TelegramPost  # local import: avoid circular
            await db.execute(
                update(TelegramPost)
                .where(TelegramPost.story_id == victim.id)
                .values(story_id=keeper.id)
            )
            # Delete victim
            await db.delete(victim)
            total_merged += 1
            logger.info(
                f"Merged visible '{(victim.title_fa or '')[:40]}' ({victim.article_count} articles) "
                f"into '{(keeper.title_fa or '')[:40]}' — reason: {mgroup.get('reason', 'overlap')}"
            )

        # Refresh keeper
        await db.flush()
        await _refresh_story_metadata(db, keeper.id)

    if total_merged:
        await db.commit()
    logger.info(f"Merged {total_merged} duplicate visible stories")
    return total_merged


# ---------------------------------------------------------------------------
# Story creation helper
# ---------------------------------------------------------------------------


async def _create_story(
    db: AsyncSession,
    articles: list[Article],
    title_fa: str,
    title_en: str,
    topics: list[str],
    source_alignments_map: dict[str, str | None] | None = None,
) -> Story:
    """Create a new story from a cluster of articles with LLM-provided metadata."""
    # Fallback titles if LLM didn't provide them
    if not title_fa:
        primary = sorted(articles, key=lambda a: a.published_at or a.ingested_at)[-1]
        title_fa = primary.title_original or primary.title_fa or "بدون عنوان"
    if not title_en:
        primary = sorted(articles, key=lambda a: a.published_at or a.ingested_at)[-1]
        title_en = primary.title_en or title_fa

    # Partition articles by the 4-subgroup narrative taxonomy.
    from app.services.narrative_groups import narrative_group as _ng_c, side_of as _side_of_c
    groups_present: set[str] = set()
    state_n = 0
    diaspora_n = 0
    for article in articles:
        src = getattr(article, "source", None)
        if src is None:
            # Treat sourceless articles as moderate_diaspora (outside) so
            # they still contribute to a side and aren't mis-clustered.
            diaspora_n += 1
            groups_present.add("moderate_diaspora")
            continue
        grp = _ng_c(src)
        groups_present.add(grp)
        if _side_of_c(grp) == "inside":
            state_n += 1
        else:
            diaspora_n += 1

    covered_by_state = state_n > 0
    covered_by_diaspora = diaspora_n > 0

    is_blindspot, blindspot_type = _compute_blindspot(
        state_count=state_n,
        diaspora_count=diaspora_n,
        covered_by_state=covered_by_state,
        covered_by_diaspora=covered_by_diaspora,
    )

    # Coverage diversity: fraction of the 4 narrative subgroups present
    coverage_diversity = len(groups_present) / 4.0

    # Earliest published date
    published_dates = [a.published_at for a in articles if a.published_at]
    first_published = min(published_dates) if published_dates else None

    # Unique sources
    source_ids = {a.source_id for a in articles}

    # Compute centroid from article embeddings
    centroid = _compute_centroid([a.embedding for a in articles if a.embedding])

    story = Story(
        title_en=title_en,
        title_fa=title_fa,
        slug=generate_slug(title_en),
        article_count=len(articles),
        source_count=len(source_ids),
        covered_by_state=covered_by_state,
        covered_by_diaspora=covered_by_diaspora,
        is_blindspot=is_blindspot,
        blindspot_type=blindspot_type,
        coverage_diversity_score=coverage_diversity,
        topics=topics,
        first_published_at=first_published,
        last_updated_at=datetime.now(timezone.utc),
        trending_score=_compute_trending_score(len(articles), first_published, len(set(a.source_id for a in articles))),
        centroid_embedding=centroid,
    )
    db.add(story)
    await db.flush()  # Get the story ID

    # Link articles to this story
    article_ids = [a.id for a in articles]
    await db.execute(
        update(Article)
        .where(Article.id.in_(article_ids))
        .values(story_id=story.id)
    )

    from app.services.events import log_event as _log_event
    await _log_event(
        db,
        event_type="cluster_new",
        actor="pipeline",
        story_id=story.id,
        signals={
            "article_count": len(articles),
            "source_count": story.source_count,
            "title_fa": (story.title_fa or "")[:120],
        },
    )

    return story


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def cluster_articles(db: AsyncSession, *, deadline_ts: float | None = None) -> dict:
    """Main incremental clustering pipeline.

    Steps:
    1. Get new unclustered articles (story_id is NULL, last 30 days)
    2. Match new articles to existing visible stories (article_count >= 5)
    3. Cluster remaining unmatched articles into new stories
    4. Promote hidden stories that now have 5+ articles
    5. Merge similar hidden stories

    Returns dict with stats:
    {matched_to_existing, new_stories_created, new_stories_hidden, merged, unclustered}
    """
    # --- Fallback: no API key ---
    if not settings.openai_api_key:
        logger.warning(
            "OPENAI_API_KEY is not set — skipping LLM clustering. "
            "Set it in .env to enable story grouping."
        )
        return {
            "matched_to_existing": 0,
            "new_stories_created": 0,
            "new_stories_hidden": 0,
            "merged": 0,
            "unclustered": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # ── Step 1: Get unclustered articles from the last 30 days ──
    # Skip orphans that have already been sent to cluster_new
    # MAX_CLUSTER_ATTEMPTS times without joining a viable group.
    # Without this gate, articles with no duplicates (e.g. niche
    # single-source pieces) cycle through cluster_new on every
    # pipeline run, paying the LLM tax indefinitely.
    result = await db.execute(
        select(Article)
        .where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
            Article.cluster_attempts < MAX_CLUSTER_ATTEMPTS,
        )
        .order_by(Article.published_at.desc().nullslast())
    )
    articles = list(result.scalars().all())

    # Noise filter — titles matching these patterns are periodic format
    # posts (radio broadcast announcements, daily price bulletins) that
    # never cluster meaningfully with other outlets' coverage but keep
    # paying the LLM tax on every run. Filtered out and retired to
    # MAX_CLUSTER_ATTEMPTS so they won't be re-fetched.
    noise_patterns = [
        re.compile(r"📻"),
        re.compile(r"^\s*بشنوید"),
        re.compile(r"برنامه\s+رادیویی"),
        re.compile(r"سرخط\s+خبرها"),
        re.compile(r"قیمت\s+(سکه|طلا|دینار|درهم|نیم\s+سکه|ربع\s+سکه|سکه\s+گرمی).*امروز"),
        re.compile(r"قیمت\s+طلا(ی\s+(جهانی|۱۸\s+عیار|دست\s+دوم))?\s+امروز"),
    ]

    def _is_noise(title: str | None) -> bool:
        if not title:
            return False
        return any(p.search(title) for p in noise_patterns)

    noise_ids: list = []
    kept: list[Article] = []
    for a in articles:
        if _is_noise(a.title_fa) or _is_noise(a.title_original):
            noise_ids.append(a.id)
        else:
            kept.append(a)
    if noise_ids:
        logger.info(
            "Noise filter: retired %d periodic-format articles "
            "(radio bulletins / daily prices)", len(noise_ids)
        )
        await db.execute(
            update(Article)
            .where(Article.id.in_(noise_ids))
            .values(cluster_attempts=MAX_CLUSTER_ATTEMPTS)
        )
    articles = kept

    # Build source lookup from a separate explicit query rather than the
    # ORM relationship attribute. The earlier joinedload(Article.source)
    # pattern occasionally surfaced as
    # `greenlet_spawn has not been called; can't call await_only() here`
    # in production hourly runs (2026-04-28 15:23 / 16:23) — likely an
    # ORM lazy-load fired after the SQLAlchemy session went into a state
    # where relationship I/O wasn't allowed. A plain SELECT into a dict
    # cannot trigger lazy loading.
    source_id_set = {a.source_id for a in articles if a.source_id is not None}
    source_lookup: dict = {}
    if source_id_set:
        src_q = await db.execute(
            select(Source.id, Source.name_en, Source.state_alignment)
            .where(Source.id.in_(source_id_set))
        )
        source_lookup = {sid: (name, alignment) for sid, name, alignment in src_q.all()}

    source_names: dict[str, str] = {}
    source_alignments_map: dict[str, str | None] = {}
    for a in articles:
        aid = str(a.id)
        info = source_lookup.get(a.source_id) if a.source_id else None
        source_names[aid] = info[0] if info else "Unknown"
        source_alignments_map[aid] = info[1] if info else None

    if not articles:
        logger.info("No unclustered articles found — nothing to do")
        return {
            "matched_to_existing": 0,
            "new_stories_created": 0,
            "new_stories_hidden": 0,
            "merged": 0,
            "unclustered": 0,
        }

    total_articles = len(articles)
    logger.info(f"Found {total_articles} unclustered articles from the last 30 days")

    # ── Step 2: Match new articles to existing stories ──
    # Each phase below wraps its own try/except with a phase tag so the
    # harness's persisted error makes clear *which* phase the failure
    # came from, not just the SQLAlchemy message at top level. The
    # 2026-04-29 cluster `greenlet_spawn` errors had no stack-trace
    # locality — adding intermediate commits also persists matched
    # articles before the much-longer cluster_new phase runs, so a
    # later-phase failure doesn't roll back the matches.
    try:
        unmatched_ids = await _match_to_existing_stories(
            db, articles, source_names, deadline_ts=deadline_ts,
        )
        await db.commit()
    except Exception as _e:
        raise RuntimeError(f"cluster_phase=match_existing: {type(_e).__name__}: {_e}") from _e
    matched_count = total_articles - len(unmatched_ids)
    logger.info(
        f"Step 2 complete: {matched_count} matched to existing, "
        f"{len(unmatched_ids)} still unmatched"
    )

    # ── Step 3: Cluster unmatched articles into new stories ──
    # Re-fetch unmatched articles fresh from the DB. The input `articles`
    # list may now contain expired ORM objects from a keepalive rollback
    # inside the match phase — passing them to _cluster_new_articles
    # causes greenlet_spawn at the first attribute access (observed in
    # _dedup_signature on 2026-04-30 runs). Fresh fetch sidesteps the
    # whole expiration issue.
    try:
        if unmatched_ids:
            unmatched_result = await db.execute(
                select(Article).where(Article.id.in_(unmatched_ids))
            )
            unmatched = list(unmatched_result.scalars().all())
        else:
            unmatched = []
        new_published, new_hidden = await _cluster_new_articles(
            db, unmatched, source_names, source_alignments_map,
            deadline_ts=deadline_ts,
        )
        await db.commit()
    except Exception as _e:
        raise RuntimeError(f"cluster_phase=cluster_new: {type(_e).__name__}: {_e}") from _e

    # ── Step 4: Promote hidden stories that now have 5+ articles ──
    # (No is_published column — the API filters by article_count >= 5.
    #  But we log how many stories crossed the threshold after this run.)
    promoted_result = await db.execute(
        select(func.count(Story.id)).where(Story.article_count >= 5)
    )
    total_visible = promoted_result.scalar() or 0
    logger.info(f"Total visible stories (article_count >= 5): {total_visible}")

    # ── Step 5a: Cheap cosine pre-merge for near-duplicate tinies ──
    # This runs before the LLM merge so the candidate pool handed to
    # the LLM is smaller (and the obvious dupes are already handled
    # for free).
    try:
        pre_merged = await _merge_tiny_by_cosine(db)
        await db.commit()
    except Exception as _e:
        raise RuntimeError(f"cluster_phase=merge_tiny: {type(_e).__name__}: {_e}") from _e

    # ── Step 5b: LLM-based merge of surviving hidden stories ──
    try:
        merged_count = pre_merged + await _merge_hidden_stories(db)
        await db.commit()
    except Exception as _e:
        raise RuntimeError(f"cluster_phase=merge_hidden: {type(_e).__name__}: {_e}") from _e

    # Count remaining unclustered after all steps
    unclustered_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
        )
    )
    unclustered_count = unclustered_result.scalar() or 0

    # Orphans that aged past the 30-day window — these will never cluster again
    # without a manual reset. Surface the number so ops can notice drift.
    orphan_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.story_id.is_(None),
            Article.ingested_at < cutoff,
        )
    )
    aged_orphans = orphan_result.scalar() or 0

    # Retired orphans — in-window articles that hit MAX_CLUSTER_ATTEMPTS
    # without forming a viable group. Tracked for cost-visibility; these
    # no longer cost LLM dollars because they're filtered out of step 1.
    retired_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
            Article.cluster_attempts >= MAX_CLUSTER_ATTEMPTS,
        )
    )
    retired_orphans = retired_result.scalar() or 0
    if aged_orphans > 0:
        logger.warning(
            "%d articles have story_id=NULL and ingested >30d ago — "
            "outside the clustering window; consider manual review",
            aged_orphans,
        )

    # ── Capture tier snapshot before the update so we can emit events
    #    for each story whose tier promoted this pass. Only fetching the
    #    handful currently > 0 — the UPDATE below either lifts them or
    #    leaves them; stories at tier 0 that promote will surface in the
    #    "after" delta fetch.
    pre_tier_rows = await db.execute(text(
        "SELECT id, review_tier FROM stories WHERE frozen_at IS NULL"
    ))
    pre_tier = {row[0]: row[1] or 0 for row in pre_tier_rows.all()}

    # ── Guardrails: update review_tier on actively-growing stories ──
    # Size-based tiers fire on article_count. Age-based tiers fire only
    # when the story is BOTH (a) older than the threshold AND (b) still
    # being updated past its DB-creation date (last_updated > created+3d).
    # The second condition filters out one-off late backdated additions
    # and stories that simply got 1 legit article on day 0 and then went
    # silent for a week — those shouldn't drag into the review queue.
    # Frozen stories keep their tier; 24h filter prevents constant re-flagging.
    await db.execute(text(
        """
        UPDATE stories SET review_tier = GREATEST(
          CASE
            WHEN article_count >= 200 THEN 3
            WHEN article_count >= 150 THEN 2
            WHEN article_count >= 100 THEN 1
            ELSE 0
          END,
          CASE
            WHEN last_updated_at > created_at + interval '3 days' THEN (
              CASE
                WHEN (last_updated_at - created_at) >= interval '7 days' THEN 3
                WHEN (last_updated_at - created_at) >= interval '5 days' THEN 2
                WHEN (last_updated_at - created_at) >= interval '3 days' THEN 1
                ELSE 0
              END
            )
            ELSE 0
          END,
          -- Single-source flag: stories with only one source and >=5
          -- articles are never plural coverage. Tier-1 flag for HITL
          -- review (merge into broader story or freeze + hide).
          CASE
            WHEN source_count = 1 AND article_count >= 5 THEN 1
            ELSE 0
          END
        )
        WHERE frozen_at IS NULL
          AND last_updated_at >= now() - interval '24 hours'
        """
    ))
    tier_counts = {}
    for t in (1, 2, 3):
        r = await db.execute(text(
            "SELECT COUNT(*) FROM stories WHERE review_tier = :t AND frozen_at IS NULL"
        ), {"t": t})
        tier_counts[t] = r.scalar() or 0
    if tier_counts.get(3, 0) > 0:
        logger.warning(
            "Guardrails: %d stories at tier 3 (propose freeze), "
            "%d at tier 2, %d at tier 1",
            tier_counts[3], tier_counts[2], tier_counts[1],
        )

    # Emit tier_promoted events for each story that stepped up this pass.
    post_rows = await db.execute(text(
        "SELECT id, review_tier, article_count "
        "FROM stories WHERE review_tier > 0 AND frozen_at IS NULL"
    ))
    from app.services.events import log_event as _le_tier
    for sid, new_tier, ac in post_rows.all():
        old_tier = pre_tier.get(sid, 0) or 0
        if (new_tier or 0) > old_tier:
            await _le_tier(
                db,
                event_type="tier_promoted",
                actor="pipeline",
                story_id=sid,
                signals={
                    "from_tier": int(old_tier),
                    "to_tier": int(new_tier),
                    "article_count": int(ac or 0),
                },
            )

    await db.commit()

    stats = {
        "matched_to_existing": matched_count,
        "new_stories_created": new_published,
        "new_stories_hidden": new_hidden,
        "merged": merged_count,
        "unclustered": unclustered_count,
        "aged_orphans": aged_orphans,
        "retired_orphans": retired_orphans,
    }
    logger.info(f"Incremental clustering complete: {stats}")
    return stats


# ---------------------------------------------------------------------------
# Phase 3: cluster health audit
# ---------------------------------------------------------------------------


async def audit_cluster_coherence(
    db: AsyncSession,
    *,
    min_articles: int = 10,
    sample_size: int = 4,
    pair_cosine_floor: float = 0.50,
) -> dict:
    """For every cluster of ≥ min_articles, sample a handful of articles
    and compute pairwise cosine similarity between their embeddings. If
    any pair falls below pair_cosine_floor the cluster is flagged as
    likely heterogeneous — mixed events slipped in, or topic drifted
    without splitting.

    Output rows are appended to Story.audit_notes (self-creating JSONB
    column) as {kind: "drift", detected_at, min_pair_cosine, reason}
    so Niloofar can surface them in the next audit and decide whether
    to split / prune / rename. We don't split automatically here —
    wrong splits are worse than silent drift.

    Pure-Python, no LLM calls. O(Σ stories × sample_size²) which is
    trivially fast at a few hundred stories.
    """
    from sqlalchemy import text as _text
    from app.nlp.embeddings import cosine_similarity as _cosine_sim

    # Self-heal the notes column in case a fresh environment hasn't run
    # the alembic migration yet. Idempotent.
    async with db.begin_nested() if db.in_transaction() else _nullctx():
        await db.execute(text(
            "ALTER TABLE stories ADD COLUMN IF NOT EXISTS audit_notes JSONB"
        ))

    q = await db.execute(
        select(Story.id, Story.title_fa, Story.article_count)
        .where(Story.article_count >= min_articles)
    )
    rows = q.all()

    flagged = 0
    checked = 0
    for sid, title_fa, _ac in rows:
        art_q = await db.execute(
            select(Article.id, Article.embedding, Article.title_fa)
            .where(Article.story_id == sid, Article.embedding.isnot(None))
            .order_by(Article.published_at.desc().nullslast())
            .limit(sample_size)
        )
        sample = [r for r in art_q.all() if r[1]]
        if len(sample) < 3:
            continue
        checked += 1

        pairs_below: list[tuple[float, str, str]] = []
        min_pair = 1.0
        for i in range(len(sample)):
            for j in range(i + 1, len(sample)):
                s = _cosine_sim(sample[i][1], sample[j][1])
                if s < min_pair:
                    min_pair = s
                if s < pair_cosine_floor:
                    pairs_below.append((s, sample[i][2] or "", sample[j][2] or ""))

        if pairs_below:
            flagged += 1
            note = {
                "kind": "drift",
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "min_pair_cosine": round(min_pair, 3),
                "pairs_below_floor": [
                    {"cosine": round(s, 3), "a": a[:80], "b": b[:80]}
                    for s, a, b in pairs_below[:3]
                ],
            }
            await db.execute(
                _text(
                    "UPDATE stories SET audit_notes = "
                    "COALESCE(audit_notes, '{}'::jsonb) || jsonb_build_object('cluster_drift', CAST(:note AS jsonb)) "
                    "WHERE id = :sid"
                ),
                {"note": __import__("json").dumps(note, ensure_ascii=False), "sid": sid},
            )
    await db.commit()
    return {"checked": checked, "flagged": flagged}


# Tiny helper for the ALTER TABLE guard above.
from contextlib import asynccontextmanager as _asynccontextmanager  # noqa: E402


@_asynccontextmanager
async def _nullctx():
    yield


# ---------------------------------------------------------------------------
# Phase 4: agglomerative-clustering experimental path
# ---------------------------------------------------------------------------


async def agglomerative_cluster_articles(
    db: AsyncSession,
    articles: list[Article],
    *,
    cosine_threshold: float = 0.75,
    max_time_gap_days: int = 5,
) -> list[set[uuid.UUID]]:
    """Build a similarity graph over `articles` and return connected
    components as candidate clusters. Two articles are linked when:
      cosine(embedding) ≥ cosine_threshold
      AND |published_at delta| ≤ max_time_gap_days
      AND (share ≥ 2 title tokens OR share a «…» quote OR share a number)

    Returns list of sets of article IDs. Each set is a candidate
    cluster — LLM is expected to verify and name them in a follow-up.

    This path is NOT wired into cluster_articles() by default. It's
    here as a building block that can be switched on via settings.clustering_mode
    = "agglomerative" once we've validated it offline against the
    current LLM-first pipeline. Rewriting the top-down matching flow
    end-to-end was out of scope for this commit; the function is the
    core primitive needed for that swap.
    """
    from app.nlp.embeddings import cosine_similarity as _cosine_sim

    items = [a for a in articles if a.embedding and any(v != 0.0 for v in (a.embedding or [])[:5])]

    # Precompute signals per article
    sigs: dict[uuid.UUID, dict] = {}
    for a in items:
        title = a.title_fa or a.title_original or ""
        sigs[a.id] = {
            "tokens": _title_tokens(title),
            "quotes": _quoted_phrases(title),
            "numbers": _number_tokens(title),
            "published_at": a.published_at,
        }

    # Union-find
    parent: dict[uuid.UUID, uuid.UUID] = {a.id: a.id for a in items}

    def find(x: uuid.UUID) -> uuid.UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: uuid.UUID, y: uuid.UUID) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i, a in enumerate(items):
        for b in items[i + 1:]:
            sim = _cosine_sim(a.embedding, b.embedding)
            if sim < cosine_threshold:
                continue
            pa, pb = sigs[a.id], sigs[b.id]
            # Time gap
            if pa["published_at"] and pb["published_at"]:
                gap = abs((pa["published_at"] - pb["published_at"]).total_seconds()) / 86400.0
                if gap > max_time_gap_days:
                    continue
            # Shared-signal gate
            shared_tokens = len(pa["tokens"] & pb["tokens"])
            shares_quote = bool(pa["quotes"] & pb["quotes"])
            shares_number = bool(pa["numbers"] & pb["numbers"])
            if shared_tokens >= 2 or shares_quote or shares_number:
                union(a.id, b.id)

    groups: dict[uuid.UUID, set[uuid.UUID]] = {}
    for aid in parent:
        root = find(aid)
        groups.setdefault(root, set()).add(aid)

    # Drop singletons — by definition not a cluster
    return [g for g in groups.values() if len(g) >= 2]
