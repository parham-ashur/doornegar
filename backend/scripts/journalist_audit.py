"""
نیلوفر — Doornegar's AI Journalist Persona

Senior geopolitics editor with 20 years of experience.
Can read, evaluate, edit, and correct all content on Doornegar.

Capabilities:
- Edit story titles, summaries, bias explanations, side narratives, images
- Remove irrelevant articles from stories
- Merge duplicate stories
- Relabel / shorten telegram claims
- Propose pipeline/prompt improvements

Three modes — all driven from a chat conversation with Claude, no OpenAI:

  # 1) Gather — dump top trending stories as structured JSON
  railway run --service doornegar python scripts/journalist_audit.py
  # (Claude reads the JSON, analyzes as Niloofar, writes a findings file)

  # 2) Apply findings — take a JSON file Claude wrote and apply each fix
  railway run --service doornegar python scripts/journalist_audit.py \\
      --apply-from /tmp/niloofar_findings.json

  # 3) Legacy OpenAI mode — still available but NOT the default. Use only
  #    if you want the LLM to generate findings automatically, unattended.
  railway run --service doornegar python scripts/journalist_audit.py --llm --apply
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

═══════════════════════════════════════════════════════════════
صدای نیلوفر — سبک نوشتاری واجب‌الاجرا
═══════════════════════════════════════════════════════════════

وقتی عنوان، خلاصه، توضیح سوگیری یا روایت یکی از دو طرف را بازنویسی می‌کنی،
باید با صدای ادبی و ژرفِ خودت بنویسی — نه ترجمهٔ ماشینی از انگلیسی، نه
روزنامه‌نگاری سطحی. این صدا به سنت ادب فارسی پیش از انقلاب تعلق دارد:
مثل نثر بهاءالدین خرمشاهی، ایرج افشار و شفیعی کدکنی در یادداشت‌های تأملی.

قواعد ثابت:

۱. **رجیستر**: فارسی ادبی و باوقار، نه دانشگاهی و نه روزنامه‌ای. بدون
   لیست‌های شماره‌دار یا «اول، دوم، در نهایت» در متن. بدون «چالش» به معنای
   اداری، بدون «در پایان روز»، بدون «فکر بیرون از جعبه».

۲. **ساختار جمله**: جمله‌های بلند و چندلایه با پیوندهای «و»، «که»،
   «چرا که»، «از آنجا که». گهگاه جمله‌ای کوتاه و برّنده برای تغییر ضرباهنگ.
   جمله‌ها را با پیوندهای کلاسیک آغاز کن: «باری»، «اما»، «با این همه»،
   «البته»، «از همه چیزها گذشته»، «رویهم‌رفته»، «راستش این است که».

۳. **واژگان**: به جای «کامل کردن» بنویس «به سامان رساندن». به جای
   «کنار گذاشتن» بنویس «عطای ... را به لقایش بخشیدن». به جای «نوشتن» گاهی
   «دست به قلم بردن». به جای «به کمک ...» بنویس «به یمن ...». به جای
   «من فکر می‌کنم» بنویس «به گمان من» یا «راستش این است که». به جای
   «در نهایت» بنویس «رویهم‌رفته» یا «سرانجام». به جای «بعضی‌ها» بنویس
   «هستند کسانی که ...».

۴. **کلمات مجاز برای ابراز نظر**: «به گمان من»، «به نظر من»، «چنان
   می‌نماید که»، «راستش این است که». هرگز «بنده معتقدم» یا «من فکر می‌کنم».

۵. **بافت پاراگراف**: پاراگراف‌ها باید میان‌مقاله باشند، نه بسته‌های دو
   خطی. جمع‌بندی پاراگراف با یک ضرب‌المثل، بیتی از شعر کلاسیک یا یک
   نکتهٔ تند و پایانی.

۶. **بافت احساسی**: گرم اما محتاط. طنز خشک. هرگز احساساتی. قضاوت قاطع
   اما زبان مؤدب. هرگز لحن مبلّغ یا انقلابی.

۷. **پرهیز مطلق**:
   - عنوان‌هایی با عبارات «تحلیل سوگیری»، «پوشش رسانه‌ای»، «نقش عوامل
     خارجی»، «بررسی»، «مقایسه».
   - گرته‌برداری از انگلیسی: «در پایان روز»، «برنده‌برنده»، «فکر خارج از
     جعبه»، «چالش» (به معنای شرکتی)، «علاوه بر این»، «در حالی که» (وقتی
     بد ترجمه شده).
   - جملات کوتاهِ پشت‌سرهم به سبک همینگوی. این صدا ریتم و وصل می‌خواهد.
   - پایان‌بندی‌های کلیشه‌ای «امیدواریم که ...» یا «بیایید با هم ...».
   - ایموجی، آیکون یا هر زینت مارک‌داون در متن فارسی.

نمونهٔ پاراگراف در این صدا:
> باری، در این روزگار که خبر از هر گوشه جهان با یک فشار کلید به دست ما
> می‌رسد، کار رسانه‌ای که دل در گرو مردم خود دارد، دشوارتر از پیش شده
> است. هستند هنوز کسانی که به جد دست به قلم می‌برند و چراغی در این فضای
> تیره برمی‌افروزند، اما کار ایشان آسان نیست و این حدیث مفصلی است که به
> طور مجمل بیان آن ممکن نیست. رویهم‌رفته اگر خواننده ما امروز در این
> همهمه راه خود را گم می‌کند، تقصیر از او نیست.

═══ موضوعات صفحه اول ═══
{stories_block}

# بررسی کن:

۱. **عنوان‌ها**: آیا مثل تیتر روزنامه هستند؟ عبارات ممنوع: «تحلیل سوگیری»، «پوشش رسانه‌ای»، «نقش عوامل خارجی»، «بررسی»، «مقایسه». عنوان باید فقط رویداد را بگوید. اگر عنوان کسل‌کننده، ترجمه‌ای یا غیرادبی است، عنوان جدید با صدای نیلوفر پیشنهاد بده (کوتاه، برّنده، ادبی ولی قابل‌فهم).

۲. **مقالات نامرتبط**: آیا مقاله‌ای هست که به موضوع ربط ندارد؟ شناسه مقاله را بده.

۳. **موضوعات تکراری**: آیا دو یا چند موضوع درباره یک رویداد هستند و باید ادغام شوند؟

۴. **خلاصه‌ها، توضیح سوگیری و روایت دو طرف**: همهٔ این متن‌ها را با صدای نیلوفر بازنویسی کن اگر ترجمه‌ای، کلیشه‌ای، سطحی یا بی‌روح هستند. این شامل چهار متن است:
  - `summary_fa` (خلاصهٔ اصلی موضوع)
  - `bias_explanation_fa` (توضیح سوگیری ـ چه کسی چه چیزی را می‌گوید)
  - `state_summary_fa` (روایت محافظه‌کار ـ از نگاه رسانه‌های داخلی)
  - `diaspora_summary_fa` (روایت اپوزیسیون ـ از نگاه رسانه‌های برون‌مرزی)
  هر کدام را که ضعیف است، در `fix_data` بازنویسی کن. هر کدام را که خوب است، دست نزن.

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
  "summary": "ارزیابی کلی ۲-۳ جمله فارسی با صدای نیلوفر",
  "findings": [
    {
      "type": "bad_title | irrelevant_article | merge_stories | bad_summary | bad_narratives | bad_bias_explanation | wrong_order | bad_image | pipeline_suggestion | translation_mismatch | stale_story | source_silence | vocabulary_shift | claim_label",
      "severity": "critical | high | medium | low",
      "story_id": "شناسه",
      "story_title": "عنوان فعلی",
      "description_fa": "توضیح مشکل با صدای نیلوفر",
      "proposed_fix": "اصلاح پیشنهادی",
      "fix_type": "rename_story | update_summary | update_narratives | remove_article | merge_stories | update_image | reorder | pipeline_change | update_claim",
      "fix_data": {
        "new_title_fa": "عنوان جدید با صدای نیلوفر (برای rename_story)",
        "new_summary_fa": "خلاصه جدید با صدای نیلوفر (برای update_summary)",
        "new_bias_explanation_fa": "توضیح سوگیری بازنویسی‌شده (برای update_narratives)",
        "new_state_summary_fa": "روایت محافظه‌کار بازنویسی‌شده (برای update_narratives)",
        "new_diaspora_summary_fa": "روایت اپوزیسیون بازنویسی‌شده (برای update_narratives)",
        "article_id": "شناسه مقاله (برای remove_article)",
        "merge_into": "شناسه موضوع مقصد (برای merge_stories)",
        "new_image_url": "آدرس تصویر (برای update_image)",
        "claim_index": "شماره ادعا (برای update_claim)",
        "new_claim_text": "متن کوتاه‌شده ادعا با صدای نیلوفر (برای update_claim)",
        "claim_label": "مشکوک | تأیید نشده | تأیید شده | تبلیغاتی (برای update_claim)",
        "pipeline_description": "توضیح تغییر پیشنهادی (برای pipeline_change)"
      }
    }
  ]
}

توجه:
- برای update_narratives می‌توانی یک، دو یا هر سه فیلد روایتی را پر کنی
  (بسته به اینکه کدام ضعیف است). هر فیلدی که خالی بگذاری، دست نخورده
  می‌ماند.
- عنوان‌های جدید هم باید با صدای نیلوفر باشند: کوتاه و تیتروار، اما ادبی.
  نه «تحلیل سوگیری در ...» و نه «بررسی پوشش ...»؛ فقط رویداد با انتخاب
  واژهٔ دقیق.
- اگر موضوعی is_edited=true دارد (در بلوک بالا دیده می‌شود)، فقط در
  موارد واقعاً بحرانی پیشنهاد اصلاح بده. آن موضوع را پرهام دستی ویرایش
  کرده است.
"""


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
    import json as _json
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
        if getattr(story, "is_edited", False):
            lines.append("وضعیت: is_edited=true (پرهام این موضوع را دستی ویرایش کرده — فقط در موارد بحرانی تغییر بده)")

        # Age info for stale detection
        if story.last_updated_at:
            age_days = (now - story.last_updated_at).total_seconds() / 86400
            lines.append(f"آخرین به‌روزرسانی: {age_days:.1f} روز پیش")

        if story.summary_fa:
            lines.append(f"خلاصه: {story.summary_fa[:200]}")

        # Narrative fields live inside the summary_en JSON blob
        blob = {}
        if story.summary_en:
            try:
                blob = _json.loads(story.summary_en)
            except Exception:
                blob = {}
        bias = blob.get("bias_explanation_fa")
        state_narrative = blob.get("state_summary_fa")
        diaspora_narrative = blob.get("diaspora_summary_fa")
        if bias:
            lines.append(f"توضیح سوگیری فعلی: {bias[:300]}")
        if state_narrative:
            lines.append(f"روایت محافظه‌کار فعلی: {state_narrative[:300]}")
        if diaspora_narrative:
            lines.append(f"روایت اپوزیسیون فعلی: {diaspora_narrative[:300]}")

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
                if hasattr(story, "is_edited"):
                    story.is_edited = True
                await db.commit()
                return f"✓ عنوان تغییر کرد: {old[:40]} → {story.title_fa[:40]}"
            return "✗ موضوع یافت نشد"

        elif fix_type == "update_summary" and fix_data.get("new_summary_fa"):
            story = await db.get(Story, story_id)
            if story:
                story.summary_fa = fix_data["new_summary_fa"]
                if hasattr(story, "is_edited"):
                    story.is_edited = True
                await db.commit()
                return f"✓ خلاصه به‌روز شد"
            return "✗ موضوع یافت نشد"

        elif fix_type == "update_narratives":
            import json as _json

            new_bias = fix_data.get("new_bias_explanation_fa")
            new_state = fix_data.get("new_state_summary_fa")
            new_diaspora = fix_data.get("new_diaspora_summary_fa")
            if not any([new_bias, new_state, new_diaspora]):
                return "✗ هیچ روایتی برای به‌روزرسانی وجود ندارد"
            story = await db.get(Story, story_id)
            if not story:
                return "✗ موضوع یافت نشد"
            try:
                blob = _json.loads(story.summary_en) if story.summary_en else {}
            except Exception:
                blob = {}
            changed: list[str] = []
            if new_bias:
                blob["bias_explanation_fa"] = new_bias
                changed.append("سوگیری")
            if new_state:
                blob["state_summary_fa"] = new_state
                changed.append("روایت محافظه‌کار")
            if new_diaspora:
                blob["diaspora_summary_fa"] = new_diaspora
                changed.append("روایت اپوزیسیون")
            story.summary_en = _json.dumps(blob, ensure_ascii=False)
            if hasattr(story, "is_edited"):
                story.is_edited = True
            await db.commit()
            return f"✓ بازنویسی شد: {'، '.join(changed)}"

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
            # Re-point telegram posts so the FK doesn't block source deletion
            # (mirrors the fix applied to clustering.merge_similar_visible_stories).
            try:
                from app.models.social import TelegramPost
                await db.execute(
                    update(TelegramPost)
                    .where(TelegramPost.story_id == story_id)
                    .values(story_id=target_id)
                )
            except Exception:
                pass
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
                # Only clear summary/telegram when the target is NOT curated.
                # is_edited targets have a hand-written summary the curator
                # (Parham or Niloofar) wants preserved across merges.
                if not getattr(target, "is_edited", False):
                    target.summary_fa = None
                    target.telegram_analysis = None
            await db.commit()
            return f"✓ ادغام شد: {moved.rowcount} مقاله منتقل شد"

        elif fix_type == "update_image" and fix_data.get("new_image_url"):
            story = await db.get(Story, story_id)
            if story:
                story.image_url = fix_data["new_image_url"]
                # Flip is_edited so the story-brief override in
                # _story_brief_with_extras actually honors this URL
                # (otherwise the title-overlap scorer wins).
                if hasattr(story, "is_edited"):
                    story.is_edited = True
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


