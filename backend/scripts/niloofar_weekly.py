"""
نیلوفر — خلاصه هفتگی (Weekly Editorial Summary)

تولید گزارش هفتگی شامل:
- ۵ موضوع مهم هفته
- پیش‌بینی‌ها و نتایج آنها
- روند اعتبار منابع
- خروجی به صورت Markdown

Usage:
  python scripts/niloofar_weekly.py
  python scripts/niloofar_weekly.py --days 7
  python scripts/niloofar_weekly.py --output weekly_report.md
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WEEKLY_PROMPT = """تو نیلوفر هستی، سردبیر ارشد با ۲۰ سال تجربه در ژئوپلیتیک خاورمیانه.
وظیفه تو نوشتن گزارش هفتگی دورنگر به زبان فارسی است.

═══ موضوعات مهم هفته ═══
{stories_block}

═══ آمار منابع ═══
{source_stats}

═══ نقاط کور (Blindspots) ═══
{blindspots}

# دستورالعمل:
گزارش هفتگی را به صورت Markdown بنویس با این بخش‌ها:

## ۱. پنج خبر مهم هفته
برای هر خبر: عنوان، چرا مهم است، و تفاوت پوشش رسانه‌ها (۲-۳ جمله)

## ۲. روندهای کلیدی
الگوهای تکراری که در پوشش خبری هفته دیده شد (۳-۵ مورد).
هر مورد دقیقاً این قالب را داشته باشد (عنوان کوتاه + یک توضیح تحلیلی):
- **عنوان روند**: یک جمله تحلیلی که روند را به طور مشخص توضیح دهد.
توضیح نباید خالی باشد — اگر فقط عنوان بنویسی، مورد ناقص است.

## ۳. نقاط کور رسانه‌ای
موضوعاتی که فقط یک طرف پوشش داد و طرف دیگر سکوت کرد

## ۴. عملکرد منابع
کدام منابع بهتر عمل کردند و کدام ضعیف‌تر بودند (بر اساس داده‌ها)

## ۵. چشم‌انداز هفته آینده
بر اساس روندهای فعلی، چه اتفاقاتی محتمل است (۲-۳ پیش‌بینی).
هر پیش‌بینی دقیقاً همان قالب: عنوان + یک جمله تحلیلی.
- **عنوان پیش‌بینی**: یک جمله که پیش‌بینی را مشخص بگوید.

