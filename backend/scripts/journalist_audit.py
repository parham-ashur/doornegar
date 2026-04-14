"""
نیلوفر — Doornegar's AI Journalist Persona

Senior geopolitics editor with 20 years of experience.
Can read, evaluate, edit, and correct all content on Doornegar.

Capabilities:
- Edit story titles, summaries, images
- Remove irrelevant articles from stories
- Merge duplicate stories
- Flag quality issues
- Propose pipeline/prompt improvements

Usage:
  railway run --service doornegar python scripts/journalist_audit.py
  railway run --service doornegar python scripts/journalist_audit.py --apply
"""

import asyncio
import json
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JOURNALIST_PROMPT = """تو نیلوفر هستی، یک سردبیر ارشد با ۲۰ سال تجربه در ژئوپلیتیک خاورمیانه.
وظیفه تو بررسی و اصلاح محتوای صفحه اول سایت دورنگر است.

دورنگر یک پلتفرم شفافیت رسانه‌ای ایران است که اخبار رسانه‌های محافظه‌کار و اپوزیسیون را مقایسه می‌کند.

═══ موضوعات صفحه اول ═══
{stories_block}

# بررسی کن:

۱. **عنوان‌ها**: آیا مثل تیتر روزنامه هستند؟ عبارات ممنوع: «تحلیل سوگیری»، «پوشش رسانه‌ای»، «نقش عوامل خارجی»، «بررسی»، «مقایسه». عنوان باید فقط رویداد را بگوید.

۲. **مقالات نامرتبط**: آیا مقاله‌ای هست که به موضوع ربط ندارد؟ شناسه مقاله را بده.

۳. **موضوعات تکراری**: آیا دو یا چند موضوع درباره یک رویداد هستند و باید ادغام شوند؟

۴. **خلاصه‌ها**: آیا خلاصه‌ها دقیق و بدون تکرار و کلیشه هستند؟ خلاصه جدید بنویس اگر ضعیف است.

۵. **ترتیب**: آیا مهم‌ترین خبر بالاست؟

۶. **تصاویر**: آیا تصویری نامناسب یا تکراری وجود دارد؟

۷. **پیشنهاد برای خط‌لوله**: آیا مشکل سیستمی می‌بینی که باید در کد/پرامپت اصلاح شود؟

۸. **تطابق ترجمه**: آیا عنوان فارسی و انگلیسی هر موضوع یک مفهوم را می‌رسانند؟ اگر ترجمه نادرست یا ناقص است، گزارش کن.

۹. **موضوعات کهنه**: آیا موضوعی هست که ۳ روز یا بیشتر مقاله جدید نداشته ولی هنوز در صفحه اول است؟ باید آرشیو شود.

۱۰. **سکوت منابع**: آیا گروهی از منابع هم‌راستا (مثلا ۳+ منبع دولتی) همگی درباره یک موضوع مهم سکوت کرده‌اند؟

۱۱. **تغییر واژگان روایی**: آیا منبعی واژه‌ای را که قبلا برای یک مفهوم استفاده می‌کرد تغییر داده؟ (مثلا از «اعتراضات» به «اغتشاشات» یا برعکس)

۱۲. **برچسب اعتبار ادعاها**: برای هر ادعای کلیدی (key_claim) در تحلیل تلگرام، بررسی کن:
  - آیا برچسب اعتبار (مشکوک، تأیید نشده، تأیید شده، تبلیغاتی) وجود دارد؟ اگر نه، یکی پیشنهاد کن.
  - آیا برچسب فعلی درست است؟ اگر نه، برچسب صحیح را بنویس.
  - آیا متن ادعا طولانی است؟ نسخه کوتاه‌تر بنویس (حداکثر ۲ جمله).
  - آیا ادعا واقعاً یک ادعا است یا فقط یک گزارش عادی؟ اگر گزارش عادی است، حذف کن.

۱۳. **جایگاه رسانه‌ها**: برای هر موضوع بررسی کن:
  - آیا همه رسانه‌هایی که مقاله دارند در نمودار نشان داده شده‌اند؟
  - آیا جایگاه هر رسانه درست است؟ (محافظه‌کار سمت راست، اپوزیسیون سمت چپ)
  - آیا لوگوی رسانه‌ها وجود دارد؟ اگر لوگو ندارد، گزارش کن.
  - آیا رسانه‌هایی هستند که مقاله دارند ولی در لیست منابع نیستند؟

# خروجی JSON:

فقط JSON برگردان. هر یافته باید fix_type و fix_data داشته باشد تا قابل اجرا باشد.

{
  "overall_grade": "A/B/C/D",
  "summary": "ارزیابی کلی ۲-۳ جمله فارسی",
  "findings": [
    {
      "type": "bad_title | irrelevant_article | merge_stories | bad_summary | wrong_order | bad_image | pipeline_suggestion | translation_mismatch | stale_story | source_silence | vocabulary_shift | claim_label",
      "severity": "critical | high | medium | low",
      "story_id": "شناسه",
      "story_title": "عنوان فعلی",
      "description_fa": "توضیح مشکل",
      "proposed_fix": "اصلاح پیشنهادی",
      "fix_type": "rename_story | update_summary | remove_article | merge_stories | update_image | reorder | pipeline_change | update_claim",
      "fix_data": {
        "new_title_fa": "عنوان جدید (برای rename_story)",
        "new_summary_fa": "خلاصه جدید (برای update_summary)",
        "article_id": "شناسه مقاله (برای remove_article)",
        "merge_into": "شناسه موضوع مقصد (برای merge_stories)",
        "new_image_url": "آدرس تصویر (برای update_image)",
        "claim_index": "شماره ادعا (برای update_claim)",
        "new_claim_text": "متن کوتاه‌شده ادعا (برای update_claim)",
        "claim_label": "مشکوک | تأیید نشده | تأیید شده | تبلیغاتی (برای update_claim)",
        "pipeline_description": "توضیح تغییر پیشنهادی (برای pipeline_change)"
      }
    }
  ]
}"""


