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
        "rss_urls": ["https://www.iranintl.com/fa/feed", "https://www.iranintl.com/en/feed"],
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
        "description_fa": "سکوی خبری مستقل با همکاری روزنامه‌نگاران مهاجر و خبرنگاران شهروندی داخل ایران.",
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
        "rss_urls": ["https://rss.dw.com/xml/rss-fa-all"],  # NOTE: DW Persian feed may be broken/unreliable
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
        # RSS geo-blocked from Railway; coverage comes from Telegram channel @Tasnimnews.
        "rss_urls": [],
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
        "rss_urls": ["https://www.presstv.ir/rss/rss-101.xml"],
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
        # RSS geo-blocked from Railway; coverage comes from Telegram channel @mehrnews.
        "rss_urls": [],
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
    {
        "name_en": "Tabnak",
        "name_fa": "تابناک",
        "slug": "tabnak",
        "website_url": "https://www.tabnak.ir",
        "rss_urls": ["https://www.tabnak.ir/fa/rss/allnews"],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "principlist",
        "language": "fa",
        "description_en": "Iranian news website affiliated with principlist faction. Semi-state media.",
        "description_fa": "وب‌سایت خبری وابسته به جریان اصولگرا. رسانه نیمه‌دولتی.",
    },
    # === New sources (added 2026-04-06) ===
    {
        "name_en": "RFI Farsi",
        "name_fa": "آر‌اف‌آی فارسی",
        "slug": "rfi-farsi",
        "website_url": "https://www.rfi.fr/fa/",
        "rss_urls": ["https://www.rfi.fr/fa/rss"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "Radio France International's Persian service. Independent, French state-funded.",
        "description_fa": "سرویس فارسی رادیو بین‌المللی فرانسه. مستقل، بودجه دولت فرانسه.",
    },
    {
        "name_en": "Radio Farda",
        "name_fa": "رادیو فردا",
        "slug": "radio-farda",
        "website_url": "https://www.radiofarda.com",
        "rss_urls": ["https://www.radiofarda.com/api/z-pqpiev-qpp"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "RFE/RL Persian service. US Congress-funded. Prague-based.",
        "description_fa": "سرویس فارسی رادیو اروپای آزاد. بودجه کنگره آمریکا. مستقر در پراگ.",
    },
    {
        "name_en": "VOA Farsi",
        "name_fa": "صدای آمریکا",
        "slug": "voa-farsi",
        "website_url": "https://ir.voanews.com",
        "rss_urls": ["https://ir.voanews.com/api/z-pqpiev-qpp"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "Voice of America Persian service. US government-funded.",
        "description_fa": "سرویس فارسی صدای آمریکا. بودجه دولت آمریکا.",
    },
    {
        "name_en": "Euronews Persian",
        "name_fa": "یورونیوز فارسی",
        "slug": "euronews-persian",
        "website_url": "https://fa.euronews.com",
        "rss_urls": ["https://fa.euronews.com/rss"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "European news network's Persian service. EU-funded, centrist.",
        "description_fa": "سرویس فارسی شبکه خبری اروپایی. بودجه اتحادیه اروپا.",
    },
    {
        "name_en": "Khabar Online",
        "name_fa": "خبرآنلاین",
        "slug": "khabar-online",
        "website_url": "https://www.khabaronline.ir",
        # RSS geo-blocked from Railway; coverage comes from Telegram channel @khabaronline_ir.
        "rss_urls": [],
        "state_alignment": "semi_state",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "moderate",
        "language": "fa",
        "description_en": "Iranian news website. Semi-state, moderate leaning. Inside Iran.",
        "description_fa": "وب‌سایت خبری ایرانی. نیمه‌دولتی، گرایش میانه‌رو.",
    },
    {
        "name_en": "Zeitoons",
        "name_fa": "زیتون",
        "slug": "zeitoons",
        "website_url": "https://www.zeitoons.com",
        "rss_urls": [],
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": "reformist",
        "language": "fa",
        "description_en": "Independent Persian media focused on civil society and reform.",
        "description_fa": "رسانه مستقل فارسی با تمرکز بر جامعه مدنی و اصلاحات.",
    },
    {
        "name_en": "Kayhan London",
        "name_fa": "کیهان لندن",
        "slug": "kayhan-london",
        "website_url": "https://kayhan.london",
        "rss_urls": ["https://kayhan.london/feed/"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": "monarchist",
        "language": "fa",
        "description_en": "London-based opposition newspaper. Monarchist-leaning. Founded 1984.",
        "description_fa": "روزنامه اپوزیسیون مستقر در لندن. گرایش سلطنت‌طلبانه. تأسیس ۱۹۸۴.",
    },
    {
        "name_en": "HRANA — Human Rights Activists News Agency",
        "name_fa": "هرانا — خبرگزاری فعالان حقوق بشر",
        "slug": "hrana",
        "website_url": "https://www.hra-news.org",
        "rss_urls": ["https://www.hra-news.org/feed/"],
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "Human rights news agency covering violations inside Iran — Baluch, Kurdish, labor, women, and political prisoner cases. US-based, cited by UN.",
        "description_fa": "خبرگزاری حقوق بشر که نقض حقوق را در ایران گزارش می‌دهد — بلوچ، کرد، کارگری، زنان، زندانیان سیاسی.",
    },
    {
        "name_en": "Etemad Online",
        "name_fa": "اعتماد آنلاین",
        # NOTE: slug deliberately `etemad-online` (not `etemad`). An existing
        # broken Etemad source with slug `etemad` and URL etemadnewspaper.ir
        # predates this seed entry; keeping distinct slugs avoids the
        # idempotent-skip behaviour of seed_sources silently dropping this row.
        # Deactivate the old `etemad` row in the Fetch Stats dashboard.
        "slug": "etemad-online",
        "website_url": "https://www.etemadonline.com",
        # RSS geo-blocked from Railway; coverage comes from Telegram channel @EtemadOnline.
        "rss_urls": [],
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "inside_iran",
        "factional_alignment": "reformist",
        "language": "fa",
        "description_en": "Leading domestic reformist daily (Khatami-era lineage). Published inside Iran; periodically suspended by judiciary.",
        "description_fa": "روزنامه اصلی اصلاح‌طلب داخلی (میراث دوره خاتمی). داخل ایران منتشر می‌شود؛ گاه توسط قوه قضائیه تعلیق شده است.",
    },
    # (Cycle-1 audit Island 13: removed duplicate dw-persian entry that
    # used to live here. Idempotency check on slug means the duplicate
    # never persisted; the rss-per-all URL it carried is patched into
    # production via app/main.py's startup DDL anyway.)
    {
        "name_en": "Independent Persian",
        "name_fa": "ایندیپندنت فارسی",
        "slug": "independent-persian",
        "website_url": "https://www.independentpersian.com",
        "rss_urls": ["https://www.independentpersian.com/rss.xml"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "The Independent's Persian-language edition. UK-based; mainstream liberal coverage of Iran and the region.",
        "description_fa": "نسخهٔ فارسی روزنامهٔ ایندیپندنت بریتانیا. پوشش اصلی‌جریان لیبرال دربارهٔ ایران و منطقه.",
    },
    {
        "name_en": "Akhbar-Rooz",
        "name_fa": "اخبار روز",
        "slug": "akhbar-rooz",
        "website_url": "https://akhbar-rooz.com",
        "rss_urls": ["https://akhbar-rooz.com/feed/"],
        "state_alignment": "diaspora",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "Long-running Persian-language left/socialist diaspora publication. Paris-based; political commentary and opinion.",
        "description_fa": "نشریهٔ قدیمی چپ و سوسیالیست برون‌مرزی. مستقر در پاریس؛ تحلیل سیاسی و مقالهٔ نظری.",
    },
    # === Human-rights & ethnic-minority monitors (added 2026-06-03) ===
    # Closes the protests/HR coverage gap (incident protest-hr-coverage-gap):
    # HRANA was our only HR outlet, and Baluch/Kurdish-rights coverage was zero.
    # Classified `independent` (non-partisan HR documentation) to match HRANA,
    # not `diaspora`, so HR-monitor volume doesn't skew the diaspora bias bucket.
    {
        "name_en": "Human Rights Activists News Agency (HRANA)",
        "name_fa": "خبرگزاری هرانا",
        "slug": "hrana",
        "website_url": "https://www.hra-news.org",
        # PERSIAN feed (verified 2026-06-03: 30 entries, same-day, native fa).
        # The English monitors (IHR/CHRI/KHRN) publish in English, which the
        # Persian-first pipeline drops as off-topic / fails to cluster — so HR
        # coverage never reached the homepage. HRANA is the premier inside-Iran
        # HR wire IN PERSIAN, so its protest/execution/kolbar reporting actually
        # clusters. The /en feed (en-hrana.org) is the English sibling — NOT used.
        "rss_urls": ["https://www.hra-news.org/feed/"],
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "both",
        "factional_alignment": None,
        "language": "fa",
        "description_en": "Persian-language Human Rights Activists News Agency — the premier inside-Iran HR wire (protests, executions, political prisoners, labor & kolbar deaths). Native Persian, so it clusters onto the homepage where our English HR monitors can't.",
        "description_fa": "خبرگزاری فعالان حقوق بشر (هرانا) — مرجع فارسی‌زبان پایش حقوق بشر در ایران؛ اعتراض‌ها، اعدام‌ها، زندانیان سیاسی، و جان‌باختن کارگران و کولبران.",
    },
    {
        "name_en": "Iran Human Rights (IHRNGO)",
        "name_fa": "سازمان حقوق بشر ایران",
        "slug": "iran-human-rights",
        "website_url": "https://iranhr.net",
        "rss_urls": ["https://iranhr.net/en/rss/"],  # verified Atom; /en/feed/ 403s, use /en/rss/
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "both",
        "description_en": "Oslo-based, non-partisan. The authoritative execution / death-penalty monitor for Iran, cited by the UN and wire services.",
        "description_fa": "مستقر در اسلو، غیرجناحی. مرجع پایش اعدام و مجازات مرگ در ایران؛ مورد استناد سازمان ملل.",
    },
    {
        "name_en": "Center for Human Rights in Iran (CHRI)",
        "name_fa": "مرکز حقوق بشر در ایران",
        "slug": "chri",
        "website_url": "https://iranhumanrights.org",
        "rss_urls": ["https://iranhumanrights.org/feed/"],  # verified RSS 2.0
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "both",
        "description_en": "New York-based, nonpartisan. High-quality English HR journalism (free expression, political prisoners, due process), heavily cited by academics.",
        "description_fa": "مستقر در نیویورک، غیرجناحی. روزنامه‌نگاری باکیفیت حقوق بشر؛ پراستناد نزد پژوهشگران.",
    },
    {
        "name_en": "Kurdistan Human Rights Network (KHRN)",
        "name_fa": "شبکهٔ حقوق بشر کردستان",
        "slug": "khrn",
        "website_url": "https://kurdistanhumanrights.org",
        "rss_urls": ["https://kurdistanhumanrights.org/en/feed"],  # no trailing slash — /en/feed/ 301-redirects (2026-06-03)
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "both",
        "description_en": "Paris-based monitor of Kurdish-region rights (kolbars, political prisoners) — a minority-rights blind spot none of our other sources cover.",
        "description_fa": "ناظر مستقر در پاریس بر حقوق مناطق کردنشین (کولبران، زندانیان سیاسی).",
    },
    {
        "name_en": "Haalvsh",
        "name_fa": "هالووش",
        "slug": "haalvsh",
        "website_url": "https://haalvsh.org",
        # Baluch-rights monitor. Feed CONFIRMED Cloudflare-blocked from Railway
        # (2026-06-03 ingest pulled 0 articles, 403) — rss_urls left empty;
        # re-add via its Telegram channel in a future Telegram batch.
        "rss_urls": [],
        "state_alignment": "independent",
        "irgc_affiliated": False,
        "production_location": "outside_iran",
        "factional_alignment": None,
        "language": "both",
        "description_en": "Baluch-rights monitor for Sistan-Baluchestan / Sunni community — our biggest geographic blind spot (Zahedan context).",
        "description_fa": "ناظر حقوق بلوچ در سیستان‌وبلوچستان و جامعهٔ اهل‌سنت — بزرگ‌ترین نقطهٔ کور جغرافیایی ما.",
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
