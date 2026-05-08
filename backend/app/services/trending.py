"""Single source of truth for `Story.trending_score`.

Established cycle-4 (2026-05-08). Pre-this module, two divergent
formulas wrote to the same column:

- `clustering._compute_trending_score`: `article_count × 0.5^(hours_ago/48)`
  (2-day half-life, anchored on `first_published_at`).
- `auto_maintenance.step_recalculate_trending`: `article_count × 0.85^days_ago`
  (~4-day half-life, anchored on `frozen_at` ?? `last_updated_at` ?? `first_published_at`).

For the same story (10 articles, 7 days old, last_updated_at = 7d ago):
the formulas produced 0.88 vs 3.2 — a 3.6x divergence in the SAME column,
flipping homepage rank between cron passes vs interim writes.

This module picks ONE canonical formula and exposes it for both writers.

## The canonical formula

```
recency_anchor = frozen_at if story is frozen
                 else last_updated_at if not None
                 else first_published_at if not None
                 else (no anchor → recency = 0.05)
recency = max(0.005, 0.85^days_since_anchor)
plurality_zero = (source_count <= 1 and article_count >= 5)
score = 0.0 if plurality_zero else article_count * recency
```

## Why these design choices

- **Anchor on last_updated_at**, not first_published_at: a story that
  gained a fresh article on day 25 should NOT decay like a 25-day-old
  story. The editorial intent (per CLAUDE.md): "stories matter most
  for ~7 days, are dated after ~14, dead by 30."
- **frozen_at takes precedence**: per Parham 2026-05-03, freeze closes
  the chapter — a 75d-old frozen umbrella whose last_updated_at was
  just bumped (by recluster_orphans or any other touch) shouldn't
  outrank fresh sibling stories.
- **0.85^days half-life (~4.3 days)**: produces day-0=1.0, day-7=0.32,
  day-14=0.10, day-30=0.01. Combined with `archived_at` gating
  elsewhere, this naturally pushes old content off the homepage
  without explicit cutoffs in every consumer.
- **Single-source demotion**: a "story" with one source is a single
  outlet's bulletin dump, not pluralism. Visible stories always have
  `article_count >= 5`, so single-source means a large bulk-feed —
  zero its trending so it can't ride volume to the top.
"""

from datetime import datetime, timezone
from typing import Optional


def compute_trending_score(
    *,
    article_count: int,
    last_updated_at: Optional[datetime] = None,
    frozen_at: Optional[datetime] = None,
    first_published_at: Optional[datetime] = None,
    source_count: Optional[int] = None,
) -> float:
    """Canonical trending score. Matches step_recalculate_trending shape;
    `clustering._compute_trending_score` delegates here too.

    Returns 0.0 for single-source stories above the visibility cutoff
    (so they never top the homepage on volume alone).
    """
    # Plurality gate first — cheap and short-circuits the math.
    if source_count is not None and source_count <= 1 and article_count >= 5:
        return 0.0

    # Anchor selection: frozen_at wins (closes the chapter), then
    # last_updated_at (refreshed-recent stories behave like young ones),
    # then first_published_at as fallback.
    if frozen_at is not None:
        anchor = frozen_at
    elif last_updated_at is not None:
        anchor = last_updated_at
    elif first_published_at is not None:
        anchor = first_published_at
    else:
        # No anchor at all — tiny non-zero so the story still shows on
        # admin-facing /api/v1/stories listings but doesn't compete with
        # real homepage candidates.
        return article_count * 0.05

    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    days_ago = (datetime.now(timezone.utc) - anchor).total_seconds() / 86400.0
    days_ago = max(0.0, days_ago)
    recency = max(0.005, 0.85 ** days_ago)
    return article_count * recency
