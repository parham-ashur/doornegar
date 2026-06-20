"""Content-type classifier for the ingest pipeline.

Iranian outlets dump a mix of original reporting, op-eds, panel and
interview transcripts, talk-show writeups, and aggregator pieces that
just summarise other outlets. We only want original news downstream
into NLP / clustering / bias scoring; everything else is noise.

The classifier runs between ingest and NLP. It labels each article as
one of:

    news          original reporting on a current event           (keep)
    opinion       op-eds, columns, editorials                     (drop)
    discussion    interviews, panel discussions, roundtables      (drop)
    aggregation   summarises / re-quotes other outlets            (drop)
    other         analysis, explainers, listicles, service        (drop)

Per-source whitelist lives in ``Source.content_filters['allowed']``
(default ``["news"]``). NLP only picks up articles whose label is in
the source's allowed set.

Implementation is cascaded:

1. **Heuristics** (free) — Persian keyword / URL / RSS-category
   signals. When a strong signal fires we emit a confidence-≥0.8
   label and stop.
2. **LLM fallback** (gpt-4.1-nano via OpenAI) for ambiguous cases,
   batched 10 articles per call. Logs cost under the
   ``ingest.content_type`` purpose tag.

At ~2000 articles/day with ~70% heuristic catch we expect <$1/month.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.article import Article
from app.models.source import Source

logger = logging.getLogger(__name__)


LABELS = ("news", "opinion", "discussion", "aggregation", "other", "off_topic")
DEFAULT_ALLOWED = ("news",)
HEURISTIC_CONFIDENCE_FLOOR = 0.8
LLM_BATCH_SIZE = 10
ARTICLE_BODY_TRUNCATE = 400


# ─── Persian / English keyword tables ──────────────────────────────────
# Title-prefix patterns. Iranian outlets routinely prepend section labels
# like "یادداشت/" or "گفت‌وگو/" before the headline.
_OPINION_TITLE_PREFIXES = (
    "یادداشت",
    "سرمقاله",
    "ستون",
    "نقد ",
    "اپ‌اد",
    "اپ ـ اد",
    "opinion",
    "editorial",
)
_DISCUSSION_TITLE_PREFIXES = (
    "گفت‌وگو",
    "گفت و گو",
    "گفتگو",
    "مصاحبه",
    "میزگرد",
    "پرسش و پاسخ",
    "interview",
)

# URL-slug substrings (case-insensitive). Highest precision when present.
_OPINION_URL_PATTERNS = (
    "/opinion",
    "/yaddasht",
    "/sarmaghaleh",
    "/editorial",
    "/column",
    "/note",
    "/یادداشت",
    "/سرمقاله",
)
_DISCUSSION_URL_PATTERNS = (
    "/interview",
    "/goftogu",
    "/goft-o-gu",
    "/mosahebe",
    "/panel",
    "/roundtable",
    "/مصاحبه",
    "/گفتگو",
)
_OTHER_URL_PATTERNS = (
    "/analysis",
    "/explainer",
    "/feature",
    "/تحلیل",
)

# RSS <category> tag substrings.
_OPINION_RSS = ("opinion", "editorial", "column", "یادداشت", "سرمقاله")
_DISCUSSION_RSS = ("interview", "panel", "گفت", "مصاحبه", "میزگرد")
_OTHER_RSS = ("analysis", "explainer", "تحلیل")

# ─── Off-domain topic blocklist (Parham 2026-05-01 evening) ────────────
# These match the sections we don't want eating LLM budget: sports,
# entertainment, lifestyle. Matched against rss_category (highest
# precision, source-supplied) and title section labels. When fired,
# article is labeled "other" with conf 0.9 — short-circuits the
# gpt-4.1-nano classifier AND the downstream NLP/cluster/score path
# since `other` isn't in any source's content_filters['allowed'] list.
# Conservative: words like "استقلال" (independence — also a Tehran
# football club) and "بازیگر" (actor — also "political actor")
# are intentionally excluded because their political usage is real.
_OFF_DOMAIN_RSS = (
    # Sports
    "ورزش", "ورزشی", "فوتبال", "والیبال", "بسکتبال", "هندبال",
    "sport", "sports", "football",
    # Entertainment
    "سینما", "موسیقی", "هنری", "تلویزیون", "سرگرمی", "سلبریتی",
    "entertainment", "celebrity", "music", "cinema",
    # Lifestyle
    "آشپزی", "طالع", "فال", "مد", "آرایش", "گردشگری", "سبک زندگی",
    "lifestyle", "cooking", "horoscope", "fashion", "tourism",
)

# Title section-label keywords (matched via _title_label_match for high
# precision — only fires when the keyword appears as a section prefix
# with a separator like ورزش/, ورزش:, ورزش -).
_OFF_DOMAIN_TITLE_PREFIXES = (
    # Sports
    "ورزش", "ورزشی", "فوتبال", "والیبال", "بسکتبال", "هندبال",
    "جام جهانی", "المپیک", "پرسپولیس",
    # Entertainment
    "سینما", "موسیقی", "سلبریتی", "جشنواره فیلم",
    # Lifestyle
    "آشپزی", "طالع", "فال", "گردشگری",
)
# High-precision off-domain terms that can appear ANYWHERE in the title,
# not just as a section-label prefix. Catches Telegram-converted posts and
# feeds that carry no rss_category/section tag (e.g. «کاسمیرو در مسیر میامی»,
# «ایران قهرمان وزنه‌برداری جهان شد») — the exact junk that slipped past the
# prefix/rss checks into war clusters (Niloofar audit 2026-06-02). Kept tight:
# sports-specific terms + unambiguous club/athlete proper nouns + a few
# lifestyle tells. Anything ambiguous falls through to the LLM scope check.
_OFF_DOMAIN_CONTENT = (
    # Sports — competitions, roles, transfers
    "لیگ برتر", "لیگ قهرمانان", "جام جهانی", "جام ملت", "سرمربی", "نیمکت ذخیره",
    "نقل و انتقالات", "وزنه‌برداری", "وزنه برداری", "گل‌زنی", "هتریک",
    "تیم ملی فوتبال", "تیم ملی والیبال", "تیم ملی کشتی", "قهرمان جهان شد",
    "قهرمانی جوانان وزنه", "مسابقات وزنه‌برداری", "مدال طلا گرفت", "صعود به لیگ برتر",
    # Sports — goal-scoring lines in match reports. The ORDINAL "گل اول/دوم/…"
    # appears only in football match writeups; high precision. Added 2026-06-20
    # after a Niloofar audit found tasnim match reports («گل دوم آرژانتین به
    # الجزایر توسط مسی در دقیقه ۶۰», «گل سوم نروژ به عراق») mislabeled news@1.0
    # by the nano stage and clustering into war grab-bags. Firing here (step 0,
    # before the news-verb heuristic) keeps them off the nano path entirely.
    "گل اول", "گل دوم", "گل سوم", "گل چهارم", "گل پنجم", "گل ششم",
    "خلاصه بازی", "خلاصه نیمه",
    # Clubs / athletes (almost always sports in an Iran-news feed)
    "رئال مادرید", "بارسلونا", "منچسترسیتی", "منچستر یونایتد", "گواردیولا",
    "آرتتا", "لیونل مسی", "کریستیانو رونالدو", "رافائل نادال", "کاسمیرو",
    "اینفانتینو", "قلعه‌نویی", "لامین یامال", "کی‌روش", "رونالدینیو",
    # Entertainment / film / lifestyle fluff
    "جشنواره فیلم", "باکس آفیس", "اکران کمدی", "آلبوم موسیقی", "مولتی ویتامین",
    "طالع بینی", "فال روز",
    # Book-publisher promo spam. The shargh feed floods dozens of identical
    # «انتشارات کتاب شرق منتشر کرد» book-release ads, mislabeled news and
    # polluting clusters (2026-06-20). Promotional/cultural, not political news.
    "انتشارات کتاب شرق",
)

# Political/diplomatic override (Parham 2026-06-06): if any of these appear, the
# article is treated as NEWS even when it also trips the sports blocklist —
# they're diplomacy/statecraft terms that don't occur in a routine match
# report, so they won't leak ordinary sports coverage. Caught the US-visa /
# World-Cup-team story that was being dropped as off_topic.
_POLITICAL_OVERRIDE_TERMS = (
    "ویزا", "تحریم", "وزارت خارجه", "وزارت امور خارجه", "کاخ سفید",
    "سفارت", "دیپلمات", "پاسپورت", "گذرنامه",
)

# Lede news verbs. Strong signal that the article opens with a
# reported fact rather than an opinion/quote framing.
_NEWS_VERBS = (
    "اعلام کرد",
    "خبر داد",
    "گزارش داد",
    "اظهار داشت",
    "تأکید کرد",
    "تاکید کرد",
    "گفت:",
    "افزود:",
    "اعلام شد",
    "منتشر کرد",
    "announced",
    "reported",
)

# Aggregation tells in body — heavy attribution to other outlets.
_AGGREGATION_VERBS = ("به نقل از", "به گزارش", "نقل از")
# Multi-topic ROUNDUP headlines (2026-06-03 clustering-quality pass). These
# bundle many unrelated items under one title, so their embedding sits near
# "general news" and they glue onto whatever cluster is nearby (a BBC world
# roundup landed in a singer's obituary). Drop as aggregation. High-precision
# multi-word phrases only — avoid bare "خبرهای جهان" which appears in real leads.
_ROUNDUP_TITLE_PATTERNS = (
    "تازه‌ترین خبرهای جهان", "خبرهای کوتاه", "چند خبر کوتاه", "اخبار کوتاه",
    "مرور مطبوعات", "نگاهی به مطبوعات", "گزیده اخبار", "بسته خبری",
    "تیتر روزنامه‌ها", "مهم‌ترین عناوین", "مرور رسانه‌ها",
)
# Persian quote chars («...») that aggregators string together.
_PERSIAN_QUOTE_RE = re.compile(r"«[^»]+»")


# ─── Heuristic stage ──────────────────────────────────────────────────
@dataclass(frozen=True)
class _Verdict:
    label: str
    confidence: float


def heuristic_classify(article: Article) -> _Verdict | None:
    """Return a high-confidence (label, confidence) pair, or None when
    signals are mixed and we should defer to the LLM.

    Pure function — no DB, no IO. Easy to test with stub Article-like
    objects.
    """
    title = (article.title_original or "").strip()
    body = (article.content_text or article.summary or "").strip()
    url = (article.url or "").lower()
    rss_cat = (article.rss_category or "").lower()

    # 0. Off-domain blocklist (sports / entertainment / lifestyle).
    #    Fires before everything else so we never pay the gpt-4.1-nano
    #    classifier on a sports column. Two precision tiers:
    #    a) rss_category match — source explicitly tagged the section.
    #    b) title section-label match — same precision rule as the
    #       opinion/discussion checks below, requires a separator after
    #       the keyword so "ورزشگاه" doesn't trip "ورزش".
    #
    # Political-diplomacy OVERRIDE (Parham 2026-06-06): a story carrying a
    # clear diplomatic/political signal is NEWS even if it mentions the team.
    # The «تیم ملی فوتبال» entry in the sports list was dropping a major Iran
    # story — US visa diplomacy around the World Cup team (NYT / White House /
    # sanctions) — as off_topic, so 12 articles never clustered. These signals
    # are diplomatic, not sports, so they don't leak routine match reports.
    _pol_blob = title + " " + body[:600]
    _political_override = any(
        kw in _pol_blob for kw in _POLITICAL_OVERRIDE_TERMS
    )
    if not _political_override:
        if rss_cat:
            for kw in _OFF_DOMAIN_RSS:
                if kw in rss_cat:
                    return _Verdict("off_topic", 0.9)
        title_head_for_off = title[:60]
        for kw in _OFF_DOMAIN_TITLE_PREFIXES:
            if _title_label_match(title_head_for_off, kw):
                return _Verdict("off_topic", 0.9)
        # c) content keywords anywhere in the title — section-tag-free junk
        #    (Telegram posts, untagged feeds). High precision; ambiguous cases
        #    defer to the LLM.
        for kw in _OFF_DOMAIN_CONTENT:
            if kw in title:
                return _Verdict("off_topic", 0.9)

    # 0b. Multi-topic roundup headlines → aggregation (drop). Cluster-pollution
    #     guard: these bundle unrelated items and attach to any nearby cluster.
    for kw in _ROUNDUP_TITLE_PATTERNS:
        if kw in title:
            return _Verdict("aggregation", 0.9)

    # 1. URL-slug patterns — highest precision when they fire.
    for pat in _OPINION_URL_PATTERNS:
        if pat in url:
            return _Verdict("opinion", 0.95)
    for pat in _DISCUSSION_URL_PATTERNS:
        if pat in url:
            return _Verdict("discussion", 0.95)
    for pat in _OTHER_URL_PATTERNS:
        if pat in url:
            return _Verdict("other", 0.85)

    # 2. RSS category. Same idea, slightly lower precision because the
    #    field is free-form and outlets sometimes reuse one tag for
    #    everything.
    if rss_cat:
        if any(k in rss_cat for k in _OPINION_RSS):
            return _Verdict("opinion", 0.9)
        if any(k in rss_cat for k in _DISCUSSION_RSS):
            return _Verdict("discussion", 0.9)
        if any(k in rss_cat for k in _OTHER_RSS):
            return _Verdict("other", 0.85)

    # 3. Title prefixes — Iranian outlets routinely tag the section in
    #    the headline. Match either as a prefix or with a slash/colon
    #    separator inside the first 30 chars.
    #
    # MoU guard (2026-06-20): «یادداشت تفاهم» / «تفاهم‌نامه» = Memorandum of
    # Understanding (the Iran-US deal — the top story), NOT an op-ed «یادداشت».
    # Without this, headlines like «مسعود پزشکیان یادداشت تفاهم را امضا کرد»
    # matched the «یادداشت» op-ed prefix and were dropped as opinion at ingest,
    # starving deal coverage. The adjacent «یادداشت تفاهم» check is precise: it
    # spares MoU-content news but still flags «یادداشت العربیه …» (a real note/
    # op-ed) as opinion. Found via the content_type validation dry-run.
    _is_mou = (
        "یادداشت تفاهم" in title
        or "تفاهم‌نامه" in title
        or "تفاهم نامه" in title
    )
    title_head = title[:60]
    for kw in _OPINION_TITLE_PREFIXES:
        if kw == "یادداشت" and _is_mou:
            continue
        if _title_label_match(title_head, kw):
            return _Verdict("opinion", 0.9)
    for kw in _DISCUSSION_TITLE_PREFIXES:
        if _title_label_match(title_head, kw):
            return _Verdict("discussion", 0.9)

    # 4. Body-based aggregation detection.
    if body:
        attribution_hits = sum(body.count(v) for v in _AGGREGATION_VERBS)
        if attribution_hits >= 3:
            return _Verdict("aggregation", 0.85)
        # Heavy quoting: most of the body lives inside «...» quote pairs.
        if len(body) >= 300:
            quoted_chars = sum(len(m) for m in _PERSIAN_QUOTE_RE.findall(body))
            if quoted_chars / len(body) > 0.6:
                return _Verdict("aggregation", 0.85)

    # 5. News-verb tell in the lede. Lower confidence than the
    #    drop-signals above because original reporting and op-eds can
    #    both quote officials.
    if body:
        opening = body[:400]
        if any(v in opening for v in _NEWS_VERBS):
            return _Verdict("news", 0.85)

    # No strong signal — let the LLM look at it.
    return None


def _title_label_match(title_head: str, keyword: str) -> bool:
    """True when ``keyword`` appears as a section-label prefix.

    Iranian outlets mix several separator conventions: ``یادداشت/``,
    ``یادداشت:``, ``یادداشت |``, sometimes a leading slash. We accept
    any of these inside the first 60 chars.
    """
    if not title_head.startswith(keyword) and keyword not in title_head[:30]:
        return False
    # Reject false positives where the keyword is just part of a longer word.
    idx = title_head.find(keyword)
    after = title_head[idx + len(keyword) : idx + len(keyword) + 2]
    if not after:
        return True
    return after[0] in (" ", "/", ":", "|", "،", "-", "—", "ـ")


# ─── LLM stage ────────────────────────────────────────────────────────
_LLM_PROMPT = """\
You are a content-type classifier for an Iranian news aggregator.

