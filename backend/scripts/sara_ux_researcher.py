"""
sara -- Doornegar's UX Researcher Persona

Gathers story data from the DB for Claude to analyze in chat.
No LLM calls -- outputs structured JSON only.

Usage:
  railway run --service doornegar python scripts/sara_ux_researcher.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fetch_stories():
    """Fetch top 10 stories with article counts."""
    from app.database import async_session
    from app.models.story import Story
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(10)
        )
        return list(result.scalars().all())


def build_story_data(stories) -> list[dict]:
    """Build structured data for each story."""
    data = []
    for story in stories:
        data.append({
            "story_id": str(story.id),
            "title_en": story.title_en or None,
            "title_fa": story.title_fa or None,
            "summary_en": story.summary_en[:300] if story.summary_en else None,
            "summary_fa": story.summary_fa[:300] if story.summary_fa else None,
            "article_count": story.article_count,
            "source_count": story.source_count,
            "is_blindspot": story.is_blindspot,
            "blindspot_type": story.blindspot_type,
            "topics": story.topics,
            "trending_score": float(story.trending_score) if story.trending_score else None,
        })
    return data


async def main():
    stories = await fetch_stories()
    if not stories:
        print("No stories found to evaluate.")
        return

    story_count = len(stories)
    story_data = build_story_data(stories)

    # DB-level findings
    db_findings = {
        "stories_evaluated": story_count,
        "stories_missing_en_summary": sum(1 for s in stories if not s.summary_en),
        "stories_missing_fa_summary": sum(1 for s in stories if not s.summary_fa),
        "stories_missing_en_title": sum(1 for s in stories if not s.title_en),
        "stories_missing_fa_title": sum(1 for s in stories if not s.title_fa),
        "blindspot_stories": sum(1 for s in stories if s.is_blindspot),
    }

    full_report = {
        "persona": "sara",
        "persona_fa": "سارا",
        "role": "UX Researcher",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_findings": db_findings,
        "stories": story_data,
    }

    # Print summary header
    print("\n" + "=" * 60)
    print("  SARA — UX Researcher Data Gathered")
    print("=" * 60)
    print(f"  Stories evaluated: {story_count}")
    print(f"  Missing EN summaries: {db_findings['stories_missing_en_summary']}")
    print(f"  Missing FA summaries: {db_findings['stories_missing_fa_summary']}")
    print(f"  Missing EN titles: {db_findings['stories_missing_en_title']}")
    print(f"  Missing FA titles: {db_findings['stories_missing_fa_title']}")
    print(f"  Blindspot stories: {db_findings['blindspot_stories']}")
    print("=" * 60)

    # Output JSON to stdout
    print("\n" + json.dumps(full_report, ensure_ascii=False, indent=2))

    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), "sara_report.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(full_report, fp, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
