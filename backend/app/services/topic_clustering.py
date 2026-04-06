"""LLM-enhanced topic clustering.

Uses GPT-4o-mini to extract topic labels from articles, then groups
articles sharing the same topic. Much more accurate than TF-IDF for
Persian text, and cost-effective (~$0.001 per article).

Flow:
1. Get unclustered articles
2. Send titles+summaries to LLM in batches → get topic label + keywords
3. Group articles with same/similar topic labels
4. Create or merge into stories
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article
from app.models.source import Source
from app.models.story import Story
from app.services.llm_utils import call_llm, get_session_stats, parse_json_response

logger = logging.getLogger(__name__)

TOPIC_EXTRACTION_PROMPT = """\
You are a news topic classifier for Iranian media. Given a batch of article titles \
and summaries, identify the main topic/event for each article and group them.

Articles:
{articles}

For each article, return a JSON array with:
- "id": the article number
- "topic": a short topic label in English (max 8 words), e.g. "IRGC intelligence chief killed in airstrike"
- "topic_fa": the same topic in Farsi
- "keywords": 3-5 keywords in the article's language

Articles about the SAME event should get the EXACT SAME topic label.
Be specific — "Iran news" is too vague. "Execution of Ali Fahim protest detainee" is good.

Return valid JSON only:
[{{"id": 1, "topic": "...", "topic_fa": "...", "keywords": ["...", "..."]}}, ...]
"""


async def cluster_with_llm(db: AsyncSession, hours: int = 72) -> dict:
    """Cluster articles using LLM topic extraction.

    Returns stats including cost.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get unclustered articles
    result = await db.execute(
        select(Article)
        .options(selectinload(Article.source))
        .where(
            Article.story_id.is_(None),
            Article.ingested_at >= cutoff,
        )
        .order_by(Article.published_at.desc().nullslast())
    )
    articles = list(result.scalars().all())

    if len(articles) < 2:
        return {"new_stories": 0, "merged": 0, "unclustered": len(articles), "cost_usd": 0}

    logger.info(f"LLM clustering {len(articles)} articles")

    # Process in batches of 20 (to stay within context limits)
    all_topics: dict[int, dict] = {}
    batch_size = 20
    total_cost = 0.0

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        articles_text = ""
        for j, article in enumerate(batch):
            summary = (article.summary or "")[:200]
            articles_text += f"\n{j + 1}. Title: {article.title_original}\n   Summary: {summary}\n"

        prompt = TOPIC_EXTRACTION_PROMPT.format(articles=articles_text)

        try:
            response = await call_llm(prompt, max_tokens=2000, temperature=0.2)
            total_cost += response.cost_usd

            topics = parse_json_response(response.text)
            if topics and isinstance(topics, list):
                for item in topics:
                    idx = item.get("id", 0) - 1
                    if 0 <= idx < len(batch):
                        all_topics[i + idx] = item
        except Exception as e:
            logger.error(f"LLM topic extraction failed for batch {i}: {e}")

    # Group articles by topic label
    topic_groups: dict[str, list[int]] = {}
    for idx, topic_data in all_topics.items():
        label = topic_data.get("topic", "").strip().lower()
        if not label:
            continue
        if label not in topic_groups:
            topic_groups[label] = []
        topic_groups[label].append(idx)

    # Get existing stories for merging
    existing_stories = await _get_existing_stories(db, cutoff)

    stats = {"new_stories": 0, "merged": 0, "unclustered": 0, "cost_usd": round(total_cost, 4)}

    for topic_label, indices in topic_groups.items():
        if len(indices) < 1:
            continue

        cluster_articles_list = [articles[i] for i in indices]
        topic_data = all_topics[indices[0]]

        # Check if this topic matches an existing story
        merged = False
        topic_lower = topic_label.lower()
        for story in existing_stories:
            # Simple string matching on story title
            story_title_lower = (story.title_en or "").lower()
            if (
                topic_lower in story_title_lower
                or story_title_lower in topic_lower
                or _word_overlap(topic_lower, story_title_lower) > 0.5
            ):
                await _merge_into_story(db, story, cluster_articles_list)
                stats["merged"] += len(cluster_articles_list)
                merged = True
                break

        if not merged and len(cluster_articles_list) >= 2:
            story = await _create_story(
                db,
                cluster_articles_list,
                topic_data.get("topic", topic_label),
                topic_data.get("topic_fa", ""),
                topic_data.get("keywords", []),
            )
            existing_stories.append(story)
            stats["new_stories"] += 1
        elif not merged:
            stats["unclustered"] += 1

    await db.commit()

    session = get_session_stats()
    logger.info(
        f"LLM clustering complete: {stats} | "
        f"Session total: ${session['total_cost_usd']:.4f} ({session['total_calls']} calls)"
    )
    return stats


