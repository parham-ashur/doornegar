"""Story clustering service.

Groups articles about the same event/topic into "stories" using
embedding similarity. This is the core feature that enables
cross-source comparison.

Algorithm:
1. Get unclustered articles from the last 72 hours
2. Compute pairwise cosine similarity on their embeddings
3. Group articles with similarity > threshold using connected components
4. For each group, either merge into existing story or create new one
5. Update story metadata (coverage flags, trending score, etc.)
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.article import Article
from app.models.source import Source
from app.models.story import Story
from app.nlp.embeddings import cosine_similarity, cosine_similarity_matrix

logger = logging.getLogger(__name__)


def find_connected_components(similarity_matrix: np.ndarray, threshold: float) -> list[list[int]]:
    """Find connected components in the similarity graph.

    Two articles are connected if their cosine similarity exceeds the threshold.
    Uses BFS to find all connected components.

    Returns:
        List of clusters, each cluster is a list of article indices.
    """
    n = similarity_matrix.shape[0]
    visited = set()
    components = []

    for start in range(n):
        if start in visited:
            continue
        # BFS from this node
        component = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            # Find neighbors above threshold
            for neighbor in range(n):
                if neighbor not in visited and similarity_matrix[node, neighbor] >= threshold:
                    queue.append(neighbor)
        if len(component) >= 2:  # A story needs at least 2 articles
            components.append(component)

    return components


def compute_cluster_centroid(embeddings: list[list[float]]) -> list[float]:
    """Compute the centroid (mean) of a set of embeddings."""
    matrix = np.array(embeddings)
    centroid = matrix.mean(axis=0)
    # Normalize the centroid
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    return centroid.tolist()


def generate_slug(title: str) -> str:
    """Generate a URL-friendly slug from a title."""
    # Remove Persian/Arabic characters for slug, keep English
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    if not slug or len(slug) < 3:
        slug = f"story-{uuid.uuid4().hex[:8]}"
    # Truncate and add uniqueness
    slug = slug[:150] + "-" + uuid.uuid4().hex[:6]
    return slug


async def cluster_articles(db: AsyncSession) -> dict:
    """Main clustering pipeline.

    Returns dict with stats: {new_stories, merged, unclustered}.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)

    # Get unclustered articles with embeddings from the last 72 hours
    result = await db.execute(
        select(Article)
        .options(selectinload(Article.source))
        .where(
            Article.story_id.is_(None),
            Article.embedding.isnot(None),
            Article.ingested_at >= cutoff,
        )
        .order_by(Article.published_at.desc().nullslast())
    )
    articles = list(result.scalars().all())

    if len(articles) < 2:
        logger.info(f"Only {len(articles)} unclustered articles — skipping clustering")
        return {"new_stories": 0, "merged": 0, "unclustered": len(articles)}

    logger.info(f"Clustering {len(articles)} unclustered articles")

    # Build embedding matrix
    embeddings = [list(a.embedding) for a in articles]
    sim_matrix = cosine_similarity_matrix(embeddings)

    # Find clusters
    components = find_connected_components(sim_matrix, settings.clustering_similarity_threshold)
    logger.info(f"Found {len(components)} potential story clusters")

    # Get existing recent stories for potential merging
    existing_stories = await _get_recent_stories_with_centroids(db, cutoff)

    stats = {"new_stories": 0, "merged": 0, "unclustered": 0}

    for component_indices in components:
        cluster_articles = [articles[i] for i in component_indices]
        cluster_embeddings = [embeddings[i] for i in component_indices]
        centroid = compute_cluster_centroid(cluster_embeddings)

        # Check if this cluster matches an existing story
        merged = False
        for story, story_centroid in existing_stories:
            if story_centroid is not None:
                sim = cosine_similarity(centroid, story_centroid)
                if sim >= settings.story_merge_threshold:
                    # Merge into existing story
                    await _merge_into_story(db, story, cluster_articles)
                    stats["merged"] += len(cluster_articles)
                    merged = True
                    logger.info(
                        f"Merged {len(cluster_articles)} articles into story '{story.slug}'"
                    )
                    break

        if not merged:
            # Create new story
            story = await _create_story(db, cluster_articles)
            existing_stories.append((story, centroid))
            stats["new_stories"] += 1
            logger.info(
                f"Created new story '{story.slug}' with {len(cluster_articles)} articles"
            )

    # Count remaining unclustered
    clustered_ids = set()
    for component in components:
        for idx in component:
            clustered_ids.add(articles[idx].id)
    stats["unclustered"] = len(articles) - len(clustered_ids)

    await db.commit()
    logger.info(f"Clustering complete: {stats}")
    return stats