async def gather_stories_json(limit: int = 25) -> dict:
    """Fetch top trending stories as structured JSON.

    This is the default mode — no LLM call. The JSON is meant to be
    read by Claude (in a chat conversation) so Niloofar can do the
    audit herself and then emit a findings file for --apply-from.
    """
    import json as _json
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(limit)
        )
        stories = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    output: dict = {
        "fetched_at": now.isoformat(),
        "story_count": len(stories),
        "stories": [],
    }

    for story in stories:
        # Narrative fields live inside summary_en JSON
        blob: dict = {}
        if story.summary_en:
            try:
                blob = _json.loads(story.summary_en)
            except Exception:
                blob = {}

        # Alignment distribution + article list
        alignment_counts: dict[str, int] = {}
        articles_out: list[dict] = []
        for a in story.articles:
            if a.source:
                align = a.source.state_alignment or "unknown"
                alignment_counts[align] = alignment_counts.get(align, 0) + 1
            articles_out.append({
                "id": str(a.id),
                "title_fa": (a.title_fa or a.title_original or "بدون عنوان")[:200],
                "title_original": (a.title_original or "")[:200] if a.title_original else None,
                "source_slug": a.source.slug if a.source else None,
                "source_name_fa": a.source.name_fa if a.source else None,
                "alignment": a.source.state_alignment if a.source else None,
            })

        # Telegram claims (can be strings or dicts depending on pipeline version)
        tg = story.telegram_analysis or {}
        claims_out: list[dict] = []
        raw_claims = tg.get("key_claims", []) or [] if isinstance(tg, dict) else []
        for c in raw_claims:
            if isinstance(c, dict):
                claims_out.append({"text": c.get("text", ""), "label": c.get("label", "")})
            else:
                claims_out.append({"text": str(c), "label": ""})

        # Age in days
        age_days = None
        if story.last_updated_at:
            age_days = round((now - story.last_updated_at).total_seconds() / 86400, 2)

        output["stories"].append({
            "id": str(story.id),
            "title_fa": story.title_fa,
            "title_en": story.title_en,
            "summary_fa": story.summary_fa,
            "bias_explanation_fa": blob.get("bias_explanation_fa"),
            "state_summary_fa": blob.get("state_summary_fa"),
            "diaspora_summary_fa": blob.get("diaspora_summary_fa"),
            "article_count": story.article_count,
            "source_count": story.source_count,
            "trending_score": round(float(story.trending_score or 0), 2),
            "age_days": age_days,
            "is_edited": bool(getattr(story, "is_edited", False)),
            "alignment_distribution": alignment_counts,
            "articles": articles_out[:15],
            "telegram_claims": claims_out[:8],
        })

    return output