def _word_overlap(a: str, b: str) -> float:
    """Calculate word overlap ratio between two strings."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0
    overlap = len(words_a & words_b)
    return overlap / min(len(words_a), len(words_b))


async def _get_existing_stories(db: AsyncSession, cutoff: datetime) -> list[Story]:
    result = await db.execute(
        select(Story).where(Story.created_at >= cutoff)
    )
    return list(result.scalars().all())


async def _create_story(
    db: AsyncSession,
    articles: list[Article],
    title_en: str,
    title_fa: str,
    keywords: list[str],
) -> Story:
    """Create a new story from a topic cluster."""
    # Coverage analysis
    source_alignments = set()
    for article in articles:
        if article.source:
            source_alignments.add(article.source.state_alignment)

    covered_by_state = bool(source_alignments & {"state", "semi_state"})
    covered_by_diaspora = bool(source_alignments & {"diaspora", "independent"})
    is_blindspot = covered_by_state != covered_by_diaspora
    blindspot_type = None
    if is_blindspot:
        blindspot_type = "state_only" if covered_by_state else "diaspora_only"

    coverage_diversity = len(source_alignments) / 4.0
    source_ids = {a.source_id for a in articles}
    published_dates = [a.published_at for a in articles if a.published_at]
    first_published = min(published_dates) if published_dates else None

    slug = re.sub(r"[^\w\s-]", "", title_en.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:150]
    slug += "-" + uuid.uuid4().hex[:6]

    story = Story(
        title_en=title_en,
        title_fa=title_fa or articles[0].title_original,
        slug=slug,
        article_count=len(articles),
        source_count=len(source_ids),
        covered_by_state=covered_by_state,
        covered_by_diaspora=covered_by_diaspora,
        is_blindspot=is_blindspot,
        blindspot_type=blindspot_type,
        coverage_diversity_score=coverage_diversity,
        topics=keywords,
        first_published_at=first_published,
        last_updated_at=datetime.now(timezone.utc),
        trending_score=_compute_trending(len(articles), first_published),
    )
    db.add(story)
    await db.flush()

    article_ids = [a.id for a in articles]
    await db.execute(
        update(Article).where(Article.id.in_(article_ids)).values(story_id=story.id)
    )
    return story


async def _merge_into_story(db: AsyncSession, story: Story, articles: list[Article]) -> None:
    """Merge articles into existing story."""
    article_ids = [a.id for a in articles]
    await db.execute(
        update(Article).where(Article.id.in_(article_ids)).values(story_id=story.id)
    )

    count_result = await db.execute(
        select(func.count(Article.id)).where(Article.story_id == story.id)
    )
    story.article_count = count_result.scalar() or 0

    source_result = await db.execute(
        select(func.count(func.distinct(Article.source_id))).where(Article.story_id == story.id)
    )
    story.source_count = source_result.scalar() or 0
    story.last_updated_at = datetime.now(timezone.utc)
    story.trending_score = _compute_trending(story.article_count, story.first_published_at)


def _compute_trending(article_count: int, first_published: datetime | None) -> float:
    count_factor = min(article_count / 10.0, 1.0)
    if first_published:
        hours_ago = (datetime.now(timezone.utc) - first_published).total_seconds() / 3600
        recency_factor = max(0, 1.0 - (hours_ago / 72.0))
    else:
        recency_factor = 0.5
    return (count_factor * 0.6) + (recency_factor * 0.4)