async def fetch_stories():
    """Fetch top stories with articles for review."""
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
            .limit(25)
        )
        return list(result.scalars().all())


def build_stories_block(stories) -> str:
    """Build text representation of stories for the prompt."""
    from datetime import datetime, timezone

    lines = []
    now = datetime.now(timezone.utc)
    for i, story in enumerate(stories, 1):
        lines.append(f"═══ موضوع {i} ═══")
        lines.append(f"شناسه: {story.id}")
        lines.append(f"عنوان فارسی: {story.title_fa}")
        lines.append(f"عنوان انگلیسی: {story.title_en}")
        lines.append(f"تعداد مقالات: {story.article_count} | منابع: {story.source_count}")
        lines.append(f"امتیاز: {story.trending_score:.1f}")

        # Age info for stale detection
        if story.last_updated_at:
            age_days = (now - story.last_updated_at).total_seconds() / 86400
            lines.append(f"آخرین به‌روزرسانی: {age_days:.1f} روز پیش")

        if story.summary_fa:
            lines.append(f"خلاصه: {story.summary_fa[:200]}")

        # Alignment distribution for silence detection
        alignment_counts: dict[str, int] = {}
        for a in story.articles:
            if a.source:
                align = a.source.state_alignment or "unknown"
                alignment_counts[align] = alignment_counts.get(align, 0) + 1
        if alignment_counts:
            dist = ", ".join(f"{k}:{v}" for k, v in alignment_counts.items())
            lines.append(f"توزیع منابع: {dist}")

        for j, article in enumerate(story.articles[:8], 1):
            source_name = article.source.name_fa if article.source else "نامشخص"
            alignment = article.source.state_alignment if article.source else "?"
            title = article.title_fa or article.title_original or "بدون عنوان"
            lines.append(f"  مقاله {j} (id={article.id}): [{source_name} ({alignment})] {title[:80]}")

        # Include telegram claims for label verification
        tg = story.telegram_analysis or {}
        claims = tg.get("key_claims", [])
        if claims:
            lines.append(f"  ادعاهای تلگرام ({len(claims)}):")
            for c in claims[:5]:
                text = c.get("text", c) if isinstance(c, dict) else str(c)
                lines.append(f"    - {text[:100]}")

        lines.append("")
    return "\n".join(lines)


