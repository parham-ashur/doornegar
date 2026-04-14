"""
نیلوفر — امتیازدهی منابع (Source Scoring)

بر اساس داده‌های واقعی، عملکرد هر منبع را ارزیابی می‌کند:
- مقایسه ادعاها/چارچوب‌بندی هر منبع با اجماع اکثریت
- تولید امتیاز دقت و سوگیری
- ذخیره در فایل JSON برای استفاده در خط‌لوله تحلیل

Usage:
  python scripts/niloofar_source_scores.py
  python scripts/niloofar_source_scores.py --days 30
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOURCE_SCORING_PROMPT = """تو نیلوفر هستی، سردبیر ارشد با ۲۰ سال تجربه در ارزیابی رسانه‌ها.

وظیفه تو ارزیابی عملکرد یک منبع خبری بر اساس مقالاتش در موضوعات مشترک است.

═══ منبع: {source_name} ({source_alignment}) ═══

در {story_count} موضوع خبری مشارکت داشته.

نمونه عناوین این منبع و مقایسه با اجماع سایر منابع:

{comparisons}

# ارزیابی کن (فقط JSON برگردان):
{{
  "accuracy": 0.0-1.0,
  "bias_level": 0.0-1.0,
  "framing_consistency": 0.0-1.0,
  "notes": "توضیح فارسی ۱-۲ جمله درباره الگوی کلی این منبع"
}}

- accuracy: چقدر عناوین/محتوای منبع با واقعیت و اجماع همخوانی دارد (۱=بسیار دقیق)
- bias_level: میزان سوگیری در چارچوب‌بندی (۰=بی‌طرف، ۱=بسیار جهت‌دار)
- framing_consistency: آیا منبع ثبات در چارچوب‌بندی دارد (۱=ثابت)
- notes: توضیح کوتاه"""


async def fetch_source_data(days: int):
    """Fetch all sources and their articles in shared stories."""
    from app.database import async_session
    from app.models.source import Source
    from app.models.article import Article
    from app.models.story import Story
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with async_session() as db:
        # Get all active sources
        sources_result = await db.execute(
            select(Source).where(Source.is_active == True)
        )
        sources = list(sources_result.scalars().all())

        # Get stories with multiple sources from the period
        stories_result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 3, Story.source_count >= 2)
            .where(Story.created_at >= cutoff)
            .order_by(Story.trending_score.desc())
            .limit(100)
        )
        stories = list(stories_result.scalars().all())

    return sources, stories


def build_comparisons(source_slug: str, stories) -> tuple[str, int]:
    """Build comparison block for a source across stories."""
    lines = []
    story_count = 0

    for story in stories:
        # Find this source's articles in the story
        source_articles = [a for a in story.articles if a.source and a.source.slug == source_slug]
        other_articles = [a for a in story.articles if a.source and a.source.slug != source_slug]

        if not source_articles or not other_articles:
            continue

        story_count += 1
        if story_count > 15:  # Limit to 15 examples
            break

        source_title = source_articles[0].title_fa or source_articles[0].title_original or "?"
        other_titles = [
            f"[{a.source.name_fa}] {(a.title_fa or a.title_original or '?')[:60]}"
            for a in other_articles[:3]
        ]

        lines.append(f"موضوع: {story.title_fa[:60]}")
        lines.append(f"  این منبع: {source_title[:80]}")
        lines.append(f"  سایر منابع: {' | '.join(other_titles)}")
        lines.append("")

    return "\n".join(lines), story_count


async def score_source(source, comparisons: str, story_count: int) -> dict | None:
    """Score a single source using LLM."""
    import openai
    from app.config import settings
    from app.services.llm_helper import build_openai_params

    prompt = SOURCE_SCORING_PROMPT.format(
        source_name=source.name_fa,
        source_alignment=source.state_alignment,
        story_count=story_count,
        comparisons=comparisons,
    )

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.translation_model,  # gpt-4.1-nano for cost
        prompt=prompt,
        max_tokens=512,
        temperature=0.2,
    )

    try:
        response = await client.chat.completions.create(**params)
        text = response.choices[0].message.content.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        return json.loads(text)
    except Exception as e:
        print(f"  خطا در امتیازدهی {source.slug}: {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="نیلوفر — امتیازدهی منابع")
    parser.add_argument("--days", type=int, default=14, help="Look back N days (default: 14)")
    args = parser.parse_args()

    print(f"نیلوفر: ارزیابی منابع بر اساس {args.days} روز اخیر...")

    sources, stories = await fetch_source_data(args.days)
    if not stories:
        print("هیچ موضوع مشترکی یافت نشد")
        return

    print(f"  {len(sources)} منبع | {len(stories)} موضوع مشترک\n")

    scores = {}
    for source in sources:
        comparisons, story_count = build_comparisons(source.slug, stories)
        if story_count < 2:
            print(f"  ⏭ {source.name_fa} — مشارکت ناکافی ({story_count} موضوع)")
            continue

        print(f"  📊 {source.name_fa} ({source.state_alignment}) — {story_count} موضوع...")
        result = await score_source(source, comparisons, story_count)

        if result:
            scores[source.slug] = {
                "name_fa": source.name_fa,
                "name_en": source.name_en,
                "state_alignment": source.state_alignment,
                "story_count_evaluated": story_count,
                **result,
            }
            print(f"      accuracy={result.get('accuracy', '?')} bias={result.get('bias_level', '?')}")

    # Save to JSON file
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_days": args.days,
        "stories_analyzed": len(stories),
        "sources": scores,
    }

    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
    )
    os.makedirs(output_path, exist_ok=True)
    output_file = os.path.join(output_path, "source_scores.json")

    with open(output_file, "w", encoding="utf-8") as fp:
        json.dump(output, fp, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"نتیجه: {len(scores)} منبع امتیازدهی شد")
    print(f"ذخیره شد: {output_file}")

    # Print summary table
    print(f"\n{'منبع':<25} {'دقت':<8} {'سوگیری':<8} {'راستا':<12}")
    print("-" * 55)
    for slug, data in sorted(scores.items(), key=lambda x: x[1].get("accuracy", 0), reverse=True):
        print(f"{data['name_fa']:<25} {data.get('accuracy', '?'):<8} {data.get('bias_level', '?'):<8} {data['state_alignment']:<12}")


if __name__ == "__main__":
    asyncio.run(main())
