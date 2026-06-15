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
from sqlalchemy import func, or_, select, text, update
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

# Pin floor: stories at or above this priority were manually pinned by an
# operator (the seed/PATCH endpoints use 50). Together with is_edited=True,
# these mark human-curated stories that auto-merge must NEVER touch — neither
# as a keeper (it would inherit a foreign article mix) nor as a victim (it
# would be deleted outright). Background (Parham 2026-06-06): the cron's
# merge_similar step absorbed a hand-seeded, priority-50 visa story into a
# 35-article war umbrella ("America rejected the football visas؛ four Iranian
# drones were shot down"), erasing the pin and the single-topic curation.
_MERGE_PIN_PRIORITY_FLOOR = 40


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

    Rolls back on ping failure to clear the aborted-transaction state
    that asyncpg leaves behind. SQLAlchemy 2's rollback expires
    in-session ORM objects, but that's now safe because cluster_articles
    uses a FRESH async_session() for each phase via _phase_session() —
    the expired objects from a previous phase never cross into the next.
    See _phase_session below for the structural fix.
    """
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"Keepalive ping failed: {e} — rolling back session")
        try:
            await db.rollback()
        except Exception as e2:
            logger.warning(f"Session rollback after failed keepalive also failed: {e2}")

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
   - Article about the SAME KIND of event in a DIFFERENT place/theater (e.g. US strikes a drug boat in the eastern Pacific vs. US strikes on Iran) → separate story, even if the wording is nearly identical
   - Two articles sharing only a BROAD THEME but about DIFFERENT subjects → separate. The death of singer Homa Mirafshar and Marilyn Monroe's 100th birthday are BOTH "a cultural figure" but are SEPARATE stories. "PS752 victims' families" and "a Taliban divorce law" both touch "families/regulation" but are SEPARATE stories. They must share the SAME specific person/place/incident, not just a category.
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
- GEOGRAPHY: the SAME TYPE of event in a DIFFERENT place is a DIFFERENT story, and must NOT be relabeled as the Iran one. Example: "US strikes a boat in the eastern Pacific / Latin America (drug interdiction)" is NOT about Iran — exclude it; never fold its casualty numbers into an Iran strike story.
- CRITICAL: Each group must be about ONE SINGLE specific event. Do NOT combine different events even if they are related. For example:
  - "Attack on Sharif University" and "Killing of IRGC Quds Force commander" are TWO SEPARATE stories, not one
  - "Missile attack on Tel Aviv" and "Missile attack on Isfahan" are TWO SEPARATE stories
  - "Dollar price today" and "Stock market crash" are TWO SEPARATE stories
  - Two DIFFERENT people's obituaries (e.g. singer Homa Mirafshar vs Marilyn Monroe) are SEPARATE stories — sharing the theme "a cultural figure died" is NOT enough
  - Articles sharing only a broad category (aviation, families, weather, sports) but about different specific events are SEPARATE
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
    *,
    last_updated_at: datetime | None = None,
    frozen_at: datetime | None = None,
) -> float:
    """Cycle-4 (2026-05-08): now a thin shim around the canonical
    `app.services.trending.compute_trending_score`. Pre-this-fix,
    this function used `0.5^(hours/48)` (2-day half-life, anchored on
    first_published_at) while `step_recalculate_trending` used
    `0.85^days` (~4.3-day half-life, anchored on
    frozen_at??last_updated_at??first_published_at). Same Story column,
    different formulas, 3.6x divergence in scale — homepage rank
    flickered between cron passes (which used the canonical formula)
    and interim writes from `_refresh_stories_metadata_batch` /
    `match_existing` / `merge_similar` / HITL ops.

    The canonical formula is now the second one (matches scheduled
    recalc, anchors on the editorial-intent fields). See
    `app/services/trending.py` for design rationale.

    Most callers in this module pass only article_count and
    first_published — the keyword args are for the few sites that
    have the richer story state.
    """
    from app.services.trending import compute_trending_score
    return compute_trending_score(
        article_count=article_count,
        last_updated_at=last_updated_at,
        frozen_at=frozen_at,
        first_published_at=first_published,
        source_count=source_count,
    )


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

    Accepts either ORM Article objects OR primitive dicts (with keys
    matching Article column names). _cluster_new_articles passes dicts
    captured eagerly to dodge ORM expiration; _match_to_existing_stories
    passes ORM objects.

    Title + first ~150 chars of content is enough for the LLM to group
    by specific event. 400 chars was overkill for a grouping task and
    doubled token cost with no measurable quality win.

    source_names: optional pre-extracted mapping of article.id -> source name
    """
    def _g(obj, key):
        # Field accessor that works for both dict and ORM object.
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

    lines = []
    for i, article in enumerate(articles, 1):
        title = _g(article, "title_original") or _g(article, "title_fa") or _g(article, "title_en") or "(no title)"
        if source_names:
            sname = source_names.get(str(_g(article, "id")), "Unknown")
        else:
            sname = "Unknown"
        body = (_g(article, "content_text") or _g(article, "summary") or "").strip()
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


# ── Layer 2: headline grounding check (2026-05-31) ─────────────────────
# Even with the Layer 1 geo gate, a contaminated cluster (or an over-eager
# title model) can produce a headline that fuses a NUMBER from one article
# onto a SUBJECT from another — the «۲۰۰ کشته در حملات به شناورهای ایرانی»
# failure, where the 200 came from eastern-Pacific drug-boat strikes, not
# Iran. This check runs ONLY when a generated title contains a number
# (where dangerous composites happen), so cost stays near zero, and
# rewrites the headline to drop any unsupported figure/subject.
GROUNDING_PROMPT = """\
You are a meticulous Persian-language fact-checking news editor.

A proposed headline (تیتر) was generated to summarize a cluster of news \
articles. Verify it ONLY against the SOURCE HEADLINES below — assume nothing \
that is not written there.

Proposed headline:
{title}

Source headlines:
{articles_block}

Check, in order:
1. Every NUMBER in the proposed headline (casualty counts, amounts, dates) must \
appear in at least one source headline AND be attached to the SAME subject/event. \
A number describing one event must NOT be attached to a different subject or place.
2. Every named SUBJECT, PLACE, or ACTOR in the proposed headline must be supported \
by at least one source headline.

Return ONLY valid JSON:
{{"grounded": true_or_false, "reason": "short Persian explanation", "corrected_title_fa": "..."}}

- If everything is supported → grounded=true and corrected_title_fa = the original headline unchanged.
- If a number or subject is NOT supported → grounded=false and corrected_title_fa = a faithful, specific Persian headline that REMOVES or CORRECTS the unsupported claim (no questions, no vague summaries).
"""


async def _call_openai_grounding(prompt: str) -> dict | None:
    """Cheap-tier (gpt-4.1-nano) JSON call for the headline grounding
    check. Returns the parsed dict, or None on ANY failure — no silent
    fallback: the caller keeps the original title and logs when this is
    None, rather than trusting a fabricated 'grounded' verdict."""
    if not settings.openai_api_key:
        return None
    from app.services.llm_helper import build_openai_params
    from app.services.llm_usage import log_llm_usage

    def _sync_call():
        client = OpenAI(api_key=settings.openai_api_key)
        try:
            params = build_openai_params(
                model=settings.content_type_model,
                prompt=prompt,
                max_tokens=400,
                temperature=0,
            )
            response = client.chat.completions.create(**params)
            return _parse_llm_response(response.choices[0].message.content), response.usage
        except Exception as e:
            logger.error(f"Title grounding LLM error: {e}")
            return None, None

    parsed, usage = await asyncio.get_event_loop().run_in_executor(None, _sync_call)
    if usage is not None:
        await log_llm_usage(
            model=settings.content_type_model,
            purpose="clustering.title_grounding",
            usage=usage,
        )
    return parsed or None


