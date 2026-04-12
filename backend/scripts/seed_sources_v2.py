"""Seed script v2: adds new media sources and analysts to the database.

Usage:
    cd doornegar/backend
    python scripts/seed_sources_v2.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.analyst import Analyst
from app.models.source import Source

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# New media sources
# ---------------------------------------------------------------------------

NEW_SOURCES = [
    # IRGC-affiliated
    {
        "name_en": "Mehr News Agency",
        "name_fa": "خبرگزاری مهر",
        "slug": "mehr-news",
        "website_url": "https://www.mehrnews.com",
        "rss_urls": ["https://www.mehrnews.com/rss"],
        "state_alignment": "state",
        "irgc_affiliated": True,
        "production_location": "inside_iran",
        "factional_alignment": "hardline",
        "language": "both",
        "description_en": "IRGC-affiliated news agency. Founded 2003. Publishes in multiple languages.",
        "description_fa": "خبرگزاری وابسته به سپاه پاسداران. تأسیس ۱۳۸۲. انتشار به چند زبان.",
    },
    {
        "name_en": "Mashregh News",
        "name_fa": "مشرق‌نیوز",
        "slug": "mashregh-news",
        "website_url": "https://www.mashreghnews.ir",
        "rss_urls": ["https://www.mashreghnews.ir/rss"],
        "state_alignment": "state",
        "irgc_affiliated": True,
        "production_location": "inside_iran",
        "factional_alignment": "hardline",
        "language": "fa",
        "description_en": "IRGC-affiliated hardline news outlet. Focus on military and security affairs.",
        "description_fa": "رسانه خبری اصولگرای وابسته به سپاه. تمرکز بر امور نظامی و امنیتی.",
    },
    {
        "name_en": "Nour News",
        "name_fa": "نورنیوز",
        "slug": "nour-news",
        "website_url": "https://www.nournews.ir",
        "rss_urls": ["https://www.nournews.ir/fa/rss"],
        "state_alignment": "state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "hardline",
        "language": "fa",
        "description_en": "Hardline state-aligned news outlet. Close to Supreme National Security Council.",
        "description_fa": "رسانه خبری اصولگرا. نزدیک به شورای عالی امنیت ملی.",
    },
    # State / semi-state
    {
        "name_en": "IRNA",
        "name_fa": "ایرنا",
        "slug": "irna",
        "website_url": "https://www.irna.ir",
        "rss_urls": ["https://www.irna.ir/rss"],
        "state_alignment": "state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "principlist",
        "language": "both",
        "description_en": "Islamic Republic News Agency. Official state news agency of Iran.",
        "description_fa": "خبرگزاری جمهوری اسلامی ایران. خبرگزاری رسمی دولت.",
    },
    {
        "name_en": "IRIB News",
        "name_fa": "خبرگزاری صدا و سیما",
        "slug": "irib-news",
        "website_url": "https://www.iribnews.ir",
        "rss_urls": ["https://www.iribnews.ir/fa/rss"],
        "state_alignment": "state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "principlist",
        "language": "fa",
        "description_en": "Islamic Republic of Iran Broadcasting news division. State TV/radio.",
        "description_fa": "بخش خبری صدا و سیمای جمهوری اسلامی ایران.",
    },
    {
        "name_en": "ILNA",
        "name_fa": "ایلنا",
        "slug": "ilna",
        "website_url": "https://www.ilna.ir",
        "rss_urls": ["https://www.ilna.ir/fa/rss"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "reformist",
        "language": "fa",
        "description_en": "Iranian Labour News Agency. Semi-state, reformist-leaning. Covers labour and social issues.",
        "description_fa": "خبرگزاری کار ایران. نیمه‌دولتی، گرایش اصلاح‌طلبانه. پوشش مسائل کارگری و اجتماعی.",
    },
    {
        "name_en": "Shargh Daily",
        "name_fa": "روزنامه شرق",
        "slug": "shargh",
        "website_url": "https://www.sharghdaily.com",
        "rss_urls": ["https://www.sharghdaily.com/fa/rss"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "reformist",
        "language": "fa",
        "description_en": "Leading reformist daily newspaper. Repeatedly suspended and reopened.",
        "description_fa": "روزنامه پیشرو اصلاح‌طلب. بارها توقیف و بازگشایی شده.",
    },
    {
        "name_en": "Etemad Online",
        "name_fa": "اعتماد آنلاین",
        "slug": "etemad",
        "website_url": "https://www.etemadnewspaper.ir",
        "rss_urls": ["https://www.etemadnewspaper.ir/fa/rss"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "reformist",
        "language": "fa",
        "description_en": "Reformist daily newspaper. One of the most prominent reform-aligned outlets in Iran.",
        "description_fa": "روزنامه اصلاح‌طلب. یکی از برجسته‌ترین رسانه‌های اصلاح‌طلب در ایران.",
    },
    {
        "name_en": "Entekhab",
        "name_fa": "انتخاب",
        "slug": "entekhab",
        "website_url": "https://www.entekhab.ir",
        "rss_urls": ["https://www.entekhab.ir/fa/rss"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "moderate",
        "language": "fa",
        "description_en": "Moderate semi-state news aggregator. Wide coverage of domestic politics.",
        "description_fa": "خبرگزاری نیمه‌دولتی میانه‌رو. پوشش گسترده سیاست داخلی.",
    },
    # Diaspora
    {
        "name_en": "Manoto",
        "name_fa": "منوتو",
        "slug": "manoto",
        "website_url": "https://www.manototv.com",
        "rss_urls": [],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": "opposition",
        "language": "fa",
        "description_en": "London-based Persian TV network. Popular entertainment and news channel among diaspora.",
        "description_fa": "شبکه تلویزیونی فارسی‌زبان مستقر در لندن. محبوب در میان ایرانیان خارج از کشور.",
    },
]

# Sources to update if they already exist (slug -> updates)
SOURCE_UPDATES = {
    "iranwire": {
        "state_alignment": "diaspora",
        "factional_alignment": "opposition",
    },
    "voa-farsi": {
        "state_alignment": "diaspora",
        "factional_alignment": "opposition",
    },
}

# ---------------------------------------------------------------------------
# Analysts
# ---------------------------------------------------------------------------

ANALYSTS = [
    {
        "name_en": "Abbas Abdi",
        "name_fa": "عباس عبدی",
        "slug": "abbas-abdi",
        "telegram_handle": None,
        "twitter_handle": None,
        "political_leaning": "reformist",
        "location": "inside_iran",
        "affiliation": "Journalist, former political prisoner",
        "focus_areas": ["domestic_politics", "reform_movement"],
        "bio_en": "Prominent reformist journalist and political analyst. Former student activist, served prison time. Known for sharp political commentary from inside Iran.",
        "bio_fa": "روزنامه‌نگار و تحلیلگر سیاسی اصلاح‌طلب. فعال دانشجویی سابق و زندانی سیاسی سابق.",
    },
    {
        "name_en": "Sadegh Zibakalam",
        "name_fa": "صادق زیباکلام",
        "slug": "sadegh-zibakalam",
        "telegram_handle": "@zibakalam_sadegh",
        "twitter_handle": None,
        "political_leaning": "reformist",
        "location": "inside_iran",
        "affiliation": "Tehran University",
        "focus_areas": ["domestic_politics", "foreign_policy", "history"],
        "bio_en": "Tehran University political science professor. Outspoken reformist. Frequently summoned by authorities for public statements.",
        "bio_fa": "استاد علوم سیاسی دانشگاه تهران. اصلاح‌طلب صریح‌اللهجه. بارها به‌خاطر اظهارنظرها احضار شده.",
    },
    {
        "name_en": "Ahmad Zeidabadi",
        "name_fa": "احمد زیدآبادی",
        "slug": "ahmad-zeidabadi",
        "telegram_handle": "@ahmadzeidabadi",
        "twitter_handle": None,
        "political_leaning": "reformist",
        "location": "inside_iran",
        "affiliation": "Independent journalist",
        "focus_areas": ["domestic_politics", "civil_society", "press_freedom"],
        "bio_en": "Award-winning journalist and political commentator. Imprisoned after 2009 Green Movement. Continues writing under restrictions.",
        "bio_fa": "روزنامه‌نگار و مفسر سیاسی برنده جایزه. پس از جنبش سبز ۸۸ زندانی شد. همچنان با محدودیت می‌نویسد.",
    },
    {
        "name_en": "Hossein Bastani",
        "name_fa": "حسین بستانی",
        "slug": "hossein-bastani",
        "telegram_handle": None,
        "twitter_handle": "@h_bastani",
        "political_leaning": "independent",
        "location": "outside_iran",
        "affiliation": "BBC Persian",
        "focus_areas": ["irgc", "military", "power_structure"],
        "bio_en": "BBC Persian journalist specializing in IRGC and Iran's military-security apparatus. Deep source network inside Iran.",
        "bio_fa": "روزنامه‌نگار بی‌بی‌سی فارسی متخصص در سپاه و ساختار نظامی-امنیتی ایران.",
    },
    {
        "name_en": "Maziar Bahari",
        "name_fa": "مازیار بهاری",
        "slug": "maziar-bahari",
        "telegram_handle": None,
        "twitter_handle": "@mazaborz",
        "political_leaning": "independent",
        "location": "outside_iran",
        "affiliation": "IranWire",
        "focus_areas": ["human_rights", "press_freedom", "citizen_journalism"],
        "bio_en": "Filmmaker, journalist, founder of IranWire. Imprisoned in 2009 (depicted in 'Rosewater'). Advocates for press freedom.",
        "bio_fa": "فیلمساز، روزنامه‌نگار، بنیانگذار ایران‌وایر. در سال ۸۸ زندانی شد. مدافع آزادی مطبوعات.",
    },
    {
        "name_en": "Hamed Esmaeilion",
        "name_fa": "حامد اسماعیلیون",
        "slug": "hamed-esmaeilion",
        "telegram_handle": "@esaborz",
        "twitter_handle": "@esaborz",
        "political_leaning": "opposition",
        "location": "outside_iran",
        "affiliation": "Association of Families of PS752 Victims",
        "focus_areas": ["human_rights", "accountability", "diaspora_activism"],
        "bio_en": "Writer and activist. Lost wife and daughter in PS752 shootdown. Became prominent voice of diaspora opposition movement.",
        "bio_fa": "نویسنده و فعال مدنی. همسر و دختر خود را در سقوط پرواز ۷۵۲ از دست داد. صدای برجسته جنبش اپوزیسیون.",
    },
    {
        "name_en": "Mariam Memarsadeghi",
        "name_fa": "مریم معمارصادقی",
        "slug": "mariam-memarsadeghi",
        "telegram_handle": None,
        "twitter_handle": "@memarsadeghi",
        "political_leaning": "opposition",
        "location": "outside_iran",
        "affiliation": "Tavaana",
        "focus_areas": ["civil_society", "democracy", "education"],
        "bio_en": "Co-founder of Tavaana civic education platform. Advocates for democratic transition in Iran.",
        "bio_fa": "هم‌بنیانگذار پلتفرم آموزش مدنی توانا. مدافع گذار دموکراتیک در ایران.",
    },
    {
        "name_en": "Amirabbas Fakhravar",
        "name_fa": "امیرعباس فخرآور",
        "slug": "amirabbas-fakhravar",
        "telegram_handle": None,
        "twitter_handle": "@afakhravar",
        "political_leaning": "opposition",
        "location": "outside_iran",
        "affiliation": None,
        "focus_areas": ["regime_change", "geopolitics", "us_iran_relations"],
        "bio_en": "Dissident and political activist. Former political prisoner. Advocates for regime change from Washington DC.",
        "bio_fa": "مخالف و فعال سیاسی. زندانی سیاسی سابق. مدافع تغییر رژیم از واشنگتن.",
    },
    {
        "name_en": "Trita Parsi",
        "name_fa": "تریتا پارسی",
        "slug": "trita-parsi",
        "telegram_handle": None,
        "twitter_handle": "@taborz",
        "political_leaning": "academic",
        "location": "outside_iran",
        "affiliation": "Quincy Institute",
        "focus_areas": ["us_iran_relations", "foreign_policy", "diplomacy", "sanctions"],
        "bio_en": "Political scientist and author. Executive VP of Quincy Institute. Expert on US-Iran relations and diplomacy.",
        "bio_fa": "دانشمند سیاسی و نویسنده. معاون اجرایی مؤسسه کوینسی. متخصص روابط ایران و آمریکا.",
    },
    {
        "name_en": "Negar Mortazavi",
        "name_fa": "نگار مرتضوی",
        "slug": "negar-mortazavi",
        "telegram_handle": None,
        "twitter_handle": "@negaborz",
        "political_leaning": "independent",
        "location": "outside_iran",
        "affiliation": "Independent journalist",
        "focus_areas": ["us_iran_relations", "sanctions", "media_analysis"],
        "bio_en": "Iranian-American journalist and podcast host. Covers Iran-US relations and sanctions. Known for balanced analysis.",
        "bio_fa": "روزنامه‌نگار ایرانی-آمریکایی و مجری پادکست. پوشش روابط ایران و آمریکا و تحریم‌ها.",
    },
    {
        "name_en": "Roya Hakakian",
        "name_fa": "رویا حکاکیان",
        "slug": "roya-hakakian",
        "telegram_handle": None,
        "twitter_handle": "@royaborz",
        "political_leaning": "independent",
        "location": "outside_iran",
        "affiliation": "Author",
        "focus_areas": ["human_rights", "culture", "diaspora_identity", "history"],
        "bio_en": "Iranian-American author and poet. Writes about Iran's modern history, Jewish-Iranian identity, and human rights.",
        "bio_fa": "نویسنده و شاعر ایرانی-آمریکایی. درباره تاریخ معاصر ایران، هویت یهودی-ایرانی و حقوق بشر می‌نویسد.",
    },
    {
        "name_en": "Ali Vaez",
        "name_fa": "علی واعظ",
        "slug": "ali-vaez",
        "telegram_handle": None,
        "twitter_handle": "@aliaborz",
        "political_leaning": "academic",
        "location": "outside_iran",
        "affiliation": "International Crisis Group",
        "focus_areas": ["nuclear_program", "foreign_policy", "diplomacy", "geopolitics"],
        "bio_en": "Iran Project Director at International Crisis Group. Leading expert on Iran's nuclear program and regional policy.",
        "bio_fa": "مدیر پروژه ایران در گروه بین‌المللی بحران. کارشناس برنامه هسته‌ای و سیاست منطقه‌ای ایران.",
    },
    {
        "name_en": "Kasra Aarabi",
        "name_fa": "کسری اعرابی",
        "slug": "kasra-aarabi",
        "telegram_handle": None,
        "twitter_handle": "@kasra_aarabi",
        "political_leaning": "academic",
        "location": "outside_iran",
        "affiliation": "United Against Nuclear Iran (UANI)",
        "focus_areas": ["irgc", "ideology", "regional_influence", "terrorism"],
        "bio_en": "Iran analyst at UANI. Specialist in IRGC ideology and Iran's regional proxy networks.",
        "bio_fa": "تحلیلگر ایران در UANI. متخصص ایدئولوژی سپاه و شبکه‌های نیابتی منطقه‌ای ایران.",
    },
    {
        "name_en": "Sanam Vakil",
        "name_fa": "صنم وکیل",
        "slug": "sanam-vakil",
        "telegram_handle": None,
        "twitter_handle": "@sanaborz",
        "political_leaning": "academic",
        "location": "outside_iran",
        "affiliation": "Chatham House",
        "focus_areas": ["foreign_policy", "geopolitics", "gulf_relations", "gender"],
        "bio_en": "Director of Middle East and North Africa programme at Chatham House. Expert on Iran's foreign policy.",
        "bio_fa": "مدیر برنامه خاورمیانه و شمال آفریقا در چتم هاوس. کارشناس سیاست خارجی ایران.",
    },
    {
        "name_en": "Hossein Ronaghi",
        "name_fa": "حسین رونقی",
        "slug": "hossein-ronaghi",
        "telegram_handle": "@hosseinronaghi",
        "twitter_handle": "@haborz",
        "political_leaning": "opposition",
        "location": "inside_iran",
        "affiliation": None,
        "focus_areas": ["digital_rights", "internet_freedom", "human_rights"],
        "bio_en": "Digital rights activist. Repeatedly imprisoned. Advocate for internet freedom in Iran. Currently detained.",
        "bio_fa": "فعال حقوق دیجیتال. بارها زندانی شده. مدافع آزادی اینترنت در ایران. در حال حاضر بازداشت.",
        "is_imprisoned": True,
    },
    {
        "name_en": "Narges Mohammadi",
        "name_fa": "نرگس محمدی",
        "slug": "narges-mohammadi",
        "telegram_handle": None,
        "twitter_handle": None,
        "political_leaning": "opposition",
        "location": "inside_iran",
        "affiliation": "Defenders of Human Rights Center",
        "focus_areas": ["human_rights", "women_rights", "prison_conditions"],
        "bio_en": "Nobel Peace Prize laureate (2023). Human rights activist. Currently imprisoned in Evin Prison.",
        "bio_fa": "برنده جایزه صلح نوبل (۲۰۲۳). فعال حقوق بشر. در حال حاضر در زندان اوین.",
        "is_imprisoned": True,
    },
]

# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------


async def seed_new_sources(db: AsyncSession) -> dict:
    """Add new sources and apply updates to existing ones."""
    added = 0
    skipped = 0
    updated = 0

    for source_data in NEW_SOURCES:
        result = await db.execute(
            select(Source).where(Source.slug == source_data["slug"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            source = Source(**source_data)
            db.add(source)
            added += 1
            logger.info(f"  + Added source: {source_data['slug']}")
        else:
            skipped += 1
            logger.info(f"  ~ Skipped source (exists): {source_data['slug']}")

    # Apply updates to existing sources
    for slug, updates in SOURCE_UPDATES.items():
        result = await db.execute(select(Source).where(Source.slug == slug))
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in updates.items():
                setattr(existing, key, value)
            updated += 1
            logger.info(f"  * Updated source: {slug} -> {updates}")
        else:
            logger.info(f"  ? Source not found for update: {slug}")

    await db.commit()
    return {"added": added, "skipped": skipped, "updated": updated}


async def seed_analysts(db: AsyncSession) -> dict:
    """Seed analysts into the database."""
    added = 0
    skipped = 0

    for analyst_data in ANALYSTS:
        result = await db.execute(
            select(Analyst).where(Analyst.slug == analyst_data["slug"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            analyst = Analyst(**analyst_data)
            db.add(analyst)
            added += 1
            logger.info(f"  + Added analyst: {analyst_data['slug']}")
        else:
            skipped += 1
            logger.info(f"  ~ Skipped analyst (exists): {analyst_data['slug']}")

    await db.commit()
    return {"added": added, "skipped": skipped}


async def main():
    logger.info("=== Doornegar Seed v2 ===\n")

    async with async_session() as db:
        logger.info("--- Seeding new sources ---")
        source_stats = await seed_new_sources(db)
        logger.info(
            f"\nSources: {source_stats['added']} added, "
            f"{source_stats['skipped']} skipped, "
            f"{source_stats['updated']} updated\n"
        )

        logger.info("--- Seeding analysts ---")
        analyst_stats = await seed_analysts(db)
        logger.info(
            f"\nAnalysts: {analyst_stats['added']} added, "
            f"{analyst_stats['skipped']} skipped\n"
        )

    logger.info("=== Seed v2 complete ===")


if __name__ == "__main__":
    asyncio.run(main())
