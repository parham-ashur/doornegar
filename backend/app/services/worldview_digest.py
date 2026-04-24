"""Weekly worldview synthesis — one card per 4-subgroup bundle.

Entry point: `generate_worldview_digests(db, anchor=None)`.

For each of the 4 bundles the service:
  1. Pulls every article published in the 7-day window whose source
     maps to that bundle (via narrative_groups.narrative_group).
  2. Joins in their BiasScore rows for framing/tone/reasoning.
  3. Pre-aggregates (deterministic, no LLM) into compact frequency
     tables + a sampled set of per-article bias narratives.
  4. Cross-bundle pass detects topic absences — topics other bundles
     covered that this bundle didn't.
  5. Calls Claude once per bundle with the pre-aggregated input and a
     strict-JSON prompt, logs the cost under purpose='worldview_digest'.
  6. Validates the output (drops beliefs with <3 articles or <2 sources)
     and upserts into worldview_digests.

Preconditions per bundle (audit_worldview_coverage.py enforces the same
thresholds). If a bundle fails any, we write a row with status='insufficient'
instead of synthesizing — a quiet week reads as quiet on the UI.
"""
from __future__ import annotations

import json
import logging
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, distinct
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.article import Article
from app.models.bias_score import BiasScore
from app.models.source import Source
from app.models.worldview_digest import WorldviewDigest
from app.services.llm_usage import log_llm_usage
from app.services.narrative_groups import (
    NARRATIVE_GROUPS_ORDER,
    NarrativeGroup,
    narrative_group,
)

logger = logging.getLogger(__name__)

# ─── Preconditions (mirror scripts/audit_worldview_coverage.py) ──────
MIN_SOURCES = 3
MIN_ARTICLES = 20
MIN_BIAS_COVERAGE_PCT = 75

# Grounding floor: every published belief must be backed by ≥3 articles
# from ≥2 distinct sources. Enforced after the LLM returns.
MIN_ARTICLES_PER_BELIEF = 3
MIN_SOURCES_PER_BELIEF = 2

# LLM sampling bounds
SAMPLE_BIAS_NARRATIVES = 10
TOP_ENTITIES = 20
TOP_FRAMINGS = 15
TOP_TOPICS = 20

# Cross-bundle absence detection
ABSENCE_OTHER_BUNDLES_COVERING = 2  # topic must show up in ≥2 other bundles
ABSENCE_OTHER_BUNDLES_MIN_COUNT = 5  # with ≥5 articles each there


# ─── Data shapes ─────────────────────────────────────────────────────
@dataclass
class BundleAggregate:
    """Deterministic pre-LLM digest of one bundle's 7 days of coverage."""
    bundle: NarrativeGroup
    window_start: datetime
    window_end: datetime
    article_count: int
    source_count: int
    bias_coverage_pct: float
    # article_id → source_id lookup (string UUIDs) so belief validation can
    # verify ≥2 distinct sources per cited set.
    article_to_source: dict[str, str] = field(default_factory=dict)
    # [(label, count)], top N
    framing_top: list[tuple[str, int]] = field(default_factory=list)
    entity_top: list[tuple[str, int]] = field(default_factory=list)
    topic_top: list[tuple[str, int]] = field(default_factory=list)
    # Tone averages: political_alignment mean/std, tone_score mean, emotional mean
    tone_summary: dict[str, float] = field(default_factory=dict)
    # [{article_id, reasoning_fa}] — sampled bias narratives to give the LLM
    # concrete prose to work from instead of only frequency counts.
    bias_samples: list[dict[str, Any]] = field(default_factory=list)
    # Topics covered in ≥2 other bundles but not this one.
    absences: list[str] = field(default_factory=list)

    def passes_preconditions(self) -> tuple[bool, list[str]]:
        failures = []
        if self.source_count < MIN_SOURCES:
            failures.append(f"sources={self.source_count} < {MIN_SOURCES}")
        if self.article_count < MIN_ARTICLES:
            failures.append(f"articles={self.article_count} < {MIN_ARTICLES}")
        if self.bias_coverage_pct < MIN_BIAS_COVERAGE_PCT:
            failures.append(
                f"bias_coverage={self.bias_coverage_pct:.1f}% < {MIN_BIAS_COVERAGE_PCT}%"
            )
        return (not failures, failures)


