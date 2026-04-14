"""
mina -- Doornegar's Translator/Localizer Persona

Gathers EN/FA title/summary pairs from the DB for Claude to analyze in chat.
No LLM calls -- outputs structured JSON only.

Usage:
  railway run --service doornegar python scripts/mina_translator.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fetch_visible_stories():
    """Fetch all visible stories (article_count >= 5) for translation review."""
    from app.database import async_session
    from app.models.story import Story
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .where(Story.article_count >= 5)
            .order_by(Story.trending_score.desc())
            .limit(30)
        )
        return list(result.scalars().all())


def build_pairs_data(stories) -> list[dict]:
    """Build structured FA/EN pairs for each story."""
    data = []
    for story in stories:
        data.append({
            "story_id": str(story.id),
            "title_en": story.title_en or None,
            "title_fa": story.title_fa or None,
            "summary_en": story.summary_en[:200] if story.summary_en else None,
            "summary_fa": story.summary_fa[:200] if story.summary_fa else None,
            "article_count": story.article_count,
            "has_en_title": bool(story.title_en),
            "has_fa_title": bool(story.title_fa),
            "has_en_summary": bool(story.summary_en),
            "has_fa_summary": bool(story.summary_fa),
        })
    return data


async def db_quality_checks(stories) -> dict:
    """Pure DB checks for translation completeness."""
    missing_fa_title = [
        {"story_id": str(s.id), "title_en": s.title_en}
        for s in stories if not s.title_fa
    ]
    missing_en_title = [
        {"story_id": str(s.id), "title_fa": s.title_fa}
        for s in stories if not s.title_en
    ]
    missing_fa_summary = [
        {"story_id": str(s.id), "title_en": s.title_en or s.title_fa, "article_count": s.article_count}
        for s in stories if not s.summary_fa
    ]
    missing_en_summary = [
        {"story_id": str(s.id), "title_en": s.title_en or s.title_fa, "article_count": s.article_count}
        for s in stories if not s.summary_en
    ]

    return {
        "total_stories": len(stories),
        "missing_fa_title": missing_fa_title,
        "missing_en_title": missing_en_title,
        "missing_fa_summary": missing_fa_summary,
        "missing_en_summary": missing_en_summary,
        "completeness_pct": round(
            (len(stories) - len(missing_fa_title) - len(missing_en_title))
            / (len(stories) * 2) * 100, 1
        ) if stories else 0,
    }


async def main():
    stories = await fetch_visible_stories()
    if not stories:
        print("No visible stories found (need article_count >= 5).")
        return

    pairs_data = build_pairs_data(stories)
    db_checks = await db_quality_checks(stories)

    full_report = {
        "persona": "mina",
        "persona_fa": "مینا",
        "role": "Translator/Localizer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_checks": db_checks,
        "pairs": pairs_data,
    }

    # Print summary header
    print("\n" + "=" * 60)
    print("  MINA — Translator/Localizer Data Gathered")
    print("=" * 60)
    print(f"  Stories evaluated: {db_checks['total_stories']}")
    print(f"  Title completeness: {db_checks['completeness_pct']}%")
    print(f"  Missing FA titles: {len(db_checks['missing_fa_title'])}")
    print(f"  Missing EN titles: {len(db_checks['missing_en_title'])}")
    print(f"  Missing FA summaries: {len(db_checks['missing_fa_summary'])}")
    print(f"  Missing EN summaries: {len(db_checks['missing_en_summary'])}")
    print("=" * 60)

    # Output JSON to stdout
    print("\n" + json.dumps(full_report, ensure_ascii=False, indent=2))

    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), "mina_report.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(full_report, fp, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