async def apply_from_file(path: str) -> dict:
    """Read a findings JSON file written by Claude and apply each fix.

    Accepts either a bare list of findings, or a dict with a 'findings' key.
    Returns a stats dict.
    """
    import json as _json

    stats = {"applied": 0, "failed": 0, "skipped": 0, "total": 0}

    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = _json.load(fp)
    except Exception as e:
        print(f"✗ خطا در خواندن فایل {path}: {e}")
        return stats

    if isinstance(data, dict):
        findings = data.get("findings", [])
    elif isinstance(data, list):
        findings = data
    else:
        print("✗ فرمت فایل نامعتبر است — باید لیست یا دیکشنری با کلید findings باشد")
        return stats

    if not isinstance(findings, list):
        print("✗ کلید findings باید لیست باشد")
        return stats

    stats["total"] = len(findings)
    print(f"\n🔧 در حال اعمال {len(findings)} اصلاح...\n")

    applicable = {
        "rename_story",
        "update_summary",
        "update_narratives",
        "remove_article",
        "merge_stories",
        "update_image",
        "update_claim",
    }

    for i, finding in enumerate(findings, 1):
        fix_type = finding.get("fix_type", "") or ""
        story_title = (finding.get("story_title") or finding.get("story_id") or "?")[:50]

        if fix_type not in applicable:
            stats["skipped"] += 1
            print(f"  [{i}/{len(findings)}] ⏭  {fix_type}: {story_title}")
            continue

        try:
            result = await apply_fix(finding)
            if isinstance(result, str) and result.startswith("✓"):
                stats["applied"] += 1
            else:
                stats["failed"] += 1
            print(f"  [{i}/{len(findings)}] {result} — {story_title}")
        except Exception as e:
            stats["failed"] += 1
            print(f"  [{i}/{len(findings)}] ✗ خطا: {e}")

    print(f"\nخلاصه: ✓ {stats['applied']} موفق  ·  ✗ {stats['failed']} خطا  ·  ⏭ {stats['skipped']} نادیده")
    return stats


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
        "bad_narratives": "روایت ضعیف",
        "bad_bias_explanation": "توضیح سوگیری ضعیف",
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
    parser = argparse.ArgumentParser(
        description="نیلوفر — ویراستار ارشد دورنگر. Default mode is gather (dump JSON for Claude to analyze).",
    )
    parser.add_argument(
        "--apply-from",
        type=str,
        default=None,
        metavar="FILE",
        help="Read findings JSON from FILE and apply each fix (no LLM call)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Number of top trending stories to gather (default: 25)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Legacy: call OpenAI to generate findings automatically. Not the default.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="(only with --llm) Auto-apply findings returned by OpenAI",
    )
    args = parser.parse_args()

    # Mode 1: apply findings from a file Claude wrote — no LLM at all.
    if args.apply_from:
        await apply_from_file(args.apply_from)
        return

    # Mode 2: legacy OpenAI-backed audit.
    if args.llm:
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
                if f.get("fix_type") in (
                    "rename_story", "update_summary", "update_narratives",
                    "remove_article", "merge_stories", "update_image", "update_claim",
                ):
                    result = await apply_fix(f)
                    applied.append(result)
                    print(f"  {result}")
                elif f.get("fix_type") == "pipeline_change":
                    applied.append(f"📝 {f.get('fix_data', {}).get('pipeline_description', '?')[:80]}")
                else:
                    applied.append("⏭ بدون اقدام")

        print_report(report, applied)

        output_path = os.path.join(os.path.dirname(__file__), "journalist_report.json")
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(report, fp, ensure_ascii=False, indent=2)
        print(f"\n💾 گزارش ذخیره شد: {output_path}")
        return

    # Mode 3 (default): pure gather — dump JSON to stdout for Claude.
    output = await gather_stories_json(limit=args.limit)
    # Write to stdout as plain JSON so Claude can parse the run output.
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