# ─── Step 1–2: SQL pull + join ───────────────────────────────────────
async def _gather_bundle_data(
    db: AsyncSession,
    bundle: NarrativeGroup,
    window_start: datetime,
    window_end: datetime,
    src_to_bundle: dict[str, NarrativeGroup],
) -> tuple[list[Article], dict[str, BiasScore]]:
    """Return (articles in bundle/window, {article_id_str: BiasScore})."""
    # Source IDs that belong to this bundle.
    bundle_source_ids = [sid for sid, b in src_to_bundle.items() if b == bundle]
    if not bundle_source_ids:
        return [], {}

    articles_res = await db.execute(
        select(Article).where(
            Article.published_at >= window_start,
            Article.published_at < window_end,
            Article.source_id.in_(bundle_source_ids),
        )
    )
    articles = list(articles_res.scalars().all())
    if not articles:
        return [], {}

    article_ids = [a.id for a in articles]
    bs_res = await db.execute(
        select(BiasScore).where(BiasScore.article_id.in_(article_ids))
    )
    # One article can have multiple BiasScores (e.g. llm_initial + llm_refined).
    # Prefer reasoning_fa-populated rows, then most recent.
    bs_by_article: dict[str, BiasScore] = {}
    for bs in bs_res.scalars().all():
        key = str(bs.article_id)
        existing = bs_by_article.get(key)
        if existing is None:
            bs_by_article[key] = bs
        elif existing.reasoning_fa is None and bs.reasoning_fa is not None:
            bs_by_article[key] = bs
    return articles, bs_by_article


# ─── Step 3: deterministic pre-aggregation ───────────────────────────
def _aggregate(
    bundle: NarrativeGroup,
    window_start: datetime,
    window_end: datetime,
    articles: list[Article],
    bs_by_article: dict[str, BiasScore],
) -> BundleAggregate:
    agg = BundleAggregate(
        bundle=bundle,
        window_start=window_start,
        window_end=window_end,
        article_count=len(articles),
        source_count=len({str(a.source_id) for a in articles if a.source_id}),
    )
    if not articles:
        return agg

    agg.article_to_source = {str(a.id): str(a.source_id) for a in articles if a.source_id}

    # Framing-label frequency from BiasScore.framing_labels (JSONB list of strings).
    framing_counter: Counter[str] = Counter()
    entity_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    political_vals: list[float] = []
    tone_vals: list[float] = []
    emotional_vals: list[float] = []
    with_reasoning: list[tuple[str, str]] = []  # (article_id, reasoning_fa)

    for a in articles:
        # Article.keywords (JSONB list) → topic-frequency proxy.
        kws = a.keywords or []
        if isinstance(kws, list):
            for kw in kws:
                if isinstance(kw, str) and kw.strip():
                    topic_counter[kw.strip().lower()] += 1
        # Article.named_entities (JSONB list of dicts or strings).
        ents = a.named_entities or []
        if isinstance(ents, list):
            for e in ents:
                label = None
                if isinstance(e, str):
                    label = e.strip()
                elif isinstance(e, dict):
                    label = (e.get("name") or e.get("text") or e.get("entity") or "").strip()
                if label:
                    entity_counter[label] += 1

        bs = bs_by_article.get(str(a.id))
        if bs is None:
            continue
        if isinstance(bs.framing_labels, list):
            for fl in bs.framing_labels:
                if isinstance(fl, str) and fl.strip():
                    framing_counter[fl.strip()] += 1
        if bs.political_alignment is not None:
            political_vals.append(float(bs.political_alignment))
        if bs.tone_score is not None:
            tone_vals.append(float(bs.tone_score))
        if bs.emotional_language_score is not None:
            emotional_vals.append(float(bs.emotional_language_score))
        if bs.reasoning_fa:
            with_reasoning.append((str(a.id), bs.reasoning_fa))

    agg.bias_coverage_pct = (
        100.0 * len(with_reasoning) / len(articles) if articles else 0.0
    )

    agg.framing_top = framing_counter.most_common(TOP_FRAMINGS)
    agg.entity_top = entity_counter.most_common(TOP_ENTITIES)
    agg.topic_top = topic_counter.most_common(TOP_TOPICS)

    def _avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    agg.tone_summary = {
        "political_alignment_mean": round(_avg(political_vals), 3),
        "tone_mean": round(_avg(tone_vals), 3),
        "emotional_mean": round(_avg(emotional_vals), 3),
        "n_scored": len(political_vals),
    }

    # Deterministic sample of bias narratives — seed by bundle+window so
    # re-runs return the same selection. Prefer diverse sources: round-
    # robin across sources, take one per source until we hit the cap.
    if with_reasoning:
        rng = random.Random(f"{bundle}:{window_start.isoformat()}")
        by_source: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for aid, reasoning in with_reasoning:
            src = agg.article_to_source.get(aid, "unknown")
            by_source[src].append((aid, reasoning))
        # Shuffle each bucket deterministically, then round-robin.
        for src in list(by_source.keys()):
            rng.shuffle(by_source[src])
        picked: list[dict[str, Any]] = []
        sources_cycle = sorted(by_source.keys())
        rng.shuffle(sources_cycle)
        while sources_cycle and len(picked) < SAMPLE_BIAS_NARRATIVES:
            next_sources = []
            for src in sources_cycle:
                if not by_source[src]:
                    continue
                aid, reasoning = by_source[src].pop()
                # Trim extremely long snippets to keep the prompt compact.
                trimmed = reasoning.strip()
                if len(trimmed) > 700:
                    trimmed = trimmed[:700].rsplit(" ", 1)[0] + "…"
                picked.append({"article_id": aid, "snippet": trimmed})
                if len(picked) >= SAMPLE_BIAS_NARRATIVES:
                    break
                next_sources.append(src)
            if not next_sources:
                break
            sources_cycle = next_sources
        agg.bias_samples = picked

    return agg


