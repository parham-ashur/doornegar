"""Phase G.3.2 (Parham 2026-05-10) — denormalized homepage aggregates.

Pre-computes the per-story image_url + coverage percentages + narrative
groups blob so /trending and /blindspots can render without
selectinload(Story.articles). The blob lives in `Story.homepage_aggregates`
and is refreshed once per cron via `step_recompute_homepage_aggregates`.

The same logic computed at read-time inside `_story_brief_with_extras`
(api/v1/stories.py) remains as a fallback for stories whose blob is
null — newly-created stories that have not yet been touched by cron,
or first deploy after the column lands.

Shape of `Story.homepage_aggregates`:
    {
      "image_url": str | None,
      "has_real_image": bool,
      "state_pct": int,
      "diaspora_pct": int,
      "independent_pct": int,
      "narrative_groups": {
        "principlist": int, "reformist": int,
        "moderate_diaspora": int, "radical_diaspora": int,
      },
      "inside_border_pct": int,
      "outside_border_pct": int,
      "computed_at": ISO8601,
    }

The compute function is pure and synchronous so the cron step + the
read-time fallback share one implementation. Drift between the read
helper and this module would silently shift homepage percentages —
the tripwire `TestHomepageAggregatesParity` calls both on a synthetic
story and asserts the blob matches.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.article import Article
    from app.models.source import Source
    from app.models.story import Story


# Mirrors `_is_bad_image` in api/v1/stories.py. Inlined to keep the
# cron step from importing the API module (circular-import risk).
_BAD_IMAGE_PATTERNS = (
    "pixel", "1x1", "blank.", "spacer.", "transparent.",
    "placeholder", "default.jpg", "default.png", "no-image",
    "logo-", "/logo.", "/icon.", "favicon",
    "apple-touch-icon",
    "google.com/s2/favicons",
    ".svg", ".ico",
    "telesco.pe", "cdn.telegram",
    "ico-192x192", "ico-512x512", "webapp/ico-", "manifest-icon",
)
_IRANINTL_TRANSFORM_RE = re.compile(
    r"-\d+x\d+\.(jpg|jpeg|png|webp)(\?|$)"
)


def _is_bad_image(url: str | None) -> bool:
    if not url or len(url) < 10:
        return True
    u = url.lower()
    if any(p in u for p in _BAD_IMAGE_PATTERNS):
        return True
    # Iran International's Sanity CDN returns 400 on bare hash paths.
    if "i.iranintl.com/" in u and not _IRANINTL_TRANSFORM_RE.search(u):
        return True
    return False


def _title_words(s: str | None) -> set[str]:
    if not s:
        return set()
    return {w for w in s.split() if len(w) >= 3}


def _pick_image(
    story: "Story", articles: list["Article"]
) -> tuple[str | None, bool]:
    """Return (image_url, has_real_image). Mirrors the read-time logic
    in api/v1/stories.py::_story_brief_with_extras image selection,
    minus the manual_image_url override (which is read live from
    story.summary_en at request time and overrides the blob).
    """
    from app.config import settings

    story_words = _title_words(story.title_fa or story.title_en)

    candidates = [
        a for a in articles
        if a.image_url and not _is_bad_image(a.image_url)
    ]
    if candidates:
        r2_prefix = settings.r2_public_url or ""

        def _score(a):
            art_words = _title_words(
                a.title_fa or a.title_original or a.title_en
            )
            overlap = len(story_words & art_words)
            is_stable = a.image_url.startswith("/images/") or (
                bool(r2_prefix) and a.image_url.startswith(r2_prefix)
            )
            return (1 if is_stable else 0, overlap, len(a.image_url))

        best = max(candidates, key=_score)
        return best.image_url, True

    # Logo fallback — most-frequent active source's logo.
    source_counts: dict[str, int] = {}
    for a in articles:
        if (
            a.source
            and a.source.logo_url
            and not _is_bad_image(a.source.logo_url)
            and getattr(a.source, "is_active", True)
        ):
            source_counts[a.source.slug] = source_counts.get(a.source.slug, 0) + 1
    if source_counts:
        top_slug = max(source_counts, key=source_counts.get)  # type: ignore[arg-type]
        for a in articles:
            if a.source and a.source.slug == top_slug and a.source.logo_url:
                return a.source.logo_url, False

    return None, False


def compute_homepage_aggregates(
    story: "Story",
    articles: list["Article"],
    source_count_rows: list[tuple["Source", int]],
) -> dict:
    """Pure function — given a story + its articles + per-source
    article-count rows, return the homepage_aggregates blob.

    `articles` is the list used for image picking (latest N is fine).
    `source_count_rows` covers the FULL article set — the percentages
    must reflect every outlet that ever cited this story, not just
    the latest N. Both the cron step and the read-time fallback pass
    these explicitly.
    """
    from app.services.narrative_groups import (
        NARRATIVE_GROUPS_ORDER,
        counts_to_percentages,
        narrative_group,
    )

    image_url, has_real_image = _pick_image(story, articles)

    # Per-source dedup (one vote per outlet, not per article).
    state = 0
    diaspora = 0
    independent = 0
    group_counts: dict[str, int] = {g: 0 for g in NARRATIVE_GROUPS_ORDER}
    sources_seen: dict[str, "Source"] = {}
    for src, _cnt in source_count_rows:
        if not src or not getattr(src, "slug", None):
            continue
        if src.slug in sources_seen:
            continue
        sources_seen[src.slug] = src
        align = getattr(src, "state_alignment", None)
        if align in ("state", "semi_state"):
            state += 1
        elif align == "diaspora":
            diaspora += 1
        else:
            independent += 1
        group_counts[narrative_group(src)] += 1

    total_sources = len(sources_seen)
    if total_sources > 0:
        state_pct = round(state * 100 / total_sources)
        diaspora_pct = round(diaspora * 100 / total_sources)
        independent_pct = round(independent * 100 / total_sources)
        narrative_pct = counts_to_percentages(group_counts)
        inside = narrative_pct["principlist"] + narrative_pct["reformist"]
        outside = (
            narrative_pct["moderate_diaspora"]
            + narrative_pct["radical_diaspora"]
        )
    else:
        state_pct = 0
        diaspora_pct = 0
        independent_pct = 0
        narrative_pct = {g: 0 for g in NARRATIVE_GROUPS_ORDER}
        inside = 0
        outside = 0

    return {
        "image_url": image_url,
        "has_real_image": has_real_image,
        "state_pct": state_pct,
        "diaspora_pct": diaspora_pct,
        "independent_pct": independent_pct,
        "narrative_groups": narrative_pct,
        "inside_border_pct": inside,
        "outside_border_pct": outside,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


async def recompute_story_aggregates(db, story_id) -> bool:
    """Recompute + persist one story's homepage_aggregates blob NOW.

    The cron's `step_recompute_homepage_aggregates` (FULL_PIPELINE step 31)
    runs BEFORE the article-removing steps `quality_postprocess` (50) and
    leaves the blob stale when those steps drop an article — so a story that
    loses its only inside-border article still served state_pct=17 and a
    «پوشش درون‌مرزی آغاز شد» badge while actually being 0% inside (Parham
    2026-06-03, story 538d848c in نگاه یک‌جانبه). Call this for any story you
    just changed the article set of, so the percentages + signal downstream
    reflect reality. Returns False if the story has no articles left.
    """
    from sqlalchemy import func as _f, select as _sel
    from sqlalchemy.orm import defer as _defer, selectinload as _sel_in
    from app.models.article import Article as _Art
    from app.models.source import Source as _Src
    from app.models.story import Story as _Sty

    story = (await db.execute(
        _sel(_Sty).where(_Sty.id == story_id)
    )).scalar_one_or_none()
    if not story:
        return False

    articles = list((await db.execute(
        _sel(_Art)
        .options(
            _defer(_Art.embedding), _defer(_Art.content_text),
            _defer(_Art.keywords), _defer(_Art.named_entities),
            _sel_in(_Art.source),
        )
        .where(_Art.story_id == story_id)
        .order_by(_Art.published_at.desc().nullslast(), _Art.ingested_at.desc())
        .limit(50)
    )).scalars().all())
    if not articles:
        return False

    source_count_rows = list((await db.execute(
        _sel(_Src, _f.count(_Art.id))
        .join(_Art, _Art.source_id == _Src.id)
        .where(_Art.story_id == story_id)
        .group_by(_Src.id)
    )).all())

    blob = compute_homepage_aggregates(story, articles, source_count_rows)
    await db.execute(
        _Sty.__table__.update().where(_Sty.id == story_id).values(homepage_aggregates=blob)
    )
    return True
