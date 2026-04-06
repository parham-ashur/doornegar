"""Seed the database with initial news sources."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source

logger = logging.getLogger(__name__)

INITIAL_SOURCES = [
    {
        "name_en": "BBC Persian",
        "name_fa": "بی‌بی‌سی فارسی",
        "slug": "bbc-persian",
        "website_url": "https://www.bbc.com/persian",
        "rss_urls": ["https://feeds.bbci.co.uk/persian/rss.xml"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "BBC's Persian-language news service. Independent, UK-based public broadcaster.",
        "description_fa": "سرویس خبری فارسی بی‌بی‌سی. رسانه عمومی مستقل مستقر در بریتانیا.",
    },
    {
        "name_en": "Iran International",
        "name_fa": "ایران اینترنشنال",
        "slug": "iran-international",
        "website_url": "https://www.iranintl.com",
        "rss_urls": ["https://www.iranintl.com/fa/feed"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": "opposition",
        "language": "both",
        "description_en": "London-based Persian-language news channel. Critical of the Islamic Republic.",
        "description_fa": "شبکه خبری فارسی‌زبان مستقر در لندن. منتقد جمهوری اسلامی.",
    },
    {
        "name_en": "IranWire",
        "name_fa": "ایران‌وایر",
        "slug": "iranwire",
        "website_url": "https://iranwire.com",
        "rss_urls": ["https://iranwire.com/fa/feed/"],
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "both",
        "description_en": "Independent news platform combining diaspora journalists and citizen reporters inside Iran.",
        "description_fa": "پلتفرم خبری مستقل با همکاری روزنامه‌نگاران مهاجر و خبرنگاران شهروندی داخل ایران.",
    },
    {
        "name_en": "Radio Zamaneh",
        "name_fa": "رادیو زمانه",
        "slug": "radio-zamaneh",
        "website_url": "https://www.radiozamaneh.com",
        "rss_urls": ["https://www.radiozamaneh.com/feed/"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "Amsterdam-based Persian media platform. Reform-leaning, focuses on culture and civil society.",
        "description_fa": "رسانه فارسی‌زبان مستقر در آمستردام. گرایش اصلاح‌طلبانه، تمرکز بر فرهنگ و جامعه مدنی.",
    },
    {
        "name_en": "Deutsche Welle Persian",
        "name_fa": "دویچه‌وله فارسی",
        "slug": "dw-persian",
        "website_url": "https://www.dw.com/fa-ir",
        "rss_urls": ["https://rss.dw.com/xml/rss-fa-all"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "German public broadcaster's Persian service. Independent international media.",
        "description_fa": "سرویس فارسی رادیو و تلویزیون دولتی آلمان. رسانه بین‌المللی مستقل.",
    },
    {
        "name_en": "Tasnim News Agency",
        "name_fa": "خبرگزاری تسنیم",
        "slug": "tasnim",
        "website_url": "https://www.tasnimnews.com",
        "rss_urls": ["https://www.tasnimnews.com/fa/rss/most-visited/"],
        "state_alignment": "state",
        "irgc_affiliated": True,
        "production_location": "inside_iran",
        "factional_alignment": "hardline",
        "language": "both",
        "description_en": "IRGC-affiliated news agency. Founded 2012. EU-sanctioned for disinformation (2023).",
        "description_fa": "خبرگزاری وابسته به سپاه پاسداران. تأسیس ۱۳۹۱. تحریم شده توسط اتحادیه اروپا.",
    },
    {
        "name_en": "Press TV",
        "name_fa": "پرس تی‌وی",
        "slug": "press-tv",
        "website_url": "https://www.presstv.ir",
        "rss_urls": ["https://www.presstv.ir/RSS"],
        "state_alignment": "state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "hardline",
        "language": "en",
        "description_en": "State-funded English-language news channel. International propaganda arm of IRIB.",
        "description_fa": "شبکه خبری انگلیسی‌زبان دولتی. بازوی تبلیغاتی بین‌المللی صدا و سیما.",
    },
    {
        "name_en": "Mehr News Agency",
        "name_fa": "خبرگزاری مهر",
        "slug": "mehr-news",
        "website_url": "https://www.mehrnews.com",
        "rss_urls": ["https://www.mehrnews.com/rss"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "principlist",
        "language": "both",
        "description_en": "Government-sponsored news agency. Founded 2003. Publishes in 6 languages.",
        "description_fa": "خبرگزاری دولتی. تأسیس ۱۳۸۲. انتشار به ۶ زبان.",
    },
    {
        "name_en": "ISNA",
        "name_fa": "ایسنا",
        "slug": "isna",
        "website_url": "https://www.isna.ir",
        "rss_urls": ["https://www.isna.ir/rss"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "moderate",
        "language": "both",
        "description_en": "Iranian Students' News Agency. Semi-independent, considered relatively moderate.",
        "description_fa": "خبرگزاری دانشجویان ایران. نیمه‌مستقل، نسبتاً معتدل.",
    },
    {
        "name_en": "Fars News Agency",
        "name_fa": "خبرگزاری فارس",
        "slug": "fars-news",
        "website_url": "https://www.farsnews.ir",
        "rss_urls": ["https://www.farsnews.ir/rss"],
        "state_alignment": "state",
        "irgc_affiliated": True,
        "production_location": "inside_iran",
        "factional_alignment": "hardline",
        "language": "both",
        "description_en": "IRGC-owned news agency. Founded 2003. Key voice of the hardline establishment.",
        "description_fa": "خبرگزاری متعلق به سپاه پاسداران. تأسیس ۱۳۸۲. صدای اصلی جریان اصولگرا.",
    },
]


async def seed_sources(db: AsyncSession) -> int:
    """Seed initial news sources. Returns count of newly created sources."""
    created = 0
    for source_data in INITIAL_SOURCES:
        existing = await db.execute(
            select(Source).where(Source.slug == source_data["slug"])
        )
        if existing.scalar_one_or_none() is None:
            source = Source(**source_data)
            db.add(source)
            created += 1
            logger.info(f"Created source: {source_data['slug']}")

    await db.commit()
    logger.info(f"Seeding complete: {created} new sources created")
    return created