# ─── Step 4: cross-bundle absence detection ──────────────────────────
def _detect_absences(aggregates: dict[NarrativeGroup, BundleAggregate]) -> None:
    """Mutate each aggregate to populate `absences`."""
    # Per-bundle → set of topics (lowercased keyword strings).
    per_bundle_topics: dict[NarrativeGroup, dict[str, int]] = {
        g: dict(aggregates[g].topic_top) for g in NARRATIVE_GROUPS_ORDER
        if g in aggregates
    }

    # Topic → list of (bundle, count) for bundles where count ≥ threshold.
    topic_support: dict[str, list[tuple[NarrativeGroup, int]]] = defaultdict(list)
    for g, topic_counts in per_bundle_topics.items():
        for topic, count in topic_counts.items():
            if count >= ABSENCE_OTHER_BUNDLES_MIN_COUNT:
                topic_support[topic].append((g, count))

    for g in per_bundle_topics:
        this_topics = per_bundle_topics[g]
        absences: list[str] = []
        for topic, supporters in topic_support.items():
            other_supporters = [s for s in supporters if s[0] != g]
            if (
                len(other_supporters) >= ABSENCE_OTHER_BUNDLES_COVERING
                and this_topics.get(topic, 0) == 0
            ):
                absences.append(topic)
        # Cap to a handful of highest-supported absences so the prompt stays compact.
        absences.sort(
            key=lambda t: -sum(c for _, c in topic_support.get(t, [])),
        )
        aggregates[g].absences = absences[:8]


