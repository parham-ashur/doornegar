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
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

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
You are a news editor specializing in Iranian media. Match each new article \
to an existing story, or say null if it doesn't match any.

Existing stories:
{stories_block}

New articles:
{articles_block}

Return valid JSON with this exact structure:
{{
  "matches": [
    {{"article_idx": 1, "story_idx": 2}},
    {{"article_idx": 3, "story_idx": null}}
  ]
}}

Rules:
- Only match if the article is about the EXACT SAME specific event as the story
- If unsure, say null — don't force matches
- Only Iran-related articles should be matched
- article_idx and story_idx are the numbers shown before each item (1-based)
- Return ONLY the JSON object, no extra text
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


def _compute_trending_score(article_count: int, first_published: datetime | None) -> float:
    """Compute a trending score based on article count and recency.

    Score = article_count * recency_factor
    recency_factor decays from 1.0 to 0.1 over 30 days.
    """
    if first_published:
        hours_ago = (datetime.now(timezone.utc) - first_published).total_seconds() / 3600
        max_hours = 30 * 24  # 30 days
        recency_factor = max(0.1, 1.0 - (hours_ago / max_hours) * 0.9)
    else:
        recency_factor = 0.5

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
    """Build the numbered article list for the prompt.

    source_names: optional pre-extracted mapping of article.id -> source name
    """
    lines = []
    for i, article in enumerate(articles, 1):
        title = article.title_original or article.title_fa or article.title_en or "(no title)"
        if source_names:
            sname = source_names.get(str(article.id), "Unknown")
        else:
            sname = "Unknown"
        lines.append(f"{i}. {title} (source: {sname})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call helpers (sync OpenAI in run_in_executor to avoid greenlet issues)
# ---------------------------------------------------------------------------


async def _call_openai(prompt: str, max_tokens: int = 4096) -> dict:
    """Send a prompt to GPT-4o-mini and return parsed JSON."""

    def _sync_call():
        client = OpenAI(api_key=settings.openai_api_key)
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0,
            )
            response_text = response.choices[0].message.content
            logger.debug(f"OpenAI response: {response_text[:300]}")
            return _parse_llm_response(response_text)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {}

    return await asyncio.get_event_loop().run_in_executor(None, _sync_call)


# ---------------------------------------------------------------------------
# Step 2: Match new articles to existing stories
# ---------------------------------------------------------------------------


async def _match_to_existing_stories(
    db: AsyncSession,
    articles: list[Article],
    source_names: dict[str, str],
) -> list[Article]:
    """Try to match new articles to existing visible stories (article_count >= 5).

    Returns the list of articles that were NOT matched (still need clustering).
    """
    # Get existing visible stories
    result = await db.execute(
        select(Story.id, Story.title_fa, Story.title_en)
        .where(Story.article_count >= 5)
        .order_by(Story.last_updated_at.desc().nullslast())
    )
    existing_stories = result.all()  # list of (id, title_fa, title_en)

    if not existing_stories:
        logger.info("No existing visible stories to match against")
        return articles

    logger.info(
        f"Matching {len(articles)} articles against {len(existing_stories)} existing stories"
    )

    # Build a lookup: 1-based story index -> story row
    # We'll process stories in batches of STORY_BATCH_SIZE
    matched_article_ids: set[uuid.UUID] = set()

    for story_batch_start in range(0, len(existing_stories), STORY_BATCH_SIZE):
        story_batch = existing_stories[story_batch_start: story_batch_start + STORY_BATCH_SIZE]

        # Build stories block
        stories_lines = []
        for i, (sid, title_fa, title_en) in enumerate(story_batch, 1):
            display = title_fa or title_en or "(no title)"
            stories_lines.append(f"S{i}. {display}")
        stories_block = "\n".join(stories_lines)

        # Only send unmatched articles
        remaining = [a for a in articles if a.id not in matched_article_ids]
        if not remaining:
            break

        articles_block = _build_articles_block(remaining, source_names)

        prompt = MATCHING_PROMPT.format(
            stories_block=stories_block,
            articles_block=articles_block,
        )

        result_json = await _call_openai(prompt, max_tokens=4096)
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

            # Assign article to story
            article.story_id = story_id
            matched_article_ids.add(article.id)
            logger.debug(
                f"Matched article '{article.title_original or article.title_fa}' "
                f"to story {story_id}"
            )

    # Flush article assignments
    if matched_article_ids:
        await db.flush()

        # Update story metadata for all affected stories
        affected_story_ids = set()
        for a in articles:
            if a.id in matched_article_ids and a.story_id:
                affected_story_ids.add(a.story_id)

        for story_id in affected_story_ids:
            await _refresh_story_metadata(db, story_id)

    logger.info(f"Matched {len(matched_article_ids)} articles to existing stories")

    # Return unmatched articles
    return [a for a in articles if a.id not in matched_article_ids]


