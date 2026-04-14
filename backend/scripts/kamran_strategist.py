"""
kamran -- Doornegar's Geopolitical Strategist Persona

Gathers story and Telegram data from the DB for Claude to analyze in chat.
No LLM calls -- outputs structured JSON only.

Usage:
  railway run --service doornegar python scripts/kamran_strategist.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fetch_stories_with_articles():
    """Fetch top 20 stories with articles grouped by source alignment."""
    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(20)
        )
        return list(result.scalars().all())


def build_story_data(stories) -> list[dict]:
    """Build structured data with articles grouped by alignment."""
    data = []
    for story in stories:
        # Group articles by source alignment
        by_alignment: dict[str, list[dict]] = {}
        for a in story.articles:
            align = a.source.state_alignment if a.source else "unknown"
            by_alignment.setdefault(align, [])
            by_alignment[align].append({
                "source_name_fa": a.source.name_fa if a.source else None,
                "source_name_en": a.source.name_en if a.source else None,
                "title_fa": a.title_fa or a.title_original or None,
                "title_en": a.title_en or None,
            })

        # Extract telegram analysis if present
        telegram = None
        if story.telegram_analysis and isinstance(story.telegram_analysis, dict):
            telegram = {}
            for key in ("summary_fa", "narrative_fa", "dominant_framing", "key_voices"):
                if key in story.telegram_analysis:
                    telegram[key] = story.telegram_analysis[key]

        data.append({
            "story_id": str(story.id),
            "title_fa": story.title_fa or None,
            "title_en": story.title_en or None,
            "summary_fa": story.summary_fa[:250] if story.summary_fa else None,
            "summary_en": story.summary_en[:250] if story.summary_en else None,
            "article_count": story.article_count,
            "trending_score": float(story.trending_score) if story.trending_score else None,
            "is_blindspot": story.is_blindspot,
            "blindspot_type": story.blindspot_type,
            "covered_by_state": story.covered_by_state,
            "covered_by_diaspora": story.covered_by_diaspora,
            "articles_by_alignment": by_alignment,
            "telegram_analysis": telegram,
        })
    return data


async def main():
    stories = await fetch_stories_with_articles()
    if not stories:
        print("No stories found for analysis.")
        return

    story_data = build_story_data(stories)

    # DB context stats
    blindspot_count = sum(1 for s in stories if s.is_blindspot)
    state_only = sum(1 for s in stories if s.covered_by_state and not s.covered_by_diaspora)
    diaspora_only = sum(1 for s in stories if s.covered_by_diaspora and not s.covered_by_state)
    has_telegram = sum(1 for s in stories if s.telegram_analysis)

    db_findings = {
        "stories_analyzed": len(stories),
        "blindspot_count": blindspot_count,
        "state_only_count": state_only,
        "diaspora_only_count": diaspora_only,
        "both_coverage_count": sum(1 for s in stories if s.covered_by_state and s.covered_by_diaspora),
        "stories_with_telegram": has_telegram,
    }

    full_report = {
        "persona": "kamran",
        "persona_fa": "کامران",
        "role": "Geopolitical Strategist",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_findings": db_findings,
        "stories": story_data,
    }

    # Print summary header
    print("\n" + "=" * 60)
    print("  KAMRAN — Geopolitical Strategist Data Gathered")
    print("=" * 60)
    print(f"  Stories analyzed: {len(stories)}")
    print(f"  Blindspots: {blindspot_count}")
    print(f"  State-only: {state_only}")
    print(f"  Diaspora-only: {diaspora_only}")
    print(f"  Stories with Telegram data: {has_telegram}")
    print("=" * 60)

    # Output JSON to stdout
    print("\n" + json.dumps(full_report, ensure_ascii=False, indent=2))

    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), "kamran_report.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(full_report, fp, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