# ─── Step 5: synthesis prompt + LLM call ─────────────────────────────
_WORLDVIEW_PROMPT_SYSTEM = """\
You are a media-analysis assistant for Doornegar, a Persian-language \
media-transparency platform. You are writing a WORLDVIEW CARD that \
describes what a specific bundle of Iranian news outlets TOLD THEIR \
READERS over a 7-day window. You are NOT describing what readers believe, \
what any demographic group believes, or what "conservatives" / \
"reformists" / "diaspora" as people think — you are describing the \
information environment these OUTLETS constructed. This distinction is \
load-bearing: the card must never read as a stereotype of a group of \
people.

Output strict JSON only. No markdown fences, no prose before or after.

Write every string field in natural Persian (Farsi). Use neutral, \
analytical phrasing. Never use pejoratives for either side. Prefer \
قلب passive/descriptive voice ("این رسانه‌ها … را برجسته کردند") over \
active ascription ("این گروه باور دارد").

Every entry in `core_beliefs`, `emphasized`, and `predictions_primed` \
MUST include:
  - article_count (integer ≥ 3)
  - example_article_ids (list of 2-5 ids, drawn from the input data)
The caller will drop any entry that doesn't meet the floor.

Return ONLY this JSON shape:
{
  "core_beliefs": [
    {"text": "…", "article_count": N, "example_article_ids": ["uuid", ...]}
  ],
  "emphasized": [
    {"topic": "…", "note": "…", "article_count": N, "example_article_ids": ["uuid", ...]}
  ],
  "absent": [
    {"topic": "…", "note": "…"}
  ],
  "tone_profile": {
    "dominant": "…",
    "alt": "…",
    "description": "یک جمله درباره لحن مسلط این هفته"
  },
  "predictions_primed": [
    {"text": "…", "article_count": N, "example_article_ids": ["uuid", ...]}
  ]
}

Lists may have up to 5 items. Prefer depth over breadth — 3 strong \
entries beat 5 weak ones.
"""


_BUNDLE_LABEL_FA = {
    "principlist": "اصول‌گرا (درون مرز)",
    "reformist": "اصلاح‌طلب/مستقل (درون مرز)",
    "moderate_diaspora": "میانه‌روی برون‌مرز",
    "radical_diaspora": "مخالف رادیکال برون‌مرز",
}


def _build_prompt(agg: BundleAggregate) -> str:
    payload = {
        "bundle": agg.bundle,
        "bundle_label_fa": _BUNDLE_LABEL_FA[agg.bundle],
        "window_start": agg.window_start.date().isoformat(),
        "window_end": agg.window_end.date().isoformat(),
        "article_count": agg.article_count,
        "source_count": agg.source_count,
        "tone_summary": agg.tone_summary,
        "framing_top": [{"label": l, "count": c} for l, c in agg.framing_top],
        "entity_top": [{"name": n, "count": c} for n, c in agg.entity_top],
        "topic_top": [{"topic": t, "count": c} for t, c in agg.topic_top],
        "bias_samples": agg.bias_samples,
        "absences_from_other_bundles": agg.absences,
    }
    return (
        "Data for this bundle's week (aggregated, no article full text):\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\nReturn the JSON card now."
    )


async def _call_claude(prompt: str, system: str, bundle: str) -> tuple[str, dict]:
    """Send one synthesis call; log usage under purpose='worldview_digest'.

    Returns (text, usage_dict). Raises on transport / API failure — the
    caller catches per-bundle so one failure doesn't take down the
    whole weekly run.
    """
    import anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured for worldview synthesis")

    model = "claude-haiku-4-5-20251001"
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    msg = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text if msg.content else ""
    usage = {
        "input_tokens": getattr(msg.usage, "input_tokens", 0),
        "output_tokens": getattr(msg.usage, "output_tokens", 0),
    }
    # Cost tagged by purpose so /dashboard/cost can isolate worldview spend.
    await log_llm_usage(
        model=model,
        purpose="worldview_digest",
        usage=usage,
        meta={"bundle": bundle},
    )
    return text, usage


def _parse_json(text: str) -> dict | None:
    s = text.strip()
    if "```json" in s:
        s = s.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in s:
        s = s.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(s)
    except Exception as e:
        logger.warning(f"worldview_digest: JSON parse failed: {e} | text[:200]={text[:200]!r}")
        return None


