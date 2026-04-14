"""
نیلوفر — تولید زمینه خبری (Editorial Context)

برای ۱۵ موضوع برتر، زمینه خبر ("آنچه باید بدانید") تولید می‌کند
و در فیلد editorial_context_fa ذخیره می‌کند.

Usage:
  python scripts/niloofar_editorial.py
  python scripts/niloofar_editorial.py --limit 5
  python scripts/niloofar_editorial.py --force   # Overwrite existing context
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


EDITORIAL_PROMPT = """تو نیلوفر هستی، سردبیر ارشد با ۲۰ سال تجربه در ژئوپلیتیک خاورمیانه.

وظیفه تو نوشتن «زمینه خبر» (آنچه باید بدانید) برای یک موضوع خبری است.
این متن به خواننده کمک می‌کند بفهمد چرا این خبر مهم است و پیشینه آن چیست.

═══ موضوع ═══
عنوان: {title_fa}
خلاصه: {summary_fa}
تعداد مقالات: {article_count} | تعداد منابع: {source_count}
توزیع منابع: {alignment_dist}

عناوین مقالات:
{article_titles}

# دستورالعمل:
- دقیقا ۲ تا ۳ جمله بنویس
- زمینه تاریخی یا سیاسی مرتبط را توضیح بده
- بدون تکرار عنوان یا خلاصه
- بدون قضاوت یا سوگیری — فقط واقعیت‌ها
- لحن حرفه‌ای و خبری
- فقط متن ساده برگردان، بدون فرمت اضافی"""


async def ensure_column():
    """Add editorial_context_fa column if it doesn't exist."""
    from app.database import async_session
    from sqlalchemy import text

    async with async_session() as db:
        await db.execute(text(
            "ALTER TABLE stories ADD COLUMN IF NOT EXISTS editorial_context_fa JSONB"
        ))
        await db.commit()


async def generate_editorial(story, articles) -> dict | None:
    """Generate editorial context for a single story."""
    import openai
    from app.config import settings
    from app.services.llm_helper import build_openai_params

    # Build alignment distribution
    alignment_counts: dict[str, int] = {}
    article_titles = []
    for a in articles:
        if a.source:
            align = a.source.state_alignment or "unknown"
            alignment_counts[align] = alignment_counts.get(align, 0) + 1
        title = a.title_fa or a.title_original or "بدون عنوان"
        source_name = a.source.name_fa if a.source else "نامشخص"
        article_titles.append(f"- [{source_name}] {title[:100]}")

    alignment_dist = ", ".join(f"{k}: {v}" for k, v in alignment_counts.items())
    titles_block = "\n".join(article_titles[:10])

    prompt = EDITORIAL_PROMPT.format(
        title_fa=story.title_fa or "",
        summary_fa=(story.summary_fa or "")[:300],
        article_count=story.article_count,
        source_count=story.source_count,
        alignment_dist=alignment_dist or "نامشخص",
        article_titles=titles_block,
    )

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.translation_model,  # gpt-4.1-nano for cost efficiency
        prompt=prompt,
        max_tokens=512,
        temperature=0.3,
    )

    try:
        response = await client.chat.completions.create(**params)
        context_text = response.choices[0].message.content.strip()
        return {
            "context": context_text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": settings.translation_model,
        }
    except Exception as e:
        print(f"  خطا در تولید زمینه: {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="نیلوفر — تولید زمینه خبری")
    parser.add_argument("--limit", type=int, default=15, help="Number of top stories (default: 15)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing editorial context")
    args = parser.parse_args()

    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Ensure column exists
    await ensure_column()

    async with async_session() as db:
        query = (
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(args.limit)
        )
        result = await db.execute(query)
        stories = list(result.scalars().all())

    if not stories:
        print("هیچ موضوعی یافت نشد")
        return

    print(f"نیلوفر: تولید زمینه خبری برای {len(stories)} موضوع...")
    stats = {"generated": 0, "skipped": 0, "failed": 0}

    for i, story in enumerate(stories, 1):
        # Skip if already has context and not forcing
        if not args.force and story.editorial_context_fa:
            print(f"  [{i}/{len(stories)}] ⏭ {story.title_fa[:50]} — زمینه موجود")
            stats["skipped"] += 1
            continue

        print(f"  [{i}/{len(stories)}] ✍ {story.title_fa[:50]}...")
        context = await generate_editorial(story, story.articles)

        if context:
            async with async_session() as db:
                from sqlalchemy import update
                await db.execute(
                    update(Story)
                    .where(Story.id == story.id)
                    .values(editorial_context_fa=context)
                )
                await db.commit()
            stats["generated"] += 1
            print(f"      → {context['context'][:80]}...")
        else:
            stats["failed"] += 1

    print(f"\nنتیجه: {stats['generated']} تولید | {stats['skipped']} رد شده | {stats['failed']} خطا")


if __name__ == "__main__":
    asyncio.run(main())