قواعد:
- لحن حرفه‌ای و تحلیلی
- بدون قضاوت ارزشی — فقط تحلیل بر اساس داده
- به فارسی بنویس
- ساختار جمله‌ها فارسی باشد، نه ترجمه‌شده از انگلیسی: فعل در انتهای بند، اتصال با «که» و «چرا که» به جای «و» بی‌مورد، بدون «توسط X» منفعل بی‌دلیل، بدون عبارات کلیشه‌ای ترجمه‌ای مثل «علاوه بر این»، «در پایان روز»، «مورد بررسی قرار گرفت»
- هیچ برچسب اضافی مثل {{story_ids: ...}} به خروجی اضافه نکن"""


async def fetch_weekly_data(days: int):
    """Fetch stories, sources, and blindspots from the past week."""
    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article
    from app.models.source import Source
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with async_session() as db:
        # Top stories of the week
        stories_result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 2)
            .where(Story.created_at >= cutoff)
            .order_by(Story.trending_score.desc())
            .limit(20)
        )
        stories = list(stories_result.scalars().all())

        # Source activity stats
        source_stats_result = await db.execute(
            select(
                Source.name_fa,
                Source.slug,
                Source.state_alignment,
                func.count(Article.id).label("article_count"),
            )
            .join(Article, Article.source_id == Source.id)
            .where(Article.created_at >= cutoff)
            .group_by(Source.id)
            .order_by(func.count(Article.id).desc())
        )
        source_stats = source_stats_result.all()

        # Blindspot stories
        blindspots_result = await db.execute(
            select(Story)
            .where(Story.is_blindspot == True)
            .where(Story.created_at >= cutoff)
            .order_by(Story.trending_score.desc())
            .limit(10)
        )
        blindspots = list(blindspots_result.scalars().all())

    return stories, source_stats, blindspots


def build_weekly_stories_block(stories) -> str:
    """Build text block for top stories."""
    lines = []
    for i, story in enumerate(stories[:10], 1):
        lines.append(f"{i}. {story.title_fa}")
        lines.append(f"   مقالات: {story.article_count} | منابع: {story.source_count}")
        lines.append(f"   امتیاز: {story.trending_score:.1f}")
        if story.summary_fa:
            lines.append(f"   خلاصه: {story.summary_fa[:200]}")

        # Coverage sides
        state_count = sum(
            1 for a in story.articles
            if a.source and a.source.state_alignment in ("state", "semi_state")
        )
        diaspora_count = sum(
            1 for a in story.articles
            if a.source and a.source.state_alignment in ("diaspora", "independent")
        )
        lines.append(f"   پوشش: دولتی={state_count} | دیاسپورا={diaspora_count}")

        if story.is_blindspot:
            lines.append(f"   ⚠ نقطه کور: {story.blindspot_type}")
        lines.append("")
    return "\n".join(lines)


def build_source_stats_block(source_stats) -> str:
    """Build text block for source stats."""
    lines = []
    for name_fa, slug, alignment, count in source_stats:
        lines.append(f"- {name_fa} ({alignment}): {count} مقاله")
    return "\n".join(lines) if lines else "داده‌ای موجود نیست"


def build_blindspots_block(blindspots) -> str:
    """Build text block for blindspot stories."""
    if not blindspots:
        return "نقطه کوری یافت نشد"
    lines = []
    for b in blindspots:
        lines.append(f"- {b.title_fa} ({b.blindspot_type})")
    return "\n".join(lines)


async def generate_weekly_report(stories_block: str, source_stats: str, blindspots: str) -> str:
    """Generate the weekly report via LLM."""
    import openai
    from app.config import settings
    from app.services.llm_helper import build_openai_params

    prompt = WEEKLY_PROMPT.format(
        stories_block=stories_block,
        source_stats=source_stats,
        blindspots=blindspots,
    )

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.translation_model,  # gpt-4.1-nano for cost
        prompt=prompt,
        max_tokens=4000,
        temperature=0.4,
    )

    response = await client.chat.completions.create(**params)
    return response.choices[0].message.content.strip()


async def main():
    parser = argparse.ArgumentParser(description="نیلوفر — خلاصه هفتگی")
    parser.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    args = parser.parse_args()

    print(f"نیلوفر: تولید گزارش هفتگی ({args.days} روز اخیر)...")

    stories, source_stats, blindspots = await fetch_weekly_data(args.days)

    if not stories:
        print("هیچ موضوعی در این بازه یافت نشد")
        return

    print(f"  {len(stories)} موضوع | {len(source_stats)} منبع فعال | {len(blindspots)} نقطه کور")

    stories_block = build_weekly_stories_block(stories)
    source_stats_block = build_source_stats_block(source_stats)
    blindspots_block = build_blindspots_block(blindspots)

    print("  در حال تولید گزارش...")
    report = await generate_weekly_report(stories_block, source_stats_block, blindspots_block)

    # Add metadata header with story references for frontend linking
    now = datetime.now(timezone.utc)
    top_stories_yaml = "\n".join(
        f'  - id: "{s.id}"\n    title: "{(s.title_fa or "").replace(chr(34), "")}"'
        for s in stories[:10]
    )
    header = f"""---
title: گزارش هفتگی نیلوفر
date: {now.strftime('%Y-%m-%d')}
period: {args.days} روز
stories_analyzed: {len(stories)}
sources_active: {len(source_stats)}
blindspots: {len(blindspots)}
generated_by: niloofar (AI journalist)
top_stories:
{top_stories_yaml}
---

"""
    full_report = header + report

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        reports_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "weekly_reports",
        )
        os.makedirs(reports_dir, exist_ok=True)
        output_path = os.path.join(reports_dir, f"weekly_{now.strftime('%Y-%m-%d')}.md")

    with open(output_path, "w", encoding="utf-8") as fp:
        fp.write(full_report)

    # Persist to maintenance_logs with status='weekly_digest' so the
    # /api/v1/stories/weekly-digest endpoint picks it up. The endpoint
    # orders by run_at DESC, so we just insert a new row each run.
    try:
        import uuid as _uuid
        from app.database import async_session
        from sqlalchemy import text as _text
        async with async_session() as db:
            await db.execute(_text(
                "INSERT INTO maintenance_logs (id, run_at, status, results) "
                "VALUES (:id, NOW(), 'weekly_digest', :results)"
            ), {"id": _uuid.uuid4(), "results": full_report})
            await db.commit()
        print("  ✓ گزارش در دیتابیس ذخیره شد")
    except Exception as e:
        print(f"  ⚠ خطا در ذخیره گزارش در دیتابیس: {e}")

    print(f"\n{'=' * 50}")
    print(f"گزارش هفتگی ذخیره شد: {output_path}")
    print(f"{'=' * 50}\n")
    print(report[:500] + "...")


if __name__ == "__main__":
    asyncio.run(main())