async def call_niloofar(stories_block: str) -> dict | None:
    """Send content to Niloofar for review."""
    import openai
    from app.config import settings
    from app.services.llm_helper import build_openai_params

    print("نیلوفر در حال بررسی محتوا...")
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.story_analysis_model or "gpt-4o-mini",
        prompt=JOURNALIST_PROMPT.replace("{stories_block}", stories_block),
        max_tokens=4000,
        temperature=0.3,
    )
    response = await client.chat.completions.create(**params)
    text = response.choices[0].message.content.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"خطا در تجزیه JSON: {text[:300]}")
        return None


async def apply_fix(finding: dict) -> str:
    """Apply a single fix to the database. Returns status message."""
    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article
    from sqlalchemy import select, func, update

    fix_type = finding.get("fix_type", "")
    fix_data = finding.get("fix_data", {})
    story_id = finding.get("story_id", "")

    async with async_session() as db:
        if fix_type == "rename_story" and fix_data.get("new_title_fa"):
            story = await db.get(Story, story_id)
            if story:
                old = story.title_fa
                story.title_fa = fix_data["new_title_fa"]
                await db.commit()
                return f"✓ عنوان تغییر کرد: {old[:40]} → {story.title_fa[:40]}"
            return "✗ موضوع یافت نشد"

        elif fix_type == "update_summary" and fix_data.get("new_summary_fa"):
            story = await db.get(Story, story_id)
            if story:
                story.summary_fa = fix_data["new_summary_fa"]
                await db.commit()
                return f"✓ خلاصه به‌روز شد"
            return "✗ موضوع یافت نشد"

        elif fix_type == "remove_article" and fix_data.get("article_id"):
            article = await db.get(Article, fix_data["article_id"])
            if article:
                article.story_id = None
                # Recount
                if story_id:
                    actual = (await db.execute(
                        select(func.count(Article.id)).where(Article.story_id == story_id)
                    )).scalar() or 0
                    story = await db.get(Story, story_id)
                    if story:
                        story.article_count = actual
                await db.commit()
                return f"✓ مقاله حذف شد از موضوع"
            return "✗ مقاله یافت نشد"

        elif fix_type == "merge_stories" and fix_data.get("merge_into"):
            target_id = fix_data["merge_into"]
            moved = await db.execute(
                update(Article).where(Article.story_id == story_id).values(story_id=target_id)
            )
            # Hide source story
            source = await db.get(Story, story_id)
            if source:
                source.article_count = 0
                source.trending_score = -100
            # Recount target
            actual = (await db.execute(
                select(func.count(Article.id)).where(Article.story_id == target_id)
            )).scalar() or 0
            source_count = (await db.execute(
                select(func.count(func.distinct(Article.source_id))).where(Article.story_id == target_id)
            )).scalar() or 0
            target = await db.get(Story, target_id)
            if target:
                target.article_count = actual
                target.source_count = source_count
                target.summary_fa = None
                target.telegram_analysis = None
            await db.commit()
            return f"✓ ادغام شد: {moved.rowcount} مقاله منتقل شد"

        elif fix_type == "update_image" and fix_data.get("new_image_url"):
            story = await db.get(Story, story_id)
            if story:
                story.image_url = fix_data["new_image_url"]
                await db.commit()
                return f"✓ تصویر به‌روز شد"
            return "✗ موضوع یافت نشد"

        elif fix_type == "update_claim":
            story = await db.get(Story, story_id)
            if story and story.telegram_analysis:
                tg = story.telegram_analysis
                claims = tg.get("key_claims", [])
                idx = fix_data.get("claim_index", 0)
                if isinstance(idx, int) and 0 <= idx < len(claims):
                    new_text = fix_data.get("new_claim_text")
                    label = fix_data.get("claim_label", "")
                    if new_text:
                        # Append label keyword so frontend can detect it
                        if label and label not in new_text:
                            new_text = f"{new_text} — {label}"
                        claims[idx] = new_text
                    tg["key_claims"] = claims
                    story.telegram_analysis = tg
                    await db.commit()
                    return f"✓ ادعا {idx} به‌روز شد"
                return f"✗ شماره ادعا نامعتبر: {idx}"
            return "✗ تحلیل تلگرام یافت نشد"

        elif fix_type == "pipeline_change":
            return f"📝 پیشنهاد ثبت شد: {fix_data.get('pipeline_description', '?')[:100]}"

        else:
            return f"⏭ نوع اصلاح ناشناخته: {fix_type}"