def _validate_and_trim(
    parsed: dict,
    agg: BundleAggregate,
) -> tuple[dict, dict]:
    """Apply the grounding floor. Returns (synthesis_fa, evidence_fa).

    evidence_fa maps belief_key → [article_id, ...] for every surviving
    entry. Belief keys are stable: "core_beliefs:0", "emphasized:2", etc.
    """
    evidence: dict[str, list[str]] = {}
    synthesis: dict[str, Any] = {}

    def _check_ground(entry: dict, kind: str, idx: int) -> dict | None:
        count = int(entry.get("article_count", 0) or 0)
        ids_raw = entry.get("example_article_ids") or []
        ids = [str(x) for x in ids_raw if x]
        # Only keep ids that actually appear in the bundle's input data.
        valid_ids = [x for x in ids if x in agg.article_to_source]
        distinct_sources = {agg.article_to_source[x] for x in valid_ids}
        if count < MIN_ARTICLES_PER_BELIEF:
            return None
        if len(valid_ids) == 0 or len(distinct_sources) < MIN_SOURCES_PER_BELIEF:
            return None
        entry = dict(entry)
        entry["example_article_ids"] = valid_ids[:5]
        entry["source_count"] = len(distinct_sources)
        evidence[f"{kind}:{idx}"] = valid_ids[:5]
        return entry

    for kind in ("core_beliefs", "emphasized", "predictions_primed"):
        items = parsed.get(kind) or []
        kept = []
        for i, entry in enumerate(items):
            if not isinstance(entry, dict):
                continue
            checked = _check_ground(entry, kind, i)
            if checked:
                kept.append(checked)
        synthesis[kind] = kept[:5]

    # Absences don't need the grounding floor — they're already gated by
    # the cross-bundle "≥2 other bundles covered this" rule.
    absent = parsed.get("absent") or []
    synthesis["absent"] = [a for a in absent if isinstance(a, dict)][:5]

    tone = parsed.get("tone_profile") or {}
    if isinstance(tone, dict):
        synthesis["tone_profile"] = {
            "dominant": str(tone.get("dominant") or "").strip(),
            "alt": str(tone.get("alt") or "").strip(),
            "description": str(tone.get("description") or "").strip(),
        }
    else:
        synthesis["tone_profile"] = {"dominant": "", "alt": "", "description": ""}

    return synthesis, evidence


# ─── Step 6: DB write ────────────────────────────────────────────────
async def _upsert_digest(
    db: AsyncSession,
    bundle: NarrativeGroup,
    window_start: date,
    window_end: date,
    status: str,
    agg: BundleAggregate,
    synthesis: dict | None,
    evidence: dict | None,
    model_used: str | None,
    token_cost_usd: float,
) -> None:
    stmt = pg_insert(WorldviewDigest).values(
        bundle=bundle,
        window_start=window_start,
        window_end=window_end,
        status=status,
        synthesis_fa=synthesis,
        evidence_fa=evidence,
        article_count=agg.article_count,
        source_count=agg.source_count,
        coverage_pct=agg.bias_coverage_pct,
        model_used=model_used,
        token_cost_usd=token_cost_usd,
    )
    # (bundle, window_start) is unique — on conflict, refresh the row.
    stmt = stmt.on_conflict_do_update(
        index_elements=["bundle", "window_start"],
        set_={
            "window_end": stmt.excluded.window_end,
            "status": stmt.excluded.status,
            "synthesis_fa": stmt.excluded.synthesis_fa,
            "evidence_fa": stmt.excluded.evidence_fa,
            "article_count": stmt.excluded.article_count,
            "source_count": stmt.excluded.source_count,
            "coverage_pct": stmt.excluded.coverage_pct,
            "model_used": stmt.excluded.model_used,
            "token_cost_usd": stmt.excluded.token_cost_usd,
            "generated_at": func.now(),
        },
    )
    await db.execute(stmt)