async def _refresh_story_metadata(db: AsyncSession, story_id: uuid.UUID) -> None:
    """Recalculate a story's article_count, source_count, coverage flags, etc."""
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if not story:
        return

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

    # Update coverage flags
    alignment_result = await db.execute(
        select(Source.state_alignment)
        .join(Article, Article.source_id == Source.id)
        .where(Article.story_id == story_id)
        .distinct()
    )
    alignments = {row[0] for row in alignment_result.all()}

    story.covered_by_state = bool(alignments & {"state", "semi_state"})
    story.covered_by_diaspora = bool(alignments & {"diaspora", "independent"})
    story.is_blindspot = story.covered_by_state != story.covered_by_diaspora
    if story.is_blindspot:
        story.blindspot_type = "state_only" if story.covered_by_state else "diaspora_only"
    else:
        story.blindspot_type = None

    story.coverage_diversity_score = len(alignments) / 4.0
    story.last_updated_at = datetime.now(timezone.utc)
    story.trending_score = _compute_trending_score(
        story.article_count, story.first_published_at
    )

    # Clear summary so it gets regenerated
    story.summary_fa = None
    story.summary_en = None


# ---------------------------------------------------------------------------
# Step 3: Cluster unmatched articles into new stories
# ---------------------------------------------------------------------------


async def _cluster_new_articles(
    db: AsyncSession,
    articles: list[Article],
    source_names: dict[str, str],
    source_alignments_map: dict[str, str | None],
) -> tuple[int, int]:
    """Cluster unmatched articles into new stories via LLM.

    Returns (new_stories_published, new_stories_hidden).
    """
    if len(articles) < 2:
        logger.info(f"Only {len(articles)} unmatched articles — skipping new clustering")
        return 0, 0

    logger.info(f"Clustering {len(articles)} unmatched articles into new stories")

    all_groups: list[dict] = []

    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start: batch_start + BATCH_SIZE]
        logger.info(
            f"Sending batch {batch_start // BATCH_SIZE + 1} "
            f"({len(batch)} articles) to OpenAI for clustering"
        )
        articles_block = _build_articles_block(batch, source_names)
        prompt = CLUSTERING_PROMPT.format(articles_block=articles_block)
        result_json = await _call_openai(prompt, max_tokens=4096)

        for group in result_json.get("groups", []):
            article_ids_in_prompt = group.get("article_ids", [])
            group_articles = []
            for idx in article_ids_in_prompt:
                actual_index = idx - 1
                if 0 <= actual_index < len(batch):
                    group_articles.append(batch[actual_index])
                else:
                    logger.warning(f"LLM returned out-of-range article ID: {idx}")

            if len(group_articles) >= 2:
                all_groups.append({
                    "articles": group_articles,
                    "title_fa": group.get("title_fa", ""),
                    "title_en": group.get("title_en", ""),
                    "topics": group.get("topics", []),
                })

    logger.info(f"LLM returned {len(all_groups)} valid groups from unmatched articles")

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
            hidden += 1
            logger.info(
                f"Created hidden story '{story.slug}' with {story.article_count} articles "
                f"(below threshold, hidden)"
            )

    return published, hidden