This aggregator covers IRAN's politics, governance, economy & policy, the
ongoing conflict/war, foreign relations, human rights, and society of political
significance. Anything outside that scope is off_topic, even if it is genuine
reporting.

For each numbered article, label it with ONE of:
- news: original reporting on an in-scope current event (kept)
- opinion: op-eds, columns, editorials, personal commentary
- discussion: interviews, panel discussions, talk-show transcripts, Q&As
- aggregation: primarily summarizes or quotes other outlets without adding original reporting
- other: analysis pieces, explainers, listicles, service journalism
- off_topic: outside the aggregator's scope — sports, weather forecasts,
  entertainment/celebrity, arts/culture features, horoscopes, routine consumer
  prices, lifestyle/health tips, local accidents/fires with no political angle,
  unrelated foreign news, book/product release promos. Use this even when the
  piece is original reporting. CRITICAL: a sports match report is ALWAYS
  off_topic — e.g. «گل دوم آرژانتین به الجزایر توسط مسی در دقیقه ۶۰», «خلاصه
  بازی», a World-Cup score line, or any goal/match/score writeup — even when it
  mentions Iran's national team. (A sports story is only in-scope when its
  substance is diplomatic/political, e.g. visa or sanctions affecting a team.)

Return a JSON array. One object per article, in the same order:
  {{"id": <int>, "label": "<one of the six>", "confidence": <float 0-1>}}