# ─── Public orchestrator ─────────────────────────────────────────────
def _default_window(anchor: date | None) -> tuple[datetime, datetime]:
    """Return (start, end) — the previous ISO week ending on anchor's Monday.

    Example: if today is Monday 2026-04-27, window is 2026-04-20..2026-04-27.
    Weekly cron runs on Monday, so this covers the week that just ended.
    """
    ref = anchor or datetime.now(tz=timezone.utc).date()
    this_monday = ref - timedelta(days=ref.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
    return start_dt, end_dt


async def generate_worldview_digests(
    db: AsyncSession,
    anchor: date | None = None,
) -> dict[str, Any]:
    """Run one weekly pass. Returns a stats dict for the maintenance log."""
    window_start, window_end = _default_window(anchor)
    logger.info(
        f"worldview_digest: window {window_start.date()} .. {window_end.date()} (UTC)"
    )

    # Build source→bundle once.
    src_res = await db.execute(select(Source).where(Source.is_active.is_(True)))
    sources = src_res.scalars().all()
    src_to_bundle = {str(s.id): narrative_group(s) for s in sources}

    # Pre-aggregate every bundle (deterministic; no LLM yet).
    aggregates: dict[NarrativeGroup, BundleAggregate] = {}
    for bundle in NARRATIVE_GROUPS_ORDER:
        articles, bs_map = await _gather_bundle_data(
            db, bundle, window_start, window_end, src_to_bundle,
        )
        aggregates[bundle] = _aggregate(
            bundle, window_start, window_end, articles, bs_map,
        )
    _detect_absences(aggregates)

    # Synthesize each bundle that passes preconditions.
    stats: dict[str, Any] = {
        "window_start": window_start.date().isoformat(),
        "window_end": window_end.date().isoformat(),
        "per_bundle": {},
    }
    total_in = 0
    total_out = 0
    for bundle in NARRATIVE_GROUPS_ORDER:
        agg = aggregates[bundle]
        ok, failures = agg.passes_preconditions()
        if not ok:
            logger.warning(f"worldview_digest/{bundle}: insufficient — {failures}")
            await _upsert_digest(
                db, bundle, window_start.date(), window_end.date(),
                status="insufficient",
                agg=agg, synthesis=None, evidence=None,
                model_used=None, token_cost_usd=0.0,
            )
            stats["per_bundle"][bundle] = {
                "status": "insufficient",
                "failures": failures,
                "article_count": agg.article_count,
                "source_count": agg.source_count,
            }
            continue

        # Synthesis call. One bundle failing must not take down the rest.
        try:
            prompt = _build_prompt(agg)
            text, usage = await _call_claude(
                prompt=prompt,
                system=_WORLDVIEW_PROMPT_SYSTEM,
                bundle=bundle,
            )
            parsed = _parse_json(text)
            if parsed is None:
                raise RuntimeError("LLM returned non-JSON output")
            synthesis, evidence = _validate_and_trim(parsed, agg)
            # Rough cost estimate mirrored on the row for UI convenience.
            # Authoritative ledger is llm_usage_logs.
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            total_in += in_tok
            total_out += out_tok
            cost_usd = (in_tok * 0.80 + out_tok * 4.00) / 1_000_000
            await _upsert_digest(
                db, bundle, window_start.date(), window_end.date(),
                status="ok",
                agg=agg, synthesis=synthesis, evidence=evidence,
                model_used="claude-haiku-4-5-20251001",
                token_cost_usd=cost_usd,
            )
            stats["per_bundle"][bundle] = {
                "status": "ok",
                "article_count": agg.article_count,
                "source_count": agg.source_count,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(cost_usd, 5),
                "beliefs_kept": len(synthesis.get("core_beliefs", [])),
                "emphasized_kept": len(synthesis.get("emphasized", [])),
                "predictions_kept": len(synthesis.get("predictions_primed", [])),
            }
        except Exception as e:
            logger.exception(f"worldview_digest/{bundle}: synthesis failed: {e}")
            stats["per_bundle"][bundle] = {"status": "error", "error": str(e)}

    await db.commit()
    stats["total_input_tokens"] = total_in
    stats["total_output_tokens"] = total_out
    stats["total_cost_usd"] = round(
        (total_in * 0.80 + total_out * 4.00) / 1_000_000, 5
    )
    return stats
