"""
reza -- Doornegar's Devil's Advocate Persona

Gathers stories with bias analysis data from the DB for Claude to analyze in chat.
No LLM calls -- outputs structured JSON only.

Usage:
  railway run --service doornegar python scripts/reza_devils_advocate.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fetch_stories_with_bias():
    """Fetch top 15 stories with their bias/summary analysis."""
    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 3)
            .order_by(Story.trending_score.desc())
            .limit(15)
        )
        return list(result.scalars().all())


def build_story_data(stories) -> list[dict]:
    """Build structured data with bias analysis for each story."""
    data = []
    for story in stories:
        # Source alignment distribution
        alignment_counts: dict[str, int] = {}
        for a in story.articles:
            if a.source:
                align = a.source.state_alignment or "unknown"
                alignment_counts[align] = alignment_counts.get(align, 0) + 1

        # Article titles grouped by alignment
        titles_by_alignment: dict[str, list[str]] = {}
        for a in story.articles:
            align = a.source.state_alignment if a.source else "unknown"
            title = a.title_fa or a.title_original or "?"
            titles_by_alignment.setdefault(align, [])
            titles_by_alignment[align].append(title[:80])

        # Editorial context
        editorial_context = None
        if story.editorial_context_fa and isinstance(story.editorial_context_fa, dict):
            editorial_context = story.editorial_context_fa

        # Coverage type
        coverage = []
        if story.covered_by_state:
            coverage.append("state")
        if story.covered_by_diaspora:
            coverage.append("diaspora")

        data.append({
            "story_id": str(story.id),
            "title_fa": story.title_fa or None,
            "title_en": story.title_en or None,
            "summary_fa": story.summary_fa[:300] if story.summary_fa else None,
            "summary_en": story.summary_en[:300] if story.summary_en else None,
            "coverage": coverage if coverage else ["unknown"],
            "is_blindspot": story.is_blindspot,
            "blindspot_type": story.blindspot_type,
            "alignment_distribution": alignment_counts,
            "titles_by_alignment": titles_by_alignment,
            "editorial_context": editorial_context,
            "article_count": story.article_count,
        })
    return data


async def main():
    stories = await fetch_stories_with_bias()
    if not stories:
        print("No stories found for bias challenge.")
        return

    story_data = build_story_data(stories)

    # DB-level coverage distribution
    coverage_dist: dict[str, int] = {}
    for s in stories:
        if s.covered_by_state and not s.covered_by_diaspora:
            key = "state_only"
        elif s.covered_by_diaspora and not s.covered_by_state:
            key = "diaspora_only"
        elif s.covered_by_state and s.covered_by_diaspora:
            key = "both"
        else:
            key = "unknown"
        coverage_dist[key] = coverage_dist.get(key, 0) + 1

    db_findings = {
        "stories_analyzed": len(stories),
        "coverage_distribution": coverage_dist,
        "blindspot_count": sum(1 for s in stories if s.is_blindspot),
    }

    full_report = {
        "persona": "reza",
        "persona_fa": "رضا",
        "role": "Devil's Advocate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_findings": db_findings,
        "stories": story_data,
    }

    # Print summary header
    print("\n" + "=" * 60)
    print("  REZA — Devil's Advocate Data Gathered")
    print("=" * 60)
    print(f"  Stories analyzed: {len(stories)}")
    print(f"  Coverage distribution: {json.dumps(coverage_dist)}")
    print(f"  Blindspot stories: {db_findings['blindspot_count']}")
    print("=" * 60)

    # Output JSON to stdout
    print("\n" + json.dumps(full_report, ensure_ascii=False, indent=2))

    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), "reza_report.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(full_report, fp, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