async def verify_title_grounding(title_fa: str, article_titles: list[str]) -> str:
    """Layer 2 — return a headline whose hard claims are grounded in the
    cluster's source headlines.

    No-op (returns the original) unless the title contains a NUMBER — that
    is where fabricated composites (a casualty figure from the wrong
    event) occur, and number-gating keeps this near-free. Best-effort:
    a missing key, an LLM error, or an empty article list returns the
    original title unchanged — we never block cluster creation on it."""
    if not title_fa or not _number_tokens(title_fa):
        return title_fa
    titles = [t.strip() for t in article_titles if t and t.strip()][:12]
    if not titles:
        return title_fa
    block = "\n".join(f"- {t}" for t in titles)
    result = await _call_openai_grounding(
        GROUNDING_PROMPT.format(title=title_fa, articles_block=block)
    )
    if not result:
        logger.warning("Title grounding check unavailable; keeping original title")
        return title_fa
    if result.get("grounded") is True:
        return title_fa
    corrected = (result.get("corrected_title_fa") or "").strip()
    if corrected and corrected != title_fa:
        logger.info(
            "Title grounding rewrote a headline (reason: %s): %r -> %r",
            result.get("reason", ""), title_fa, corrected,
        )
        return corrected
    return title_fa


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


# ── Layer 1: geographic-theater gate (2026-05-31) ──────────────────────
# The embedding matcher is blind to geography: "US strikes a boat, N
# killed" reads the same whether it's the Iran/Persian-Gulf theater or
# US drug-interdiction strikes in the eastern Pacific / Latin America.
# That blindness merged an eastern-Pacific drug-boat article (cumulative
# "200 killed") into an Iran-strikes story, and the headline generator
# fused them into the FALSE «حمله آمریکا به شناورهای ایرانی؛ ۲۰۰ کشته».
#
# This lexicon tags text with a coarse THEATER. Ubiquitous actors that
# appear across every theater (USA, Trump, "America") are deliberately
# EXCLUDED — they don't discriminate. Iran-entangled regions (Levant:
# Gaza/Israel/Lebanon/Syria; Europe, where the diaspora lives) are also
# excluded so a normal Iran-axis story is never wrongly split. The gate
# only acts on CLEARLY non-Iran theaters where a cross-merge is almost
# always an error.
_THEATER_LEXICON: dict[str, tuple[str, ...]] = {
    "iran": (
        "ایران", "تهران", "بندرعباس", "هرمز", "خلیج فارس", "سپاه",
        "خامنه", "نطنز", "فردو", "اصفهان", "مشهد", "تبریز", "شیراز",
        "پزشکیان", "irgc", "tehran", "iran", "bandar abbas", "hormuz",
    ),
    "americas": (
        "اقیانوس آرام", "آمریکای لاتین", "ونزوئلا", "کارائیب", "کلمبیا",
        "اکوادور", "پاناما", "مکزیک", "کارتل", "مواد مخدر", "قاچاق مواد",
        "pacific", "venezuela", "caribbean", "latin america", "colombia",
        "cartel", "drug traffic", "drug boat", "southcom",
    ),
    "ukraine_russia": (
        "اوکراین", "روسیه", "مسکو", "کی‌یف", "کیف", "پوتین", "زلنسکی",
        "ukraine", "russia", "moscow", "kyiv", "putin", "zelensk",
    ),
    "east_asia": (
        "تایوان", "کره شمالی", "کره جنوبی", "پکن", "ژاپن",
        "taiwan", "north korea", "south korea", "beijing",
    ),
    "south_asia": (
        "پاکستان", "افغانستان", "کابل", "هند", "کشمیر",
        "pakistan", "afghanistan", "kabul", "kashmir",
    ),
}


def _locus_set(text: str | None) -> set[str]:
    """Tag text with the coarse geographic theaters it references.

    Substring match on a curated bilingual lexicon. Returns the set of
    theater keys present (often empty for generic text, occasionally
    several). Empty result = "no strong geographic signal" → the gate
    stays silent (conservative)."""
    if not text:
        return set()
    t = text.replace("‌", " ").lower()
    out: set[str] = set()
    for theater, markers in _THEATER_LEXICON.items():
        for m in markers:
            if m in t:
                out.add(theater)
                break
    return out


