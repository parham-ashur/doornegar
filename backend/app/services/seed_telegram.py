"""Seed Telegram channels to track.

Comprehensive list from SOURCES_MASTER_LIST.md — analysts, news outlets,
aggregators, fact-checkers, and diaspora media.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import TelegramChannel

logger = logging.getLogger(__name__)

INITIAL_CHANNELS = [
    # ═══ ANALYSTS: Independent / Reform-leaning ═══
    {"username": "ahmadzeidabad", "title": "احمد زیدآبادی", "channel_type": "commentary", "political_leaning": "reformist", "language": "fa", "description": "Geopolitics, nuclear talks, domestic politics"},
    {"username": "sadeghzibakalam", "title": "صادق زیباکلام", "channel_type": "commentary", "political_leaning": "reformist", "language": "fa", "description": "Political science professor, government critique"},
    {"username": "abdiabbas", "title": "عباس عبدی", "channel_type": "commentary", "political_leaning": "reformist", "language": "fa", "description": "Reform strategy, public opinion"},
    {"username": "emadbaghi", "title": "عمادالدین باقی", "channel_type": "commentary", "political_leaning": "reformist", "language": "fa", "description": "Human rights, prisoner rights, theology"},
    {"username": "mohajerimohamad", "title": "محمد محاجری", "channel_type": "commentary", "political_leaning": "reformist", "language": "fa", "description": "Former Kayhan editor, principlist-turned-critical"},
    # MohammadMosaed — username invalid on Telegram, skipped

    # ═══ ANALYSTS: Academic / Philosophical ═══
    {"username": "mostafamalekian", "title": "مصطفی ملکیان", "channel_type": "commentary", "political_leaning": "neutral", "language": "fa", "description": "Philosophy, rationality, social ethics"},

    # ═══ ANALYSTS: Pro-regime / Hardline ═══
    {"username": "hasanabbasi_ir", "title": "حسن عباسی", "channel_type": "commentary", "political_leaning": "pro_regime", "language": "fa", "description": "IRGC strategist, asymmetric warfare"},
    {"username": "masaf", "title": "مؤسسه مصاف / رائفی‌پور", "channel_type": "commentary", "political_leaning": "pro_regime", "language": "fa", "description": "Ultra-hardline, conspiratorial"},
    {"username": "ali7adeh", "title": "علی علیزاده", "channel_type": "commentary", "political_leaning": "pro_regime", "language": "fa", "description": "London-based, shifted to pro-IR"},

    # ═══ ANALYSTS: Diaspora / External ═══
    {"username": "ammar_maleki", "title": "عمار ملکی", "channel_type": "commentary", "political_leaning": "opposition", "language": "fa", "description": "GAMAAN polling institute"},
    {"username": "HosseinBastaniChannel", "title": "حسین بستانی", "channel_type": "commentary", "political_leaning": "neutral", "language": "fa", "description": "BBC Persian investigative"},
    {"username": "masih_alinejad", "title": "مسیح علینژاد", "channel_type": "commentary", "political_leaning": "opposition", "language": "fa", "description": "Women's rights, VOA"},
    {"username": "AbdiMedia", "title": "عبدالله عبدی / عبدی مدیا", "channel_type": "commentary", "political_leaning": "opposition", "language": "fa", "description": "Investigative journalism"},

    # ═══ ORGANIZATIONS / FACT-CHECKERS ═══
    {"username": "factnameh", "title": "فکت‌نامه", "channel_type": "commentary", "political_leaning": "neutral", "language": "fa", "description": "IFCN-certified fact-checking, Toronto"},
    {"username": "rasad_tahlil", "title": "رصد", "channel_type": "commentary", "political_leaning": "neutral", "language": "fa", "description": "Think-tank style aggregator"},
    {"username": "AkhbarRouz", "title": "اخبار روز", "channel_type": "news", "political_leaning": "opposition", "language": "fa", "description": "Left-leaning diaspora"},

    # ═══ STATE / IRGC NEWS ═══
    {"username": "farsna", "title": "خبرگزاری فارس", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "Fars News Agency, IRGC primary, ~1.8M"},
    {"username": "Tasnimnews", "title": "خبرگزاری تسنیم", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "Tasnim News, IRGC/Quds Force, ~2.5M"},
    {"username": "mehrnews", "title": "خبرگزاری مهر", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "Mehr News, Supreme Leader-supervised"},
    {"username": "mashreghnews_channel", "title": "مشرق نیوز", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "IRGC-affiliated"},
    {"username": "Nournews_ir", "title": "نور نیوز", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "SNSC-linked"},
    {"username": "BisimchiMedia", "title": "بسیمچی مدیا", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "IRGC propaganda"},

    # ═══ OFFICIAL STATE AGENCIES ═══
    # iraborz — username not found on Telegram, skipped
    {"username": "iribnews", "title": "اخبار صدا و سیما", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "IRIB, Supreme Leader-controlled"},
    {"username": "isna94", "title": "ایسنا", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "Semi-official, university-linked"},
    {"username": "ilnair", "title": "ایلنا", "channel_type": "news", "political_leaning": "reformist", "language": "fa", "description": "Labor-affiliated, reform-leaning"},
    {"username": "yjcnewschannel", "title": "باشگاه خبرنگاران جوان", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "IRIB youth"},

    # ═══ DOMESTIC PRESS ═══
    {"username": "SharghDaily", "title": "روزنامه شرق", "channel_type": "news", "political_leaning": "reformist", "language": "fa", "description": "Reformist daily"},
    {"username": "EtemadOnline", "title": "روزنامه اعتماد", "channel_type": "news", "political_leaning": "reformist", "language": "fa", "description": "Reformist daily"},
    {"username": "hammihanonline", "title": "هم‌میهن", "channel_type": "news", "political_leaning": "reformist", "language": "fa", "description": "Reformist/moderate"},
    {"username": "khabaronline_ir", "title": "خبرآنلاین", "channel_type": "news", "political_leaning": "moderate", "language": "fa", "description": "Khabar Online, moderate"},
    {"username": "Asriran_press", "title": "عصر ایران", "channel_type": "news", "political_leaning": "moderate", "language": "fa", "description": "Moderate"},
    {"username": "entekhab_ir", "title": "انتخاب", "channel_type": "news", "political_leaning": "moderate", "language": "fa", "description": "Moderate aggregator"},
    # Tabnak_ir — username not found on Telegram, skipped
    {"username": "rajanews_com", "title": "رجانیوز", "channel_type": "news", "political_leaning": "pro_regime", "language": "fa", "description": "Hardline principlist"},

    # ═══ AGGREGATORS ═══
    {"username": "akhbarefori", "title": "اخبار فوری", "channel_type": "aggregator", "political_leaning": "neutral", "language": "fa", "is_aggregator": True, "description": "Major news aggregator, ~2.6M subscribers"},
    {"username": "akaborz", "title": "آخرین خبر", "channel_type": "aggregator", "political_leaning": "neutral", "language": "fa", "is_aggregator": True, "description": "News aggregator, ~2.6M subscribers"},
    {"username": "VahidOnline", "title": "وحید آنلاین", "channel_type": "aggregator", "political_leaning": "neutral", "language": "fa", "is_aggregator": True, "description": "Major political channel, ~1.33M subscribers"},
    {"username": "mamlekate", "title": "مملکته", "channel_type": "aggregator", "political_leaning": "neutral", "language": "fa", "is_aggregator": True, "description": "Breaking news + satire, ~500K subscribers"},

    # ═══ DIASPORA / INTERNATIONAL MEDIA ═══
    {"username": "bbcpersian", "title": "بی‌بی‌سی فارسی", "channel_type": "news", "political_leaning": "neutral", "language": "fa", "description": "BBC Persian, London, UK public funded"},
    {"username": "iranintltv", "title": "ایران اینترنشنال", "channel_type": "news", "political_leaning": "opposition", "language": "fa", "description": "Iran International, London, Saudi-linked"},
    # VOAIran, RadioFarda_, manaborz, IranWireFA — usernames not found on Telegram, skipped
    {"username": "radiozamaneh", "title": "رادیو زمانه", "channel_type": "news", "political_leaning": "reformist", "language": "fa", "description": "Radio Zamaneh"},
    {"username": "zeitoons", "title": "زیتون", "channel_type": "commentary", "political_leaning": "reformist", "language": "fa", "description": "Independent media, civil society focus"},

    # ═══ ENGLISH-LANGUAGE (lower priority) ═══
    {"username": "presstv", "title": "Press TV", "channel_type": "news", "political_leaning": "pro_regime", "language": "en", "description": "State-funded English channel"},
]


async def seed_telegram_channels(db: AsyncSession) -> int:
    """Seed Telegram channels. Returns count of newly created."""
    created = 0
    for channel_data in INITIAL_CHANNELS:
        existing = await db.execute(
            select(TelegramChannel).where(
                TelegramChannel.username == channel_data["username"]
            )
        )
        if existing.scalar_one_or_none() is None:
            channel = TelegramChannel(**channel_data)
            db.add(channel)
            created += 1
            logger.info(f"Created Telegram channel: @{channel_data['username']}")

    await db.commit()
    logger.info(f"Telegram seeding complete: {created} new channels")
    return created