No prose, no markdown fences, no commentary — JSON array only.

Articles:

{items}
"""


def _format_article_for_prompt(idx: int, article: Article) -> str:
    body = (article.content_text or article.summary or "").strip()
    body = body[:ARTICLE_BODY_TRUNCATE]
    title = (article.title_original or "").strip()
    rss_cat = (article.rss_category or "").strip()
    parts = [f"{idx}. TITLE: {title}"]
    if rss_cat:
        parts.append(f"   RSS_CATEGORY: {rss_cat}")
    parts.append(f"   BODY: {body}")
    return "\n".join(parts)


async def _call_openai_classify(prompt: str) -> str:
    """Call OpenAI for classification and log the usage line.

    Mirrors the cheap-tier pattern in ``bias_scoring._call_openai``:
    same client, same ``build_openai_params`` helper, same
    ``log_llm_usage`` ledger — just a different model and purpose tag.

    Tests patch this function directly to bypass the network.
    """
    import openai

    from app.services.llm_helper import build_openai_params
    from app.services.llm_usage import log_llm_usage

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.content_type_model,
        prompt=prompt,
        max_tokens=600,
        temperature=0,
    )
    response = await client.chat.completions.create(**params)
    await log_llm_usage(
        model=settings.content_type_model,
        purpose="ingest.content_type",
        usage=response.usage,
    )
    return response.choices[0].message.content or ""


def _parse_llm_response(raw: str, n: int) -> list[_Verdict | None]:
    """Parse the JSON array from the LLM. Returns ``n`` slots,
    populating None where the model omitted an entry or returned
    junk."""
    text = raw.strip()
    # Strip markdown fences if the model ignored instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]

    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        # Try to lift the first array out of free-form output.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.warning("Could not parse LLM classification response: %s", raw[:200])
            return [None] * n
        try:
            arr = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("Malformed JSON in LLM classification response: %s", raw[:200])
            return [None] * n

    if not isinstance(arr, list):
        return [None] * n

    out: list[_Verdict | None] = [None] * n
    for entry in arr:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        if not (1 <= idx <= n):
            continue
        label = entry.get("label")
        if label not in LABELS:
            continue
        try:
            conf = float(entry.get("confidence", 0.6))
        except (TypeError, ValueError):
            conf = 0.6
        conf = max(0.0, min(1.0, conf))
        out[idx - 1] = _Verdict(label, conf)
    return out


async def _classify_batch_via_llm(
    articles: list[Article],
) -> list[_Verdict | None]:
    if not articles:
        return []
    if not settings.openai_api_key:
        logger.warning(
            "Content-type classifier: OPENAI_API_KEY not set, leaving %d articles unclassified",
            len(articles),
        )
        return [None] * len(articles)

    items = "\n\n".join(
        _format_article_for_prompt(i + 1, a) for i, a in enumerate(articles)
    )
    prompt = _LLM_PROMPT.format(items=items)

    try:
        raw = await _call_openai_classify(prompt)
    except Exception as e:
        logger.warning("Content-type LLM call failed: %s", e)
        return [None] * len(articles)
    return _parse_llm_response(raw, n=len(articles))


# ─── Persistence step ─────────────────────────────────────────────────
async def classify_unclassified_articles(
    db: AsyncSession,
    *,
    batch_size: int = 200,
) -> dict:
    """Label every ``content_type IS NULL`` article and persist.

    Heuristic first; ambiguous cases batched 10 per LLM call.

    Returns counts: ``{total, by_label, llm_called, llm_returned, unresolved}``.
    """
    # Defer heavy cols (cycle-1 audit Island 1): heuristic_classify reads
    # title/url/rss_category/content_text/summary. embedding, keywords,
    # named_entities are never read in this batch path. ~5 MB per run saved.
    from sqlalchemy.orm import defer as _defer_ct
    result = await db.execute(
        select(Article)
        .options(
            _defer_ct(Article.embedding),
            _defer_ct(Article.keywords),
            _defer_ct(Article.named_entities),
        )
        .where(Article.content_type.is_(None))
        .order_by(Article.ingested_at.desc())
        .limit(batch_size)
    )
    articles = list(result.scalars().all())
    if not articles:
        return {
            "total": 0,
            "by_label": {},
            "llm_called": 0,
            "llm_returned": 0,
            "unresolved": 0,
        }

    by_label: dict[str, int] = {}
    pending: list[Article] = []

    for article in articles:
        verdict = heuristic_classify(article)
        if verdict and verdict.confidence >= HEURISTIC_CONFIDENCE_FLOOR:
            article.content_type = verdict.label
            article.content_type_confidence = verdict.confidence
            by_label[verdict.label] = by_label.get(verdict.label, 0) + 1
        else:
            pending.append(article)

    llm_called = 0
    llm_returned = 0
    unresolved = 0

    for batch_start in range(0, len(pending), LLM_BATCH_SIZE):
        batch = pending[batch_start : batch_start + LLM_BATCH_SIZE]
        verdicts = await _classify_batch_via_llm(batch)
        llm_called += len(batch)
        for article, verdict in zip(batch, verdicts):
            if verdict is None:
                # Don't silently default to a label. Leave NULL so the
                # next run retries; downstream NLP keeps skipping it
                # until a verdict lands.
                unresolved += 1
                continue
            llm_returned += 1
            article.content_type = verdict.label
            article.content_type_confidence = verdict.confidence
            by_label[verdict.label] = by_label.get(verdict.label, 0) + 1

    await db.commit()

    # Cycle-1 audit Island 1: surface unresolved_ratio so a runaway
    # LLM failure rate is visible without scraping the full log.
    unresolved_ratio = (unresolved / llm_called) if llm_called else 0.0
    logger.info(
        "Content-type classifier: total=%d heuristic-keep=%d llm=%d unresolved=%d unresolved_ratio=%.2f by_label=%s",
        len(articles),
        len(articles) - len(pending),
        llm_called,
        unresolved,
        unresolved_ratio,
        by_label,
    )
    if llm_called >= 10 and unresolved_ratio > 0.30:
        logger.warning(
            "Content-type LLM unresolved_ratio %.0f%% (>30%%) — possible LLM degradation",
            unresolved_ratio * 100,
        )
    return {
        "total": len(articles),
        "by_label": by_label,
        "llm_called": llm_called,
        "llm_returned": llm_returned,
        "unresolved": unresolved,
    }