def print_report(report: dict, applied_results: list[str] | None = None):
    """Pretty-print the audit report."""
    print("\n" + "=" * 60)
    print("📋 گزارش نیلوفر — سردبیر ارشد ژئوپلیتیک")
    print("=" * 60)
    print(f"\nارزیابی کلی: {report.get('overall_grade', '?')}")
    print(f"\n{report.get('summary', '')}")

    findings = report.get("findings", [])
    print(f"\n{'─' * 60}")
    print(f"تعداد یافته‌ها: {len(findings)}")
    print(f"{'─' * 60}")

    severity_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    type_labels = {
        "bad_title": "عنوان نادرست",
        "irrelevant_article": "مقاله نامرتبط",
        "merge_stories": "ادغام موضوعات",
        "bad_summary": "خلاصه ضعیف",
        "wrong_order": "ترتیب نادرست",
        "bad_image": "تصویر نامناسب",
        "pipeline_suggestion": "پیشنهاد سیستمی",
        "imbalance": "عدم توازن",
        "translation_mismatch": "عدم تطابق ترجمه",
        "stale_story": "موضوع کهنه",
        "source_silence": "سکوت منابع",
        "vocabulary_shift": "تغییر واژگان روایی",
        "other": "سایر",
    }

    for i, f in enumerate(findings):
        sev = severity_icons.get(f.get("severity", "low"), "⚪")
        ftype = type_labels.get(f.get("type", "other"), f.get("type", "?"))
        print(f"\n{sev} یافته {i+1}: {ftype}")
        print(f"   موضوع: {f.get('story_title', '?')[:60]}")
        print(f"   مشکل: {f.get('description_fa', '?')}")
        print(f"   پیشنهاد: {f.get('proposed_fix', '?')}")
        if applied_results and i < len(applied_results):
            print(f"   نتیجه: {applied_results[i]}")


async def main():
    parser = argparse.ArgumentParser(description="نیلوفر — ویراستار ارشد دورنگر")
    parser.add_argument("--apply", action="store_true", help="Apply all fixes automatically")
    args = parser.parse_args()

    stories = await fetch_stories()
    if not stories:
        print("هیچ موضوعی یافت نشد")
        return

    stories_block = build_stories_block(stories)
    report = await call_niloofar(stories_block)
    if not report:
        return

    applied = None
    if args.apply:
        print("\n🔧 در حال اعمال اصلاحات...")
        applied = []
        for f in report.get("findings", []):
            if f.get("fix_type") in ("rename_story", "update_summary", "remove_article", "merge_stories", "update_image"):
                result = await apply_fix(f)
                applied.append(result)
                print(f"  {result}")
            elif f.get("fix_type") == "pipeline_change":
                applied.append(f"📝 {f.get('fix_data', {}).get('pipeline_description', '?')[:80]}")
            else:
                applied.append("⏭ بدون اقدام")

    print_report(report, applied)

    # Save report
    output_path = os.path.join(os.path.dirname(__file__), "journalist_report.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    print(f"\n💾 گزارش ذخیره شد: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
