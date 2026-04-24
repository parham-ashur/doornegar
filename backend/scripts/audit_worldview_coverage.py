"""Audit the four preconditions for a worldview digest run.

For each of the 4 bundles (principlist / reformist / moderate_diaspora /
radical_diaspora), report:

    articles        — count with published_at in [window_start, window_end)
    sources         — distinct sources that contributed
    bias_coverage%  — articles with a BiasScore.reasoning_fa populated

and pass/fail against:

    1. source_count     ≥ 3
    2. article_count    ≥ 20
    3. bias_coverage%   ≥ 75

Exit code: 0 if all four bundles pass, 1 otherwise. Output is
English-only (matches Parham's "dashboard chrome stays English" rule;
this is a diagnostics script, not user-facing).

Usage:
    python -m scripts.audit_worldview_coverage            # current week (Mon..Mon)
    python -m scripts.audit_worldview_coverage --last     # previous week
    python -m scripts.audit_worldview_coverage --since 7  # last 7 days rolling
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.article import Article
from app.models.bias_score import BiasScore
from app.models.source import Source
from app.services.narrative_groups import (
    NARRATIVE_GROUPS_ORDER,
    NarrativeGroup,
    narrative_group,
)


MIN_SOURCES = 3
MIN_ARTICLES = 20
MIN_BIAS_COVERAGE_PCT = 75


@dataclass
class BundleStats:
    bundle: NarrativeGroup
    article_count: int
    source_count: int
    bias_coverage_pct: float

    def preconditions(self) -> list[tuple[str, bool]]:
        return [
            (f"sources ≥ {MIN_SOURCES}", self.source_count >= MIN_SOURCES),
            (f"articles ≥ {MIN_ARTICLES}", self.article_count >= MIN_ARTICLES),
            (
                f"bias_coverage ≥ {MIN_BIAS_COVERAGE_PCT}%",
                self.bias_coverage_pct >= MIN_BIAS_COVERAGE_PCT,
            ),
        ]

    @property
    def passes(self) -> bool:
        return all(p for _, p in self.preconditions())


def _iso_week_monday(d: date) -> date:
    """Return the Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def _window_for(args: argparse.Namespace) -> tuple[datetime, datetime]:
    now = datetime.now(tz=timezone.utc)
    today = now.date()
    if args.since is not None:
        start = today - timedelta(days=int(args.since))
        end = today + timedelta(days=1)  # include today
    elif args.last:
        this_monday = _iso_week_monday(today)
        start = this_monday - timedelta(days=7)
        end = this_monday
    else:
        this_monday = _iso_week_monday(today)
        start = this_monday
        end = this_monday + timedelta(days=7)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
    return start_dt, end_dt


async def _bundle_of_source_map(db: AsyncSession) -> dict[str, NarrativeGroup]:
    """Return source_id (str) → bundle for every active source."""
    result = await db.execute(
        select(Source).where(Source.is_active.is_(True))
    )
    sources = result.scalars().all()
    return {str(s.id): narrative_group(s) for s in sources}


async def _compute_bundle_stats(
    db: AsyncSession, window_start: datetime, window_end: datetime
) -> dict[NarrativeGroup, BundleStats]:
    # Load source→bundle map once.
    src_to_bundle = await _bundle_of_source_map(db)
    if not src_to_bundle:
        return {g: BundleStats(g, 0, 0, 0.0) for g in NARRATIVE_GROUPS_ORDER}

    # Group-level aggregates are easier in python than SQL here because the
    # bundle classification isn't a column on Source — it's a derived value.
    # Weekly windows are small (thousands of articles), so one scan is fine.
    articles_result = await db.execute(
        select(Article.id, Article.source_id).where(
            Article.published_at >= window_start,
            Article.published_at < window_end,
            Article.source_id.is_not(None),
        )
    )
    rows = articles_result.all()

    # Articles-per-bundle + distinct-sources-per-bundle.
    per_bundle_articles: dict[NarrativeGroup, list[str]] = {
        g: [] for g in NARRATIVE_GROUPS_ORDER
    }
    per_bundle_sources: dict[NarrativeGroup, set[str]] = {
        g: set() for g in NARRATIVE_GROUPS_ORDER
    }
    for article_id, source_id in rows:
        bundle = src_to_bundle.get(str(source_id))
        if bundle is None:
            continue
        per_bundle_articles[bundle].append(str(article_id))
        per_bundle_sources[bundle].add(str(source_id))

    # Bias-analysis coverage: articles whose BiasScore.reasoning_fa is
    # populated count. One query per bundle keeps the SQL simple.
    stats: dict[NarrativeGroup, BundleStats] = {}
    for g in NARRATIVE_GROUPS_ORDER:
        articles = per_bundle_articles[g]
        article_count = len(articles)
        source_count = len(per_bundle_sources[g])
        if article_count == 0:
            stats[g] = BundleStats(g, 0, source_count, 0.0)
            continue
        # BiasScore.reasoning_fa is the strongest "analysis landed" signal;
        # framing_labels alone can be set by an interrupted run.
        covered = await db.scalar(
            select(func.count(distinct(BiasScore.article_id))).where(
                BiasScore.article_id.in_(articles),
                BiasScore.reasoning_fa.is_not(None),
            )
        )
        covered = int(covered or 0)
        coverage = (covered / article_count) * 100.0
        stats[g] = BundleStats(g, article_count, source_count, coverage)
    return stats


def _print_report(
    stats: dict[NarrativeGroup, BundleStats],
    window_start: datetime,
    window_end: datetime,
) -> bool:
    print(
        f"Window: {window_start.date().isoformat()} .. "
        f"{window_end.date().isoformat()} (UTC, end-exclusive)"
    )
    print()
    print(f"{'bundle':<20} {'articles':>8} {'sources':>8} {'bias%':>8}   verdict")
    print("-" * 70)
    all_pass = True
    for g in NARRATIVE_GROUPS_ORDER:
        s = stats[g]
        verdict = "PASS" if s.passes else "FAIL"
        if not s.passes:
            all_pass = False
        print(
            f"{s.bundle:<20} {s.article_count:>8d} {s.source_count:>8d} "
            f"{s.bias_coverage_pct:>7.1f}%   {verdict}"
        )
        if not s.passes:
            for name, ok in s.preconditions():
                mark = "ok " if ok else "FAIL"
                print(f"    {mark}  {name}")
    print()
    print(
        f"Preconditions: sources≥{MIN_SOURCES}, articles≥{MIN_ARTICLES}, "
        f"bias_coverage≥{MIN_BIAS_COVERAGE_PCT}%"
    )
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAIL — synthesis will be gated per-bundle'}")
    return all_pass


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--last", action="store_true", help="audit previous ISO week")
    parser.add_argument("--since", type=int, default=None, help="rolling last N days")
    args = parser.parse_args()

    window_start, window_end = _window_for(args)
    async with async_session() as db:
        stats = await _compute_bundle_stats(db, window_start, window_end)
    all_pass = _print_report(stats, window_start, window_end)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