# ---------------------------------------------------------------------------
# Step 5: Merge similar hidden stories
# ---------------------------------------------------------------------------


async def _merge_hidden_stories(db: AsyncSession) -> int:
    """Find and merge hidden stories (article_count < 5) that are about the same event.

    Returns number of stories that were merged (absorbed into others).
    """
    result = await db.execute(
        select(Story)
        .where(Story.article_count < 5)
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
    result_json = await _call_openai(prompt, max_tokens=2048)
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

    # Determine coverage flags
    source_alignments = set()
    for article in articles:
        align = source_alignments_map.get(str(article.id)) if source_alignments_map else None
        if align:
            source_alignments.add(align)

    covered_by_state = bool(source_alignments & {"state", "semi_state"})
    covered_by_diaspora = bool(source_alignments & {"diaspora", "independent"})

    is_blindspot = covered_by_state != covered_by_diaspora
    blindspot_type = None
    if is_blindspot:
        if covered_by_state and not covered_by_diaspora:
            blindspot_type = "state_only"
        elif covered_by_diaspora and not covered_by_state:
            blindspot_type = "diaspora_only"

    # Coverage diversity
    all_alignments = {"state", "semi_state", "independent", "diaspora"}
    coverage_diversity = len(source_alignments) / len(all_alignments)

    # Earliest published date
    published_dates = [a.published_at for a in articles if a.published_at]
    first_published = min(published_dates) if published_dates else None

    # Unique sources
    source_ids = {a.source_id for a in articles}

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
        trending_score=_compute_trending_score(len(articles), first_published),
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

    return story


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def cluster_articles(db: AsyncSession) -> dict:
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
    result = await db.execute(
        select(Article)
        .options(joinedload(Article.source))
        .where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
        )
        .order_by(Article.published_at.desc().nullslast())
    )
    articles = list(result.scalars().all())

    # Pre-extract source info while in session context (avoid lazy loading later)
    source_names: dict[str, str] = {}
    source_alignments_map: dict[str, str | None] = {}
    for a in articles:
        aid = str(a.id)
        source_names[aid] = a.source.name_en if a.source else "Unknown"
        source_alignments_map[aid] = a.source.state_alignment if a.source else None

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
    unmatched = await _match_to_existing_stories(db, articles, source_names)
    matched_count = total_articles - len(unmatched)
    logger.info(
        f"Step 2 complete: {matched_count} matched to existing, "
        f"{len(unmatched)} still unmatched"
    )

    # ── Step 3: Cluster unmatched articles into new stories ──
    new_published, new_hidden = await _cluster_new_articles(
        db, unmatched, source_names, source_alignments_map
    )

    # ── Step 4: Promote hidden stories that now have 5+ articles ──
    # (No is_published column — the API filters by article_count >= 5.
    #  But we log how many stories crossed the threshold after this run.)
    promoted_result = await db.execute(
        select(func.count(Story.id)).where(Story.article_count >= 5)
    )
    total_visible = promoted_result.scalar() or 0
    logger.info(f"Total visible stories (article_count >= 5): {total_visible}")

    # ── Step 5: Merge similar hidden stories ──
    merged_count = await _merge_hidden_stories(db)

    # Count remaining unclustered after all steps
    unclustered_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
        )
    )
    unclustered_count = unclustered_result.scalar() or 0

    await db.commit()

    stats = {
        "matched_to_existing": matched_count,
        "new_stories_created": new_published,
        "new_stories_hidden": new_hidden,
        "merged": merged_count,
        "unclustered": unclustered_count,
    }
    logger.info(f"Incremental clustering complete: {stats}")
    return stats
