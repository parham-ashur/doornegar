"""Homepage coherence gate — detects and archives small incoherent clusters.

A 'grab-bag' forms when the cluster step lumps articles from different
domestic-news topics under one title because they happen to share generic
Iranian-news embedding proximity. This module scores each small active story
by how tightly its articles cluster around the story centroid; incoherent
ones are archived before LLM spend hits them.

Detection: mean cosine similarity of article embeddings to story centroid.
  coherent cluster   → articles all about the same event → sim ~ 0.65+
  grab-bag cluster   → articles span unrelated topics   → sim ~ 0.25-0.40

Observed grab-bag scores (2026-06-19/20):
  «فرهنگیان بازنشسته» (1/9 on-topic)   → estimated mean sim ≈ 0.30
  «محدودیت‌های اینترنتی» (1/5 on-topic) → estimated mean sim ≈ 0.28
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ── tunables ──────────────────────────────────────────────────────────────────
COHERENCE_MIN = 0.45     # mean article-to-centroid cosine; below = grab-bag
MIN_COVERAGE = 0.50      # skip if <50% of articles have embeddings (can't judge)
MIN_ARTICLE_COUNT = 5    # below this, too small to score reliably
MAX_ARTICLE_COUNT = 25   # above this, too risky to auto-archive (large=usually coherent)
MAX_AGE_HOURS = 48       # only gate stories created within last 48h (fresh clusters)
SAFETY_CAP = 5           # never archive more than this per run (drift backstop)
PIN_FLOOR = 1            # priority >= PIN_FLOOR = pinned → always exempt


@dataclass
class CandidateStory:
    story_id: str
    priority: int
    article_count: int
    centroid_embedding: list[float] | None
    article_embeddings: list[list[float] | None] = field(default_factory=list)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def score_coherence(story: CandidateStory) -> float | None:
    """Mean cosine similarity of article embeddings to story centroid.

    Returns None if there aren't enough embeddings to judge (< MIN_COVERAGE
    or < 3 articles with embeddings). Caller decides whether to skip or gate.
    """
    if not story.centroid_embedding:
        return None
    present = [e for e in story.article_embeddings if e]
    total = len(story.article_embeddings)
    if total == 0 or len(present) / total < MIN_COVERAGE or len(present) < 3:
        return None
    sims = [_cosine(e, story.centroid_embedding) for e in present]
    return sum(sims) / len(sims)


def plan_coherence_archive(stories: list[CandidateStory]) -> list[tuple[str, float]]:
    """Return (story_id, coherence_score) pairs to archive, capped by SAFETY_CAP.

    Caller is responsible for:
      - Excluding already-archived and frozen stories (frozen stays on homepage).
      - Excluding stories outside the age window (MAX_AGE_HOURS).
      - Excluding stories outside the article-count range (plan() checks too,
        but a double-check in the DB query is good defence-in-depth).
    """
    results = []
    for s in stories:
        if s.priority >= PIN_FLOOR:
            continue
        if not (MIN_ARTICLE_COUNT <= s.article_count <= MAX_ARTICLE_COUNT):
            continue
        score = score_coherence(s)
        if score is None:
            continue
        if score < COHERENCE_MIN:
            results.append((s.story_id, round(score, 3)))
            if len(results) >= SAFETY_CAP:
                break
    return results
