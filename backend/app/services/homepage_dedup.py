"""Homepage same-event de-duplication.

Parham 2026-06-16: a fast-breaking story (the Iran-US deal) keeps
fragmenting into multiple homepage cards because the clustering engine is
built for tight, short-lived clusters — every cron, fresh coverage forms a
new tight cluster instead of joining the big, diffuse pinned hero (whose
centroid no longer cosine-matches any single fresh article), and the
coherence audit then freezes the hero for that very breadth. Forcing one
mega-hero fights the architecture; the chosen fix (over hand-merging every
cron) is a PRESENTATION-layer dedup: detect stories that are clearly the
SAME event and keep only ONE on the homepage, auto-hiding the rest.

This module is the pure, side-effect-free core (no DB) so the matching +
selection logic is unit-testable. `auto_maintenance.step_dedupe_homepage_events`
loads the rows, calls `plan_dedup`, and applies the hides. De-dup is
PIN-ANCHORED (see `plan_dedup`): only fragments of an explicitly-pinned story
are collapsed — a transitive same-event grouping was tried first and
catastrophically over-merged the dense war/deal topic space (dry-run
2026-06-16), so it was replaced.

## Why two signals AND'd together
Calibrated 2026-06-16 against the live deal clusters + distinct contrast
stories (railway DB read):

    pair                         centroid_cos   title_jaccard
    hero vs deal:key-clauses        0.752          0.267
    hero vs deal:2wk-ceasefire      0.717          0.158
    hero vs deal:60-day-talks       0.670          0.167
    hero vs US-strikes (war)        0.585          0.200
    hero vs Lebanon/bias/distinct   0.50-0.60      0.00-0.067
    hero vs ONE anomalous distinct  1.000 (!)      0.067

Neither signal separates alone: same-event cosine (0.67-0.75) overlaps
distinct (0.50-0.60), and "US strikes...Trump announces deal" has a high
title overlap (0.20) despite being a distinct war-phase story. But the
AND is clean: same-event passes BOTH; US-strikes fails cosine; every
distinct story (including the cosine=1.0 anomaly) fails Jaccard. We bias
to PRECISION — a missed dup is a cosmetic repeat; a false merge hides a
genuinely distinct story.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Thresholds — calibrated 2026-06-16 (see module docstring). Tuned for
# precision: require BOTH a high centroid cosine AND a real title overlap.
DEDUP_COSINE_MIN = 0.64
DEDUP_JACCARD_MIN = 0.12
DEDUP_MIN_SHARED_TOKENS = 2

# Pin floor mirrors clustering._MERGE_PIN_PRIORITY_FLOOR — a pinned story
# is the operator's explicit canonical pick and is NEVER hidden by dedup.
PIN_FLOOR = 40

_PUNCT = re.compile(r"[؛،:.!؟…\-«»\"'‌/()]")
_WS = re.compile(r"\s+")
# Persian function words only. Country/actor names (ایران/آمریکا/…) are KEPT
# as content tokens on purpose: dropping them left some same-event deal
# stories sharing just one event word (توافق), which the min-shared guard
# would then reject (a missed dup = a repeated card). With them kept, real
# same-event stories share 3+ tokens; the cosine>=0.64 gate is what excludes
# the related-but-distinct "US strikes Iran...Trump announces deal" story
# (cosine 0.585), and min-shared>=2 excludes distinct stories that overlap on
# only a single generic token (e.g. a Lebanon story sharing just «ایران»).
_STOP = set(
    "و در به از با برای که را این یک تا بر های ها هم نیز یا اما بود شد است".split()
)

# Generic high-frequency tokens that appear across MANY distinct Iran stories
# (actors, places, war-casualty vocabulary). Sharing only these does NOT mean
# two stories are the same event — e.g. a peace-deal hero and a missile-strike
# story both contain {ایران, آمریکا}. Same-event detection requires at least
# one shared token OUTSIDE this set (an event-specific word like توافق, تفاهم,
# امضا, سوئیس, آتش‌بس, لبنان…). Calibrated against the 2026-06-16 dry-run where
# war-strike stories were wrongly matched to the deal hero on {ایران, آمریکا}.
GENERIC_TOKENS = set(
    # actors / places
    "ایران آمریکا اسرائیل ترامپ تهران واشنگتن جمهوری اسلامی کشور منطقه خاورمیانه "
    # war / casualty vocabulary
    "حمله حملات جنگ موشک موشکی پهپاد نظامی هوایی کشته زخمی شهید مجروح نیرو نیروهای "
    # common news verbs / temporal / framing words that bridge unrelated stories
    "خبر گزارش اعلام تایید تأیید واکنش واکنش‌ها پاسخ ادعا گفت پایان آغاز ادامه تمدید "
    "جدید اخیر روز ساعت درباره مورد جریان تنش تنش‌ها".split()
)


def normalize_title_tokens(title: str | None) -> set[str]:
    """Lowercase-ish normalize a Persian title to a set of content tokens.

    Unifies Arabic/Persian glyph variants (ي→ی, ك→ک), strips punctuation +
    ZWNJ, drops 1-char tokens and the stopword/generic-actor list.
    """
    s = (title or "").replace("ي", "ی").replace("ك", "ک")
    s = _PUNCT.sub(" ", s)
    return {
        t for t in _WS.sub(" ", s).strip().split()
        if len(t) > 1 and t not in _STOP
    }


def centroid_cosine(a, b) -> float | None:
    """Cosine of two embedding lists; None if either is missing/degenerate."""
    if not a or not b or len(a) != len(b):
        return None
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return None
    return dot / (math.sqrt(na) * math.sqrt(nb))


def token_jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class DedupRow:
    """Lightweight, DB-free view of a candidate story."""
    id: object
    title_fa: str | None
    centroid: list | None
    priority: int
    trending_score: float
    last_updated_at: object  # datetime | None — used only for sort tiebreak
    article_count: int

    @property
    def tokens(self) -> set[str]:
        return normalize_title_tokens(self.title_fa)

    @property
    def is_pinned(self) -> bool:
        return (self.priority or 0) >= PIN_FLOOR


def _same_event(a: DedupRow, b: DedupRow,
                *, cos_min: float, jac_min: float, min_shared: int) -> bool:
    shared = a.tokens & b.tokens
    if len(shared) < min_shared:
        return False
    # Must share at least one EVENT-SPECIFIC token — generic actor/place/war
    # words alone (e.g. {ایران, آمریکا}) are not evidence of the same event.
    if not (shared - GENERIC_TOKENS):
        return False
    if token_jaccard(a.tokens, b.tokens) < jac_min:
        return False
    cos = centroid_cosine(a.centroid, b.centroid)
    if cos is None or cos < cos_min:
        return False
    return True


def find_fragment_pairs(
    rows: list[DedupRow],
    *,
    cos_min: float = DEDUP_COSINE_MIN,
    jac_min: float = DEDUP_JACCARD_MIN,
    min_shared: int = DEDUP_MIN_SHARED_TOKENS,
) -> list[tuple[DedupRow, DedupRow]]:
    """Read-only, pairwise same-event scan across ALL rows — no pin required.

    `plan_dedup` only collapses fragments of an explicitly-pinned story,
    because it HIDES stories (an irreversible homepage action) and a 2026-06-16
    dry-run showed transitive same-event grouping catastrophically over-merges
    the dense war/deal topic space. That pin-anchoring means a fast-breaking
    event that fragments WITHOUT anyone pinning a canonical story is invisible
    to it — exactly what happened 2026-07-03, when the Khamenei funeral split
    across 4 un-pinned story IDs and only a manual Niloofar audit caught it.

    This function takes no action and stores nothing; it just lists candidate
    pairs for a human/Niloofar merge_stories pass (see the
    sibling_cluster_fragmentation canary in admin.py). Because nothing is
    auto-hidden or auto-grouped, it doesn't inherit the transitive-closure
    over-merge risk — a false-positive pair here just means someone glances at
    two titles and decides they're not actually the same event, same as any
    other WARN canary (homepage_grabbag, midsize_grabbag_risk). Reuses the
    identical calibrated `_same_event` test so it inherits the same precision
    bias (cosine >= 0.64 AND title-jaccard >= 0.12 AND a shared event-specific
    token, not just generic actor/place words).
    """
    pairs: list[tuple[DedupRow, DedupRow]] = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            if _same_event(a, b, cos_min=cos_min, jac_min=jac_min, min_shared=min_shared):
                pairs.append((a, b))
    return pairs


def plan_dedup(
    rows: list[DedupRow],
    *,
    cos_min: float = DEDUP_COSINE_MIN,
    jac_min: float = DEDUP_JACCARD_MIN,
    min_shared: int = DEDUP_MIN_SHARED_TOKENS,
) -> list[tuple[DedupRow, list[DedupRow]]]:
    """PIN-ANCHORED de-dup: hide non-pinned stories that are DIRECTLY the
    same event as a manually-pinned story. Returns [(pin, [rows_to_hide])].

    Why pin-anchored + direct-only (NOT transitive groups): a 2026-06-16
    dry-run on the live homepage showed that a transitive same-event grouping
    catastrophically over-merges — the entire Iran-US war/deal complex
    (Lebanon strikes, IRGC-on-US-bases, missile strikes on Israel, the peace
    deal) chained into ONE 34-story component because adjacent war-phase
    stories share generic tokens (ایران/آمریکا/حملات) and high cosine, and a
    separate trio of distinct executions merged on «اعدام». Pairwise
    precision does not survive transitive closure in a dense topic space.

    So we only collapse FRAGMENTS OF AN EXPLICITLY-PINNED STORY:
      • The representative is always the pin (the operator's canonical pick).
      • We hide only NON-pinned stories, and only those DIRECTLY `_same_event`
        as the pin (no chaining through intermediaries).
      • The cosine>=0.64 gate excludes the related-but-distinct war-strike
        stories from the deal hero (they sit at ~0.585 to it).
    When nothing is pinned, nothing is de-duped — safer than auto-merging
    un-pinned stories whose canonical choice the operator hasn't signalled.
    """
    pins = sorted(
        (r for r in rows if r.is_pinned),
        key=lambda r: ((r.priority or 0), float(r.trending_score or 0.0)),
        reverse=True,
    )
    non_pins = [r for r in rows if not r.is_pinned]
    used: set = set()
    plans: list[tuple[DedupRow, list[DedupRow]]] = []
    for pin in pins:
        dupes = [
            s for s in non_pins
            if s.id not in used
            and _same_event(pin, s, cos_min=cos_min, jac_min=jac_min, min_shared=min_shared)
        ]
        if dupes:
            for d in dupes:
                used.add(d.id)
            plans.append((pin, dupes))
    return plans