def _locus_conflict(a_loci: set[str], b_loci: set[str]) -> bool:
    """True when both sides carry a geographic signal and they are
    DISJOINT — i.e. they're about different theaters of the world.

    Conservative by construction: if either side has no locus tag, this
    returns False (no conflict), so generic articles are never blocked.
    Only fires when both name a theater and share none — the exact shape
    of the eastern-Pacific-vs-Iran mis-merge."""
    return bool(a_loci) and bool(b_loci) and a_loci.isdisjoint(b_loci)


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

    # Only consider articles that actually have non-trivial embeddings.
    # Cycle-1 audit Phase B: the prior `any(v != 0.0 for v in e[:5])`
    # check could be fooled by a vector with first 5 dims zero but rest
    # non-zero. Using L2-norm > epsilon catches all-near-zero vectors
    # regardless of which dimensions hold the residual noise.
    def _is_nontrivial_embedding(e):
        if not e:
            return False
        try:
            s = sum(v * v for v in e)
        except (TypeError, ValueError):
            return False
        return s > 0.01  # ~0.1 magnitude floor; real embeddings are ~1
    embedded = [a for a in articles if _is_nontrivial_embedding(a.embedding)]
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
            "loci": _locus_set(title),  # #6 geo-gate in the union-find too
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
            # #6 — never union across geographic theaters even at high cosine
            # (e.g. an eastern-Pacific drug-boat strike with an Iran-strikes
            # article). Mirrors the match-to-existing locus gate.
            if _locus_conflict(sigs[a_i.id]["loci"], sigs[a_j.id]["loci"]):
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
    # Past 5 days, tighten further — the cluster is approaching the 7d
    # freeze cliff. Once frozen (step_archive_stale), no new articles
    # can join at all. The 5-7d window is the last chance for accretion
    # and benefits from extra friction so fresh-but-tangentially-similar
    # articles spawn new stories instead of squeezing onto a soon-to-be-
    # frozen umbrella. Catches the same drift pattern as the 5adc903e
    # incident (Apr 10 cluster grew to 30 articles spanning unrelated
    # topics over 24 days; many attached during its 5-7d window before
    # freeze should have fired).
    EMBEDDING_SIM_THRESHOLD_NEAR_FREEZE = 0.65
    NEAR_FREEZE_CANDIDATE_DAYS = 5
    AUTO_MATCH_COSINE = 0.85
    # Raised 0.60 → 0.63 (2026-06-03 clustering-quality pass). The 0.60-0.85
    # LLM band was rubber-stamping same-theme-different-event pairs (two
    # celebrity obituaries, PS752 vs Taliban). The shared-anchor gate below
    # (#1) is the primary fix; this modest bump shrinks the permissive band
    # so fewer borderline pairs ever reach the LLM. Kept conservative to
    # avoid over-fragmenting legitimate fresh-story accretion.
    AUTO_REJECT_COSINE = 0.63
    AUTO_MATCH_JACCARD = 0.35
    AUTO_MATCH_MAX_AGE_DAYS = 2
    AUTO_REJECT_MAX_AGE_DAYS = 7
    # Cycle-1 audit Island 3: assert the band is non-degenerate. If a
    # future tune flips them, every article would either auto-reject or
    # auto-match with no LLM in the middle — not the intended behavior.
    assert AUTO_REJECT_COSINE < AUTO_MATCH_COSINE, (
        "AUTO_REJECT_COSINE must be < AUTO_MATCH_COSINE"
    )

    # F4 — never attach a new article to a story that hasn't been
    # touched in 10 days. The site's editorial intent: anything older
    # is dead context. Resurrecting a 2-week-old thread with one
    # straggler creates "thread-zombie" stories that look fresh but
    # carry stale narratives. The new article seeds its own story
    # instead. Tighter than `settings.clustering_time_window_days`
    # (which existed for legacy reasons); we pick the stricter of
    # the two.
    # 7-day data window (Parham 2026-05-09): match-existing only
    # considers articles ≤ 7 days old. Was 10. See `clustering.py`
    # cluster_articles cutoff comment for full rationale.
    AGE_CAP_DAYS = 7
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
    # Aligned 2026-05-02 with the 7d freeze-by-creation rule. Frozen
    # stories already get filtered via Story.frozen_at.is_(None) in the
    # query below, but we also gate on first_published_at directly so
    # the matcher refuses old stories even during the brief window
    # between maintenance runs (when a story has crossed 7d but
    # step_archive_stale hasn't fired yet to set frozen_at).
    UMBRELLA_FIRST_PUB_CAP_DAYS = 7
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
            # Catch-22 break (Parham 2026-06-05): the floor used to be >= 5, but
            # a freshly-formed story can't REACH 5 if nothing can match into it —
            # so post-war, fresh news fragmented into tiny hidden stories that
            # could never grow, matched_to_existing went to 0, existing stories
            # stopped updating, and the homepage froze 4 days stale. Lowered to
            # >= 3 so a small recent story can accumulate toward visibility
            # (3 → 4 visible → 5+), while keeping enough articles for a stable
            # centroid. Quality is still gated by cosine + the STRICTER
            # small-story anchor floor (jaccard >= 0.15, line ~1280) and the
            # 7-day umbrella/last_updated caps below.
            Story.article_count >= 3,
            # Pinned-hero feed exemption (Parham 2026-06-15): a story at/above
            # the pin floor is the operator's explicit "this is THE canonical
            # story." Let fresh (≤7d) articles keep joining it past the
            # max_cluster_size + umbrella first-pub caps instead of fragmenting
            # one fast event into parallel clusters (the Iran–US deal split into
            # 6). Non-pinned stories still chapter at 7d / max_cluster_size, so
            # the runaway-umbrella protection is untouched for anything the
            # operator hasn't curated. The ≤7-day ARTICLE window (time_cutoff /
            # AGE_CAP_DAYS) is UNCHANGED — stale articles still never cluster;
            # this only widens which EXISTING stories are eligible match targets.
            or_(
                Story.priority >= _MERGE_PIN_PRIORITY_FLOOR,
                Story.article_count < settings.max_cluster_size,
            ),
            Story.last_updated_at >= time_cutoff,
            Story.frozen_at.is_(None),
            # F3 — archived stories are never resurrected.
            Story.archived_at.is_(None),
            # Umbrella cap: drop stories whose first article is older
            # than the cutoff. Their continued growth signals editorial
            # sprawl, not a coherent thread.
            # Loophole closed 2026-05-03 (Parham): the prior NULL-tolerant
            # form `(first_published_at IS NULL OR first_published_at >= cutoff)`
            # let articles attach to ancient NULL-dated zombie stories
            # (clustering audit found this could absorb fresh articles
            # into 3-year-old stories). Now: NULL falls back to
            # `created_at`, so the umbrella cap applies uniformly.
            # `step_archive_stale` already backfills first_published_at
            # from MIN(article.published_at), so legitimate new stories
            # always have a real value before this gate fires.
            or_(
                Story.priority >= _MERGE_PIN_PRIORITY_FLOOR,
                func.coalesce(Story.first_published_at, Story.created_at)
                >= umbrella_cutoff,
            ),
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
        # Cycle-4 (2026-05-08): tuple return — cycle-3 fix `0f3a383`
        # forgot the early-exit paths and only updated the final
        # return. Callers do `unmatched_ids, count = await ...` and
        # would crash with ValueError on a list-shaped return.
        return article_ids_eager, 0

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
    # Two query forms (per 2026-05-03 audit — the prior single-query
    # form missed unresolved flags because it required
    # orphaned_from_story_id IS NOT NULL):
    #   1. Resolved flags — use the recorded `orphaned_from_story_id`.
    #   2. Unresolved flags (still "open" in HITL queue) — join the
    #      article's CURRENT story_id. This makes the rejection take
    #      effect immediately rather than waiting for niloofar's audit.
    anon_rej_resolved_q = await db.execute(
        select(_IF.target_id, _IF.orphaned_from_story_id).where(
            _IF.target_type == "article",
            _IF.issue_type == "wrong_clustering",
            _IF.orphaned_from_story_id.isnot(None),
            _IF.created_at >= rejection_cutoff,
        )
    )
    # Two-step: collect open-flag target ids (stored as String), then
    # look up their current story_id via a separate UUID-typed query.
    # Direct JOIN on String == UUID would fail at the SQL level.
    open_flag_ids_q = await db.execute(
        select(_IF.target_id).where(
            _IF.target_type == "article",
            _IF.issue_type == "wrong_clustering",
            _IF.status == "open",
            _IF.orphaned_from_story_id.is_(None),
            _IF.created_at >= rejection_cutoff,
        )
    )
    open_flag_ids: list = []
    import uuid as _uuid
    for (tid,) in open_flag_ids_q.all():
        if not tid:
            continue
        try:
            open_flag_ids.append(_uuid.UUID(tid))
        except (ValueError, TypeError):
            continue
    anon_rej_open_pairs: list = []
    if open_flag_ids:
        open_lookup_q = await db.execute(
            select(Article.id, Article.story_id).where(
                Article.id.in_(open_flag_ids),
                Article.story_id.isnot(None),
            )
        )
        anon_rej_open_pairs = list(open_lookup_q.all())
    rejected_pairs: set[tuple[str, str]] = set()
    for art_id, sid in rater_rej_q.all():
        if art_id and sid:
            rejected_pairs.add((str(art_id), str(sid)))
    for art_id_str, sid in anon_rej_resolved_q.all():
        if art_id_str and sid:
            rejected_pairs.add((str(art_id_str), str(sid)))
    for art_id, sid in anon_rej_open_pairs:
        if art_id and sid:
            rejected_pairs.add((str(art_id), str(sid)))
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
            "loci": _locus_set(corpus),  # Layer 1 geographic-theater gate
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
    anchor_block_count = 0          # #1 shared-anchor gate rejects (no shared entity/token/number)
    locus_block_count = 0           # Layer 1 geographic-theater rejects
    locus_blocks: list[tuple] = []  # (article_id, story_id) for the event log
    # Cycle-1 audit Island 3: count which threshold tier was selected
    # for each candidate pair so the dashboard can spot tier-distribution
    # drift (e.g. all candidates suddenly land in the strict
    # near_freeze tier = stories aging out faster than expected).
    threshold_tier_counts: dict = {
        "small_story": 0,    # target.article_count < 10 → 0.45
        "near_freeze": 0,    # age_days >= NEAR_FREEZE_CANDIDATE_DAYS
        "aged": 0,           # age_days > AGED_CANDIDATE_DAYS
        "fresh": 0,          # default tier
    }
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
        # Bad-embedding guard. Tightened 2026-05-03 (Parham, audit):
        # the prior check `not article.embedding or not any(...)`
        # treats `[]` and `[0.0]*N` as bad, but ALSO treats `None` as
        # bad — that's correct. The audit flagged that `[]` (empty list)
        # is technically truthy-falsy in different paths; explicit
        # length + non-zero check eliminates ambiguity. Articles
        # landing here get their `cluster_attempts` bumped via the
        # outer `articles_without_embedding` path, eventually orphaning
        # — which is the right outcome for irrecoverable embeddings.
        emb = article.embedding
        is_bad = (
            not emb
            or not isinstance(emb, list)
            or len(emb) == 0
            or not any(v != 0.0 for v in emb[:5])
        )
        if is_bad:
            articles_without_embedding.append(article)
            continue

        a_title = article.title_fa or article.title_original or ""
        a_tokens = _title_tokens(a_title)
        a_quotes = _quoted_phrases(a_title)
        a_numbers = _number_tokens(a_title)
        a_loci = _locus_set(a_title)  # Layer 1 geographic-theater gate

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

            # Layer 1 — geographic-theater gate (2026-05-31). Even at very
            # high cosine, a cross-theater pairing (e.g. eastern-Pacific
            # drug-boat strikes vs an Iran-strikes story) is almost always
            # a mis-merge the embedding can't see. Skip this story entirely
            # for this article — it can still form its own cluster or match
            # a same-theater story. Mirrors the prompt's "REJECTION IS THE
            # DEFAULT" stance. Conservative: only fires when BOTH sides name
            # a theater and share none.
            if _locus_conflict(a_loci, sig.get("loci") or set()):
                locus_block_count += 1
                if len(locus_blocks) < 50:
                    locus_blocks.append((article.id, story_id))
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
                threshold_tier_counts["small_story"] += 1
            elif age_days >= NEAR_FREEZE_CANDIDATE_DAYS:
                # 5-7d band: tightest accretion gate before freeze.
                base_threshold = EMBEDDING_SIM_THRESHOLD_NEAR_FREEZE
                threshold_tier_counts["near_freeze"] += 1
            elif age_days > AGED_CANDIDATE_DAYS:
                base_threshold = EMBEDDING_SIM_THRESHOLD_AGED
                threshold_tier_counts["aged"] += 1
            else:
                base_threshold = EMBEDDING_SIM_THRESHOLD
                threshold_tier_counts["fresh"] += 1
            effective_threshold = min(base_threshold * trust_factor, 0.95)
            if sim >= effective_threshold:
                # #1 shared-anchor gate (2026-06-03 clustering-quality pass):
                # EVERY LLM candidate must share at least one concrete identity
                # anchor with the story — a content token (entity/place/
                # distinctive word, stopwords already stripped by _title_tokens),
                # a «quoted» phrase, or a number. Embeddings capture THEME
                # ("celebrity death", "aviation, families"), so without this gate
                # the 0.63-0.85 band glued different EVENTS that share a theme:
                # «هما میرافشار» + «مرلین مونرو», «خانواده‌های ۷۵۲» + Taliban
                # divorce law. Small stories keep the stricter jaccard≥0.15
                # floor; all others require ≥1 shared content token. The LLM
                # still confirms — this only stops it from ever seeing
                # anchorless same-theme pairs it tends to rubber-stamp.
                s_tokens = sig.get("tokens") or set()
                shared_quote = bool(a_quotes & (sig.get("quotes") or set()))
                shared_number = bool(a_numbers & (sig.get("numbers") or set()))
                if target_small:
                    has_anchor = (
                        _jaccard(a_tokens, s_tokens) >= 0.15
                        or shared_quote or shared_number
                    )
                else:
                    has_anchor = (
                        len(a_tokens & s_tokens) >= 1
                        or shared_quote or shared_number
                    )
                if not has_anchor:
                    anchor_block_count += 1
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
        f"geo-theater-blocked: {locus_block_count}, "
        f"to LLM: {len(article_candidates)} articles × {total_candidate_pairs} pairs "
        f"(+{len(articles_without_embedding)} without embedding), "
        f"{len(articles) - pre_filtered_articles - auto_match_count} articles → new cluster"
    )
    # Cycle-1 audit Island 3: surface threshold-tier distribution.
    if any(threshold_tier_counts.values()):
        logger.info(f"Threshold tiers: {threshold_tier_counts}")
    # Cycle-1 audit Island 3: per-source breakdown of embedding-less
    # articles. Lets operators spot when one source's NLP pipeline is
    # silently failing while others work fine.
    if articles_without_embedding:
        from collections import Counter as _Counter
        by_source = _Counter(
            (str(a.source_id) if a.source_id else "unknown")
            for a in articles_without_embedding
        )
        if len(by_source) > 1 or any(v > 5 for v in by_source.values()):
            logger.warning(
                "Articles without embedding by source_id: %s",
                dict(by_source.most_common()),
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
    for art_id, sid in locus_blocks[:50]:
        await _log_event(
            db,
            event_type="cluster_block_geo_theater",
            actor="clustering",
            story_id=sid,
            article_id=art_id,
            signals={"reason": "cross_theater_geography_conflict"},
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
        # Cycle-4 (2026-05-08): tuple return for the same reason as
        # the L751 early-exit. `auto_match_pairs` already moved some
        # articles into matched_article_ids, so unmatched is the
        # complement. Articles that didn't make article_candidates
        # AND aren't in articles_without_embedding fell through entirely
        # — they're "unmatched" too.
        unmatched_ids = [
            aid for aid in article_ids_eager if aid not in matched_article_ids
        ]
        return unmatched_ids, len(article_candidates)

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
        # Cycle-1 audit Phase B (admin-freeze race): the LLM phase
        # took several minutes during which an admin may have manually
        # frozen one of the candidate stories via /admin/hitl/.../freeze.
        # Without a re-check, those assignments would resurrect a frozen
        # story (bumping last_updated_at, putting it back on the home-
        # page). Verify with one bulk SELECT and drop affected pairs.
        story_ids_in_flight = {sid for _aid, sid in matched_pairs if sid is not None}
        if story_ids_in_flight:
            still_open = await db.execute(
                select(Story.id).where(
                    Story.id.in_(story_ids_in_flight),
                    Story.frozen_at.is_(None),
                    Story.archived_at.is_(None),
                )
            )
            open_set = {row[0] for row in still_open.all()}
            stale_pairs = [
                (aid, sid) for aid, sid in matched_pairs
                if sid not in open_set
            ]
            if stale_pairs:
                logger.warning(
                    "match_existing: dropping %d article→story matches "
                    "where the story was frozen/archived mid-phase: %s",
                    len(stale_pairs),
                    [str(sid) for _, sid in stale_pairs[:5]],
                )
                stale_article_ids = {aid for aid, _ in stale_pairs}
                # Roll back the in-memory assignments — set story_id = None
                # so the flush doesn't write them.
                for art in articles:
                    if art.id in stale_article_ids:
                        art.story_id = None
                matched_pairs = [
                    (aid, sid) for aid, sid in matched_pairs
                    if sid in open_set
                ]
                matched_article_ids = {aid for aid, _ in matched_pairs}
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
    #
    # Cycle-3 fix (2026-05-08): also surface llm_candidates_sent so the
    # caller can include it in the cluster stats. Cycle-1 commit
    # 6abc775 added a stats reference to `article_candidates` in the
    # caller scope, but the variable lives only here — every cron
    # since 6abc775 deployed has hit `NameError: article_candidates`
    # at the cluster step. Tuple return surfaces the count cleanly.
    unmatched_ids = [aid for aid in article_ids_eager if aid not in matched_article_ids]
    return unmatched_ids, len(article_candidates)


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

    # Cycle-4: pass last_updated_at + frozen_at so the canonical
    # formula (anchored on the editorial-intent fields) doesn't see
    # a diverged value here.
    story.trending_score = _compute_trending_score(
        story.article_count,
        story.first_published_at,
        story.source_count,
        last_updated_at=story.last_updated_at,
        frozen_at=story.frozen_at,
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

    # 1. Load all affected Story ORM objects in one query.
    # Cycle-3 audit (2026-05-08): cycle-1 commit 7e6fa46 added defers
    # to the three merge functions but missed this batch helper. Each
    # full Story row carries ~70-80 KB of heavy JSONB
    # (translations / telegram_analysis / editorial_context_fa /
    # summary_anchor / analysis_snapshot_24h / summary_en /
    # hourly_update_signal). The function only reads summary_fa and
    # is_edited; the heavy columns ride along uselessly. At 50
    # affected stories per cluster pass × 3 daily crons = ~12 MB/day
    # wasted egress before this defer.
    from sqlalchemy.orm import defer as _defer_refresh
    story_result = await db.execute(
        select(Story)
        .options(
            _defer_refresh(Story.translations),
            _defer_refresh(Story.telegram_analysis),
            _defer_refresh(Story.editorial_context_fa),
            _defer_refresh(Story.summary_anchor),
            _defer_refresh(Story.analysis_snapshot_24h),
            _defer_refresh(Story.summary_en),
            _defer_refresh(Story.hourly_update_signal),
            _defer_refresh(Story.centroid_embedding),
        )
        .where(Story.id.in_(id_list))
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
        # Cycle-4: pass the editorial-intent anchors so this batch
        # write produces the SAME score as the scheduled recalc would.
        story.trending_score = _compute_trending_score(
            story.article_count,
            story.first_published_at,
            story.source_count,
            last_updated_at=story.last_updated_at,
            frozen_at=story.frozen_at,
        )
        # Clear summary so it gets regenerated by step_summarize — UNLESS the
        # story has been hand-edited by an admin, in which case we preserve
        # the manual content.
        if not story.is_edited:
            story.summary_fa = None
            story.summary_en = None

    # 5. Recompute centroid embeddings for affected stories.
    # Cycle-1 audit Island 3: bulk-fetch all embeddings in ONE query
    # then group by story_id in Python. Prior implementation fired one
    # SELECT per story (N+1), each loading every article.embedding for
    # that story. With 40-60 stories × 5-10 embeddings × 3 KB = 600 KB
    # to 3 MB per refresh, plus N+1 round-trip latency.
    if id_list:
        bulk_emb = await db.execute(
            select(Article.story_id, Article.embedding)
            .where(
                Article.story_id.in_(id_list),
                Article.embedding.isnot(None),
            )
        )
        embeddings_by_story: dict = {}
        for row in bulk_emb.all():
            sid_, emb = row[0], row[1]
            if not emb:
                continue
            embeddings_by_story.setdefault(sid_, []).append(emb)
        for sid in id_list:
            story = stories_by_id.get(sid)
            if not story:
                continue
            story.centroid_embedding = _compute_centroid(
                embeddings_by_story.get(sid, [])
            )


MEDOID_CENTROID_MIN = 25


def _compute_centroid(embeddings: list[list[float] | None]) -> list[float] | None:
    """Centroid of a list of embedding vectors.

    Small clusters: L2-normalized MEAN (cheap, representative).
    Large clusters (>= MEDOID_CENTROID_MIN): the MEDOID — the actual member
    nearest all others — instead of the mean. (#5, 2026-06-03 clustering-
    quality pass.) A mean centroid of a big cluster blurs into a topic-average
    that attracts ever more loosely-related articles (the grab-bag snowball);
    the medoid stays anchored to a real, representative article, so accretion
    needs genuine similarity to a concrete member, not to a blurry average.

    Returns None if no valid embeddings are provided.
    """
    valid = [e for e in embeddings if e and any(v != 0.0 for v in e[:5])]
    if not valid:
        return None
    import numpy as np
    matrix = np.array(valid, dtype=float)
    if len(valid) >= MEDOID_CENTROID_MIN:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        normed = matrix / np.clip(norms, 1e-9, None)
        sims = normed @ normed.T  # pairwise cosine
        centroid = matrix[int(sims.sum(axis=1).argmax())].copy()
    else:
        centroid = matrix.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm  # L2-normalize the centroid
    return centroid.tolist()


# ---------------------------------------------------------------------------
# Step 3: Cluster unmatched articles into new stories
# ---------------------------------------------------------------------------

# Minimum group size for cluster_new. Lowered 2026-05-03 from 5 → 2
# (Parham): the prior floor of 5 was the single biggest orphan-rate
# driver — when a maintenance run had only 4 unmatched articles, the
# entire batch was skipped and every article became an orphan with no
# chance to seed a story. Orphans accumulated to 5342 by 2026-05-03.
# Two-article seeds stay hidden (visibility gate is article_count>=4)
# until subsequent matches grow them, but they DO contribute their
# centroid to the matcher's candidate pool — which is the key benefit:
# a fresh narrative starts gathering articles immediately instead of
# waiting for 5 simultaneous reports. Singletons (=1) are still
# excluded to avoid every wire story spawning its own micro-story.
CLUSTER_NEW_GROUP_FLOOR = 2

# Articles that have been sent to cluster_new this many times without
# joining a viable group become orphans — skipped on future runs.
MAX_CLUSTER_ATTEMPTS = 3


def _content_signature(
    title_original: str | None,
    title_fa: str | None,
    title_en: str | None,
    content_text: str | None,
    summary: str | None,
) -> str:
    """Hash a content fingerprint. Splits the ORM dependency out of
    `_dedup_signature` so callers with primitive fields (dicts captured
    eagerly to dodge ORM expiration) can compute the same signature."""
    import hashlib
    title = (title_original or title_fa or title_en or "").strip()
    title_norm = " ".join(title.lower().split())[:80]
    body = (content_text or summary or "").strip()
    body_norm = " ".join(body.split())[:400]
    raw = f"{title_norm}||{body_norm}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _dedup_signature(article: Article) -> str:
    """Compute a content signature for dedup bucketing.

    Articles with identical signatures are near-duplicates (same wire
    story picked up by multiple feeds, or same feed delivering content
    twice under different URLs). The LLM only needs to see one
    representative per bucket; sibling articles attach to whichever
    story the representative lands in.
    """
    return _content_signature(
        article.title_original, article.title_fa, article.title_en,
        article.content_text, article.summary,
    )


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

    # Capture every article field this function and _create_story_from_dicts
    # need into plain Python dicts BEFORE any operation that could expire
    # the ORM objects. Background: _keepalive's rollback inside the LLM
    # batch loop expires every in-session ORM article, then any
    # subsequent attribute access (in _dedup_signature, _build_articles_
    # block, or _create_story) triggers sync lazy-load → greenlet_spawn.
    # Repeatedly observed across 2026-04-29..30 cluster runs; finally
    # fixed by working entirely with primitives below.
    article_data: list[dict] = []
    for a in articles:
        article_data.append({
            "id": a.id,
            "source_id": a.source_id,
            "title_original": a.title_original,
            "title_fa": a.title_fa,
            "title_en": a.title_en,
            "content_text": a.content_text,
            "summary": a.summary,
            "embedding": a.embedding,
            "published_at": a.published_at,
            "ingested_at": a.ingested_at,
        })

    # --- Dedup: bucket articles by content signature (using dicts) ---
    buckets: dict[str, list[dict]] = {}
    for d in article_data:
        sig = _content_signature(
            d["title_original"], d["title_fa"], d["title_en"],
            d["content_text"], d["summary"],
        )
        d["_sig"] = sig
        buckets.setdefault(sig, []).append(d)

    representatives: list[dict] = [bucket[0] for bucket in buckets.values()]
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
            group_articles: list[dict] = []
            for idx in article_ids_in_prompt:
                actual_index = idx - 1
                if 0 <= actual_index < len(batch):
                    rep = batch[actual_index]
                    # Use the cached signature stored on the dict — same value
                    # _content_signature would compute, but no recomputation.
                    rep_sig = rep["_sig"]
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

    # Collect IDs of articles that made it into a viable group (dicts)
    grouped_ids: set = set()
    for g in all_groups:
        for a in g["articles"]:
            grouped_ids.add(a["id"])

    # Everything we sent to the LLM that didn't end up in a viable group
    # gets its attempt counter bumped. Next run, articles at
    # MAX_CLUSTER_ATTEMPTS are filtered out of the unmatched pool.
    ungrouped_ids = [d["id"] for d in article_data if d["id"] not in grouped_ids]
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

    # Build a primitive source lookup for _create_story_from_dicts: one
    # SELECT against the FRESH cn_db so the data is current.
    src_id_set = {d.get("source_id") for d in article_data if d.get("source_id")}
    source_lookup: dict = {}
    if src_id_set:
        from app.models.source import Source as _SourceModel
        src_q = await db.execute(
            select(
                _SourceModel.id,
                _SourceModel.name_en,
                _SourceModel.state_alignment,
                _SourceModel.production_location,
                _SourceModel.factional_alignment,
            ).where(_SourceModel.id.in_(src_id_set))
        )
        for sid, name_en, st_align, prod_loc, fa_align in src_q.all():
            source_lookup[sid] = {
                "name_en": name_en,
                "state_alignment": st_align,
                "production_location": prod_loc,
                "factional_alignment": fa_align,
            }

    published = 0
    hidden = 0

    for group in all_groups:
        # Layer 2 — verify the generated headline's numbers/subjects are
        # grounded in the cluster's source headlines before it's saved.
        # Number-gated inside verify_title_grounding, so this is a no-op
        # (no LLM call) for the common case of a number-free title.
        grounded_title_fa = await verify_title_grounding(
            group.get("title_fa") or "",
            [
                (a.get("title_original") or a.get("title_fa") or a.get("title_en") or "")
                for a in group["articles"]
            ],
        )
        story = await _create_story_from_dicts(
            db,
            group["articles"],
            source_lookup=source_lookup,
            title_fa=grounded_title_fa,
            title_en=group["title_en"],
            topics=group["topics"],
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

    # Egress fix (Parham 2026-05-07): defer the heavy Story JSONB columns
    # this function never reads. Tiny-merge only needs id, article_count,
    # centroid_embedding (for cosine), title_fa (for log), last_updated_at.
    # Loading translations / telegram_analysis / editorial_context_fa /
    # summary_anchor / analysis_snapshot_24h / hourly_update_signal /
    # summary_en is pure waste at ~10-20 KB per row × ~1000 tiny stories.
    from sqlalchemy.orm import defer as _defer_merge
    _MERGE_STORY_DEFERS = (
        _defer_merge(Story.translations),
        _defer_merge(Story.telegram_analysis),
        _defer_merge(Story.editorial_context_fa),
        _defer_merge(Story.summary_anchor),
        _defer_merge(Story.analysis_snapshot_24h),
        _defer_merge(Story.hourly_update_signal),
        _defer_merge(Story.summary_en),
    )
    rows = (await db.execute(
        select(Story)
        .options(*_MERGE_STORY_DEFERS)
        .where(
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
    # Egress fix (Parham 2026-05-07): same defer pattern as
    # _merge_tiny_by_cosine. Hidden-story merge reads id, article_count,
    # title_fa, title_en, slug, centroid_embedding (for cosine).
    from sqlalchemy.orm import defer as _defer_merge_h
    result = await db.execute(
        select(Story)
        .options(
            _defer_merge_h(Story.translations),
            _defer_merge_h(Story.telegram_analysis),
            _defer_merge_h(Story.editorial_context_fa),
            _defer_merge_h(Story.summary_anchor),
            _defer_merge_h(Story.analysis_snapshot_24h),
            _defer_merge_h(Story.hourly_update_signal),
            _defer_merge_h(Story.summary_en),
        )
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
    UMBRELLA_FIRST_PUB_CAP_DAYS = 7  # mirror clustering matcher + freeze rule

    # Mirror the safety gates in `_match_to_existing_stories` so old or
    # oversized umbrellas can't be picked as merge keepers. Background:
    # an unfrozen 245-article umbrella would otherwise absorb fresh
    # sibling clusters every cron tick. Articles transferred → `_refresh_
    # story_metadata` bumps `last_updated_at` → story looks fresh on the
    # homepage despite being a 30-day-old chapter the freeze rule
    # already chose to retire. step_archive_stale freezes it again at
    # the end of the cron, but the in-cron merge already grew the
    # cluster and bumped its timestamp. Verified 2026-05-06 against
    # story f06af369 (245 articles, first_published_at = 2026-04-06).
    umbrella_cutoff = datetime.now(timezone.utc) - timedelta(days=UMBRELLA_FIRST_PUB_CAP_DAYS)
    # Egress fix (Parham 2026-05-07): defer heavy Story JSONB cols. This
    # function only reads title_fa, title_en, centroid_embedding (cosine),
    # article_count, last_updated_at, trending_score, first_published_at.
    from sqlalchemy.orm import defer as _defer_merge_v
    result = await db.execute(
        select(Story)
        .options(
            _defer_merge_v(Story.translations),
            _defer_merge_v(Story.telegram_analysis),
            _defer_merge_v(Story.editorial_context_fa),
            _defer_merge_v(Story.summary_anchor),
            _defer_merge_v(Story.analysis_snapshot_24h),
            _defer_merge_v(Story.hourly_update_signal),
            _defer_merge_v(Story.summary_en),
        )
        .where(
            Story.article_count >= 5,
            Story.article_count < settings.max_cluster_size,
            Story.frozen_at.is_(None),
            Story.archived_at.is_(None),
            # Never auto-merge human-curated stories. is_edited=True marks a
            # hand-seeded / Niloofar-edited story; priority >= floor marks an
            # operator pin. Excluding them from the candidate pool keeps them
            # untouched — they can be neither keeper (absorbing a foreign mix)
            # nor victim (silently deleted). See _MERGE_PIN_PRIORITY_FLOOR.
            Story.is_edited.is_(False),
            func.coalesce(Story.priority, 0) < _MERGE_PIN_PRIORITY_FLOOR,
            (
                func.coalesce(Story.first_published_at, Story.created_at)
                >= umbrella_cutoff
            ),
        )
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
        # Cycle-1 audit Island 3: log when centroid is non-list. The
        # JSONB schema should always store lists; non-list = schema drift.
        if a.centroid_embedding is not None and not isinstance(a.centroid_embedding, list):
            logger.warning(
                "Story %s centroid_embedding is non-list (%s); schema drift",
                a.id,
                type(a.centroid_embedding).__name__,
            )
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
            # Belt-and-suspenders: the candidate query already excludes
            # is_edited / pinned stories, but never delete a human-curated
            # story even if one slips through (e.g. flagged between query and
            # execution). Skip it rather than erase an operator's curation.
            if victim.is_edited or (victim.priority or 0) >= _MERGE_PIN_PRIORITY_FLOOR:
                logger.warning(
                    "Refusing to merge protected story %s ('%s', is_edited=%s, "
                    "priority=%s) into %s — left untouched",
                    victim.id,
                    (victim.title_fa or "")[:40],
                    victim.is_edited,
                    victim.priority,
                    keeper.id,
                )
                continue
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


async def _create_story_from_dicts(
    db: AsyncSession,
    article_dicts: list[dict],
    source_lookup: dict,  # source_id → (name_en, state_alignment, production_location, factional_alignment)
    title_fa: str,
    title_en: str,
    topics: list[str],
) -> Story:
    """Primitive-only variant of _create_story. Takes article dicts +
    a source lookup; never reads ORM attributes that could trigger
    lazy-loads after a keepalive rollback. Use this from cluster_new.
    """
    # Fallback titles if LLM didn't provide them
    if not title_fa:
        primary = sorted(article_dicts, key=lambda d: d.get("published_at") or d.get("ingested_at"))[-1]
        title_fa = primary.get("title_original") or primary.get("title_fa") or "بدون عنوان"
    if not title_en:
        primary = sorted(article_dicts, key=lambda d: d.get("published_at") or d.get("ingested_at"))[-1]
        title_en = primary.get("title_en") or title_fa

    # Partition articles by the 4-subgroup narrative taxonomy via the
    # source_lookup primitive dict (no ORM relationship access).
    from app.services.narrative_groups import narrative_group as _ng_c, side_of as _side_of_c
    groups_present: set[str] = set()
    state_n = 0
    diaspora_n = 0
    for d in article_dicts:
        info = source_lookup.get(d.get("source_id"))
        if info is None:
            diaspora_n += 1
            groups_present.add("moderate_diaspora")
            continue
        # info: dict with production_location, factional_alignment, state_alignment
        shim = type("S", (), {
            "production_location": info.get("production_location"),
            "factional_alignment": info.get("factional_alignment"),
            "state_alignment": info.get("state_alignment"),
        })()
        grp = _ng_c(shim)
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

    coverage_diversity = len(groups_present) / 4.0

    published_dates = [d["published_at"] for d in article_dicts if d.get("published_at")]
    first_published = min(published_dates) if published_dates else None

    source_ids = {d.get("source_id") for d in article_dicts if d.get("source_id")}

    centroid = _compute_centroid([d["embedding"] for d in article_dicts if d.get("embedding")])

    story = Story(
        title_en=title_en,
        title_fa=title_fa,
        slug=generate_slug(title_en),
        article_count=len(article_dicts),
        source_count=len(source_ids),
        covered_by_state=covered_by_state,
        covered_by_diaspora=covered_by_diaspora,
        is_blindspot=is_blindspot,
        blindspot_type=blindspot_type,
        coverage_diversity_score=coverage_diversity,
        topics=topics,
        first_published_at=first_published,
        last_updated_at=datetime.now(timezone.utc),
        trending_score=_compute_trending_score(len(article_dicts), first_published, len(source_ids)),
        centroid_embedding=centroid,
    )
    db.add(story)
    await db.flush()  # get story.id

    # Link articles to the new story (bulk UPDATE keyed by captured ids)
    article_ids = [d["id"] for d in article_dicts]
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
            "article_count": len(article_dicts),
            "source_count": story.source_count,
            "title_fa": (story.title_fa or "")[:120],
        },
    )

    return story


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

    # 7-day data window (Parham 2026-05-09): clustering, centroids,
    # telegram-link, and sentiment all operate on articles + posts ≤ 7
    # days. Older content stays queryable for archived/historical pages
    # but is invisible to the pipeline. Was 30 days before; the slack
    # let umbrella stories absorb articles for weeks before being
    # frozen. Tightening to 7 makes the freeze rule actually meaningful.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # ── Step 1: Get unclustered articles from the last 7 days ──
    # Skip orphans that have already been sent to cluster_new
    # MAX_CLUSTER_ATTEMPTS times without joining a viable group.
    # Without this gate, articles with no duplicates (e.g. niche
    # single-source pieces) cycle through cluster_new on every
    # pipeline run, paying the LLM tax indefinitely.
    # content_type gate (Niloofar audit 2026-06-02): mirror the NLP/embed
    # gate (nlp_pipeline.py) so ONLY classified, in-scope articles cluster.
    # Previously this pool took every unclustered article regardless of
    # content_type — so unclassified (content_type IS NULL, e.g. fresh
    # Telegram-converted posts) and off-topic articles (sports/weather)
    # reached the LLM title-grouper (cluster_new needs no embedding) and got
    # assigned to stories, polluting war/negotiation clusters. NULL rows now
    # wait for the classifier pass that runs BEFORE this step; off_topic /
    # non-allowed labels never cluster.
    result = await db.execute(
        select(Article)
        .join(Source, Source.id == Article.source_id)
        .where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
            Article.cluster_attempts < MAX_CLUSTER_ATTEMPTS,
            Article.content_type.isnot(None),
            text("(sources.content_filters -> 'allowed') @> to_jsonb(articles.content_type)"),
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
    # Each phase below opens its OWN fresh async_session via
    # async_session() so a session that goes bad inside phase N (Neon
    # killed connection during an LLM call → keepalive rollback →
    # ORM objects expired) doesn't poison phase N+1. Inputs cross phase
    # boundaries as primitive UUIDs only — never ORM objects.
    from app.database import async_session as _phase_session
    llm_candidates_sent = 0  # default if matcher errored / short-circuited
    try:
        async with _phase_session() as match_db:
            unmatched_ids, llm_candidates_sent = await _match_to_existing_stories(
                match_db, articles, source_names, deadline_ts=deadline_ts,
            )
            try:
                await match_db.commit()
            except Exception:
                # Session may already be in aborted state from a
                # mid-LLM keepalive failure. Rollback so the with-block
                # exits cleanly; the matched-so-far state is lost but
                # the captured `matched_article_ids` from inside the
                # function never persisted (no flush completed). Next
                # run will re-attempt the matches.
                try:
                    await match_db.rollback()
                except Exception:
                    pass
                raise
    except Exception as _e:
        raise RuntimeError(f"cluster_phase=match_existing: {type(_e).__name__}: {_e}") from _e
    matched_count = total_articles - len(unmatched_ids)
    logger.info(
        f"Step 2 complete: {matched_count} matched to existing, "
        f"{len(unmatched_ids)} still unmatched"
    )
    # Keep the outer `db` session warm. It sat idle while the
    # match_existing phase ran with its own fresh session — Neon's 5-min
    # idle reaper is happy to kill it. Without this, the outer session's
    # cleanup at end-of-step raises InterfaceError ("cannot call
    # Transaction.rollback(): the underlying connection is closed") and
    # masks whatever else might have actually failed. Observed in the
    # 2026-04-30 08:33 UTC run.
    await _keepalive(db)

    # ── Step 3: Cluster unmatched articles into new stories ──
    # Fresh session — re-fetch unmatched articles by ID. The match phase
    # session is already closed by its `async with` block above; the
    # input `articles` list may contain expired ORM objects from that
    # phase's keepalive rollback, so we never use them downstream.
    try:
        if unmatched_ids:
            async with _phase_session() as cn_db:
                unmatched_result = await cn_db.execute(
                    select(Article).where(Article.id.in_(unmatched_ids))
                )
                unmatched = list(unmatched_result.scalars().all())
                new_published, new_hidden = await _cluster_new_articles(
                    cn_db, unmatched, source_names, source_alignments_map,
                    deadline_ts=deadline_ts,
                )
                try:
                    await cn_db.commit()
                except Exception:
                    try:
                        await cn_db.rollback()
                    except Exception:
                        pass
                    raise
        else:
            new_published, new_hidden = 0, 0
    except Exception as _e:
        # Capture deeper context (Parham 2026-05-03 audit): the
        # 2026-05-03 07:46 UTC run failed here with
        # `ArgumentError: Object <Article https://t.me/presstv/187567>
        # is not legal as a SQL literal value`. Static analysis didn't
        # find the leak — adding traceback logging so the next failure
        # surfaces the offending call site immediately rather than
        # requiring another live forensic trip.
        import traceback as _tb
        logger.error(
            f"cluster_phase=cluster_new failed: {type(_e).__name__}: {_e}\n"
            f"unmatched_id_count={len(unmatched_ids) if unmatched_ids else 0}\n"
            f"traceback:\n{_tb.format_exc()[:3000]}"
        )
        raise RuntimeError(f"cluster_phase=cluster_new: {type(_e).__name__}: {_e}") from _e
    # Keep the outer `db` warm again — same rationale as above. The
    # cluster_new phase can run for many minutes when there's a backlog.
    await _keepalive(db)

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

    # Cycle-1 audit Island 3: surface LLM phase conversion rate so a
    # drop in match-rate (prompt drift, model regression) shows up in
    # stats instead of needing log inspection.
    stats = {
        "matched_to_existing": matched_count,
        "new_stories_created": new_published,
        "new_stories_hidden": new_hidden,
        "merged": merged_count,
        "unclustered": unclustered_count,
        "aged_orphans": aged_orphans,
        "retired_orphans": retired_orphans,
        # Conversion-rate signal from the match phase. Sent_to_llm is
        # the input pool, matched_to_existing is the outcome. Rejected
        # = sent_to_llm - matched_to_existing (when sent > 0).
        # Cycle-3 fix: count is captured from _match_to_existing_stories
        # via tuple return — pre-fix referenced article_candidates
        # which lives in that function's scope, raising NameError on
        # every cluster step.
        "llm_candidates_sent": int(llm_candidates_sent),
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

    # Cycle-3 audit (2026-05-08): scope to recently-active stories
    # only. Pre-this-fix, every cron iterated all 561 stories with
    # article_count >= 10 — including 3-year-old frozen umbrellas
    # that haven't accepted a new article in months. Each story
    # required a 4-row Article.embedding sample (~3.7 KB each =
    # ~15 KB/story), so 561 stories burned ~8 MB of pure waste per
    # cron audit. Adding `last_updated_at >= NOW() - 7d` AND skipping
    # frozen + archived stories drops the surface to ~30-50 stories
    # — only the ones that could realistically have absorbed
    # incoherent articles in the recent window. Frozen umbrellas
    # don't grow, so re-checking their drift adds no signal.
    audit_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    q = await db.execute(
        select(Story.id, Story.title_fa, Story.article_count)
        .where(
            Story.article_count >= min_articles,
            Story.last_updated_at >= audit_cutoff,
            Story.frozen_at.is_(None),
            Story.archived_at.is_(None),
        )
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
                if s <= pair_cosine_floor:  # <= so a pair AT the floor still flags drift
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


# ── Niloofar coherence audit that ACTS (2026-06-01) ────────────────────
# The flag-only audit above skips frozen stories — but a frozen grab-bag
# still shows on the homepage during a content drought (frozen-stays-
# visible). So this pass audits the HOMEPAGE-VISIBLE set (incl. frozen),
# and for a story that's both (a) deterministically incoherent (articles
# scatter away from the centroid) AND (b) confirmed a grab-bag by a cheap
# LLM, it ARCHIVES it. Double-gated so a legitimately big coherent story
# (e.g. the 161-article Hormuz cluster, whose articles hug its centroid)
# is never touched. Archive is reversible (PATCH archived=false).
COHERENCE_ACT_PROMPT = """\
You are a meticulous Persian news editor checking whether a story cluster is \
ABOUT ONE STORY or is a grab-bag of unrelated events mislabeled with one title.

Cluster title:
{title}

Sample of article headlines in the cluster:
{headlines_block}

A coherent cluster: the headlines are all about the SAME specific event/topic the \
title names. A grab-bag: the headlines span several unrelated events (different \
places, different topics) and the title only matches a minority.

Return ONLY valid JSON:
{{"grab_bag": true_or_false, "off_topic_ratio": 0.0_to_1.0, "dominant_topic": "...", "reason": "short Persian"}}

- off_topic_ratio = fraction of headlines NOT about the title's specific event.
- grab_bag = true only when the cluster clearly mixes several unrelated events.
"""


async def _call_openai_coherence(prompt: str) -> dict | None:
    """Cheap-tier (gpt-4.1-nano) JSON call for the coherence-act audit.
    Returns parsed dict, or None on ANY failure — no silent fallback:
    the caller NEVER archives on a None (no LLM confirm = no action)."""
    if not settings.openai_api_key:
        return None
    from app.services.llm_helper import build_openai_params
    from app.services.llm_usage import log_llm_usage

    def _sync_call():
        client = OpenAI(api_key=settings.openai_api_key)
        try:
            params = build_openai_params(
                model=settings.content_type_model,
                prompt=prompt,
                max_tokens=300,
                temperature=0,
            )
            response = client.chat.completions.create(**params)
            return _parse_llm_response(response.choices[0].message.content), response.usage
        except Exception as e:
            logger.error(f"Coherence-audit LLM error: {e}")
            return None, None

    parsed, usage = await asyncio.get_event_loop().run_in_executor(None, _sync_call)
    if usage is not None:
        await log_llm_usage(
            model=settings.content_type_model,
            purpose="clustering.coherence_audit",
            usage=usage,
        )
    return parsed or None


async def detach_offtopic_from_visible_stories(
    db: AsyncSession, *, limit: int = 500
) -> dict:
    """Cluster hygiene: detach articles sitting INSIDE visible homepage stories
    whose content_type is NOT in the source's allowed list (off_topic / opinion /
    discussion / aggregation / other).

    These were clustered BEFORE the 2026-06-02 content_type cluster gate existed.
    The gate stops NEW junk from clustering, but already-clustered articles don't
    re-cluster, so legacy off-topic pollution persists (the homepage_offtopic_leak
    canary surfaces it — 173 at install time). This drains it so the canary
    self-heals to 0. Detach only (story_id=NULL): their content_type is already
    non-allowed, so the cluster gate keeps them from rejoining — no mark needed.
    Recounts affected stories and clears their translations (article set changed).
    Mirrors the canary SQL exactly (= the cluster gate predicate)."""
    rows = (await db.execute(text("""
        SELECT a.id AS aid, a.story_id AS sid
        FROM articles a
        JOIN sources s ON s.id = a.source_id
        JOIN stories st ON st.id = a.story_id
        WHERE st.archived_at IS NULL AND st.article_count >= 5
          AND a.content_type IS NOT NULL
          AND NOT ((s.content_filters -> 'allowed') @> to_jsonb(a.content_type))
        LIMIT :lim
    """), {"lim": limit})).mappings().all()
    if not rows:
        return {"detached": 0, "stories_touched": 0}
    aids = [r["aid"] for r in rows]
    affected = {r["sid"] for r in rows if r["sid"]}
    await db.execute(
        update(Article).where(Article.id.in_(aids)).values(story_id=None)
        .execution_options(synchronize_session=False)
    )
    from app.services.translate_multilocale import clear_translations_for_story
    for sid in affected:
        live = (await db.execute(
            select(func.count(Article.id)).where(Article.story_id == sid)
        )).scalar() or 0
        st = await db.get(Story, sid)
        if st is not None:
            st.article_count = live
        try:
            await clear_translations_for_story(db, sid)
        except Exception:
            pass
    await db.commit()
    try:
        from app.services.events import log_event
        await log_event(
            db, event_type="cluster_hygiene_offtopic", actor="cron",
            signals={"detached": len(aids), "stories_touched": len(affected)},
        )
        await db.commit()
    except Exception:
        pass
    logger.info(
        "cluster hygiene: detached %d off-topic articles from %d visible stories",
        len(aids), len(affected),
    )
    return {"detached": len(aids), "stories_touched": len(affected)}


async def freeze_oversized_active_stories(db) -> dict:
    """#5 — size-based umbrella freeze (2026-06-03 clustering-quality pass).

    Freeze (set frozen_at) any ACTIVE, NON-edited story whose article_count
    has reached settings.max_cluster_size. The match-to-existing query already
    refuses to attach to stories >= max_cluster_size, so this mostly clears the
    `oversized_active_stories` canary and demotes the umbrella — but it also
    closes the brief window where recompute/merge paths could re-inflate one.

    is_edited stories are EXEMPT: those are human-curated heroes (e.g. the
    pinned war story Parham chose NOT to freeze). Frozen-stays-on-homepage, so
    a frozen umbrella still renders; it just stops absorbing new articles.
    """
    from sqlalchemy import update as _update
    from app.config import settings as _settings
    from app.models.story import Story as _Story

    rows = (await db.execute(
        select(_Story.id, _Story.article_count).where(
            _Story.frozen_at.is_(None),
            _Story.archived_at.is_(None),
            _Story.is_edited.is_(False),
            _Story.article_count >= _settings.max_cluster_size,
        )
    )).all()
    ids = [r[0] for r in rows]
    if not ids:
        return {"frozen": 0}
    now = datetime.now(timezone.utc)
    await db.execute(
        _update(_Story).where(_Story.id.in_(ids)).values(frozen_at=now)
        .execution_options(synchronize_session=False)
    )
    try:
        from app.services.events import log_event
        await log_event(
            db, event_type="cluster_hygiene_freeze_oversized", actor="cron",
            signals={"frozen": len(ids), "cap": _settings.max_cluster_size},
        )
        await db.commit()
    except Exception:
        await db.commit()
    logger.info("cluster hygiene: froze %d oversized active non-edited stories", len(ids))
    return {"frozen": len(ids)}


async def audit_homepage_coherence(
    db: AsyncSession,
    *,
    min_articles: int = 15,
    sample_size: int = 8,
    centroid_cohesion_floor: float = 0.55,
    off_topic_archive_ratio: float = 0.5,
) -> dict:
    """Audit homepage-visible stories and ARCHIVE confirmed grab-bags.

    Per story (homepage scope, article_count >= min_articles):
    1. Deterministic pre-filter — mean cosine of sampled articles to the
       story centroid. Coherent clusters hug the centroid (>floor); only
       LOW-cohesion stories advance, so cost + risk stay on the suspects.
    2. LLM confirm (cheap) — title vs sampled headlines → grab_bag verdict.
       No LLM key / LLM error → None → NEVER archive (fail-safe).
    3. Archive (+priority=-100) when both gates agree, logging the
       evidence to story_events (coherence_archive). Reversible.
    """
    from app.nlp.embeddings import cosine_similarity as _cos
    from app.services.homepage_scope import homepage_story_ids
    from app.services.events import log_event as _log_event

    stats = {"checked": 0, "low_cohesion": 0, "llm_confirmed": 0,
             "archived": 0, "archived_titles": []}

    hp_ids = await homepage_story_ids(db, trending_top_n=25, blindspot_top_n=20)
    if not hp_ids:
        return stats

    rows = (await db.execute(
        select(Story.id, Story.title_fa, Story.article_count, Story.centroid_embedding)
        .where(
            Story.id.in_(hp_ids),
            Story.article_count >= min_articles,
            Story.archived_at.is_(None),
            Story.priority <= 0,  # respect manual pins
        )
    )).all()

    for sid, title_fa, ac, centroid in rows:
        if not centroid:
            continue
        stats["checked"] += 1
        art_q = await db.execute(
            select(Article.embedding, Article.title_fa, Article.title_original)
            .where(Article.story_id == sid, Article.embedding.isnot(None))
            .order_by(Article.published_at.desc().nullslast())
            .limit(sample_size)
        )
        sample = [r for r in art_q.all() if r[0]]
        if len(sample) < 5:
            continue
        cohesion = sum(_cos(r[0], centroid) for r in sample) / len(sample)
        if cohesion >= centroid_cohesion_floor:
            continue  # hugs the centroid → coherent → skip (no LLM)
        stats["low_cohesion"] += 1

        headlines = [(r[1] or r[2] or "").strip() for r in sample]
        headlines = [h for h in headlines if h]
        block = "\n".join(f"- {h}" for h in headlines)
        verdict = await _call_openai_coherence(
            COHERENCE_ACT_PROMPT.format(title=title_fa or "", headlines_block=block)
        )
        if not verdict:
            continue  # fail-safe: no LLM confirm → no archive
        if not (verdict.get("grab_bag") is True
                and float(verdict.get("off_topic_ratio") or 0) >= off_topic_archive_ratio):
            continue
        stats["llm_confirmed"] += 1

        from datetime import datetime as _dt_c, timezone as _tz_c
        await db.execute(
            update(Story).where(Story.id == sid).values(
                archived_at=_dt_c.now(_tz_c.utc), priority=-100,
            )
        )
        await _log_event(
            db, event_type="coherence_archive", actor="maintenance",
            story_id=sid,
            signals={
                "article_count": int(ac or 0),
                "centroid_cohesion": round(cohesion, 3),
                "off_topic_ratio": float(verdict.get("off_topic_ratio") or 0),
                "reason": str(verdict.get("reason") or "")[:200],
                "title_fa": (title_fa or "")[:120],
            },
        )
        stats["archived"] += 1
        stats["archived_titles"].append((title_fa or "")[:60])
        logger.info(
            "Coherence-archive: %s (ac=%s, cohesion=%.2f, off_topic=%.2f) — %s",
            (title_fa or "")[:50], ac, cohesion,
            float(verdict.get("off_topic_ratio") or 0), verdict.get("reason", ""),
        )
    await db.commit()
    logger.info(f"Homepage coherence act: {stats}")
    return stats


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
