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


LABELS = ("news", "opinion", "discussion", "aggregation", "other")
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
    title_head = title[:60]
    for kw in _OPINION_TITLE_PREFIXES:
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

For each numbered article, label it with ONE of:
- news: original reporting on a current event (kept)
- opinion: op-eds, columns, editorials, personal commentary
- discussion: interviews, panel discussions, talk-show transcripts, Q&As
- aggregation: primarily summarizes or quotes other outlets without adding original reporting
- other: analysis pieces, explainers, listicles, service journalism

Return a JSON array. One object per article, in the same order:
  {{"id": <int>, "label": "<one of the five>", "confidence": <float 0-1>}}

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
    result = await db.execute(
        select(Article)
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

    logger.info(
        "Content-type classifier: total=%d heuristic-keep=%d llm=%d unresolved=%d by_label=%s",
        len(articles),
        len(articles) - len(pending),
        llm_called,
        unresolved,
        by_label,
    )
    return {
        "total": len(articles),
        "by_label": by_label,
        "llm_called": llm_called,
        "llm_returned": llm_returned,
        "unresolved": unresolved,
    }