async def _get_recent_stories_with_centroids(
    db: AsyncSession, cutoff: datetime
) -> list[tuple[Story, list[float] | None]]:
    """Get recent stories and compute their embedding centroids."""
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles))
        .where(Story.created_at >= cutoff)
    )
    stories = result.scalars().all()

    stories_with_centroids = []
    for story in stories:
        article_embeddings = [
            list(a.embedding) for a in story.articles if a.embedding is not None
        ]
        if article_embeddings:
            centroid = compute_cluster_centroid(article_embeddings)
        else:
            centroid = None
        stories_with_centroids.append((story, centroid))

    return stories_with_centroids


async def _create_story(db: AsyncSession, articles: list[Article]) -> Story:
    """Create a new story from a cluster of articles."""
    # Use the most recent article's title as story title
    # (In Phase 2, we'll use LLM to generate a neutral headline)
    primary_article = sorted(articles, key=lambda a: a.published_at or a.ingested_at)[-1]

    title_fa = primary_article.title_original
    title_en = primary_article.title_en or primary_article.title_original

    # Determine coverage flags
    source_alignments = set()
    for article in articles:
        if article.source:
            source_alignments.add(article.source.state_alignment)

    covered_by_state = bool(source_alignments & {"state", "semi_state"})
    covered_by_diaspora = bool(source_alignments & {"diaspora", "independent"})

    is_blindspot = covered_by_state != covered_by_diaspora  # Only one side covers it
    blindspot_type = None
    if is_blindspot:
        if covered_by_state and not covered_by_diaspora:
            blindspot_type = "state_only"
        elif covered_by_diaspora and not covered_by_state:
            blindspot_type = "diaspora_only"

    # Coverage diversity: what fraction of alignment types are represented
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
        slug=generate_slug(title_en if title_en != title_fa else f"story-{len(articles)}"),
        article_count=len(articles),
        source_count=len(source_ids),
        covered_by_state=covered_by_state,
        covered_by_diaspora=covered_by_diaspora,
        is_blindspot=is_blindspot,
        blindspot_type=blindspot_type,
        coverage_diversity_score=coverage_diversity,
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


async def _merge_into_story(db: AsyncSession, story: Story, articles: list[Article]) -> None:
    """Merge new articles into an existing story, updating metadata."""
    article_ids = [a.id for a in articles]
    await db.execute(
        update(Article)
        .where(Article.id.in_(article_ids))
        .values(story_id=story.id)
    )

    # Recount
    count_result = await db.execute(
        select(func.count(Article.id)).where(Article.story_id == story.id)
    )
    story.article_count = count_result.scalar() or 0

    source_result = await db.execute(
        select(func.count(func.distinct(Article.source_id))).where(Article.story_id == story.id)
    )
    story.source_count = source_result.scalar() or 0

    # Update coverage flags
    alignment_result = await db.execute(
        select(Source.state_alignment)
        .join(Article, Article.source_id == Source.id)
        .where(Article.story_id == story.id)
        .distinct()
    )
    alignments = {row[0] for row in alignment_result.all()}

    story.covered_by_state = bool(alignments & {"state", "semi_state"})
    story.covered_by_diaspora = bool(alignments & {"diaspora", "independent"})
    story.is_blindspot = story.covered_by_state != story.covered_by_diaspora
    if story.is_blindspot:
        story.blindspot_type = (
            "state_only" if story.covered_by_state else "diaspora_only"
        )
    else:
        story.blindspot_type = None

    story.coverage_diversity_score = len(alignments) / 4.0
    story.last_updated_at = datetime.now(timezone.utc)
    story.trending_score = _compute_trending_score(
        story.article_count, story.first_published_at
    )


def _compute_trending_score(article_count: int, first_published: datetime | None) -> float:
    """Compute a trending score based on article count and recency.

    Higher score = more articles + more recent.
    """
    count_factor = min(article_count / 10.0, 1.0)  # Cap at 10 articles

    if first_published:
        hours_ago = (datetime.now(timezone.utc) - first_published).total_seconds() / 3600
        recency_factor = max(0, 1.0 - (hours_ago / 72.0))  # Decay over 72 hours
    else:
        recency_factor = 0.5

    return (count_factor * 0.6) + (recency_factor * 0.4)
