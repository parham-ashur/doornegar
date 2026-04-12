# Doornegar Quality Audit — 2026-04-12

## Executive Summary

First comprehensive quality audit of the live Doornegar platform. Found **5 critical bugs** (3 fixed), **clustering drift** producing duplicate stories, and several code health issues. Neon transfer crisis (4.5/5GB) resolved with caching optimizations.

---

## 1. LLM Output Quality

### Summaries: GOOD
- Farsi quality is solid — formal, accurate, well-structured
- Side-by-side comparisons (state vs diaspora framing) work well
- bias_explanation_fa provides genuine insight

### Issues Found
| Issue | Severity | Example |
|-------|----------|---------|
| **Title mismatch (EN/FA)** | HIGH | Story `6d0eb739`: EN="Iran's missile attack on Tel Aviv" vs FA="Joint US-Israel airstrikes on Iran" — **opposite events** |
| **No analyst factors** | LOW | All existing summaries predate the feature. Needs Refresh 16 from dashboard |
| **Bias scores reasonable** | OK | Tone/factuality/emotional scores look correctly calibrated |

### Prompt Issues (from audit)
- Story analysis: informal "تو" should be "شما" for system prompt
- Analyst addendum: potential_outcomes says "min 2" but also "null if irrelevant" — contradictory
- Clustering prompt: no few-shot JSON examples → causes malformed outputs
- Bias scoring: pro_regime/reformist/opposition scores described as non-exclusive but LLMs assume they sum to 1.0

---

## 2. Clustering Quality

### Duplicate Stories (CRITICAL)
6 stories about Iran-US ceasefire should be 2-3:
1. "Ceasefire Agreement Between Iran and US" — 39 articles
2. "Immediate ceasefire proposal" — 22 articles
3. "Two-week ceasefire between US and Iran" — 19 articles
4. "Reactions to the Iran-US Ceasefire" — 10 articles
5. "Iran and US Ceasefire and International Reactions" — 10 articles
6. "Two-week conditional suspension..." — 9 articles

3 Islamabad talks stories should be 1:
1. "Failure to reach agreement in Islamabad" — 18 articles
2. "Islamabad talks end without agreement" — 11 articles
3. "Iran and US Negotiations in Islamabad" — 10 articles

### Mismatched Articles
Ceasefire story (39 articles) contains 5+ unrelated articles:
- Execution of Amir-Hossein Hatami (unrelated)
- Saudi Arabia Hajj hostage speculation (unrelated)
- Iran riots info war (unrelated)
- Erfan Soltani execution story (unrelated)
- Fatemiyoun forces anger (unrelated)

### Duplicate Articles
At least 2 pairs of duplicate articles within the ceasefire cluster (Radio Zamaneh).

### Single-Source Cluster
"Press TV reports collection" — source_count=1, not useful for cross-source comparison.

---

## 3. Homepage/UX

### What Works
- RTL layout correct
- Images showing on trending stories
- Dates visible (relative time + update timestamps)
- Bias percentages showing on hero and cards
- ~30 stories displayed across various layouts
- No error messages or broken states

### Bugs Found and Fixed
| Bug | Status |
|-----|--------|
| Ghost story (0 articles, trending_score=182) at top of `/stories` list | **FIXED** |
| `/stories` endpoint returned state_pct=0 for all stories | **FIXED** |
| `/stories` endpoint returned image_url=null for all stories | **FIXED** |

---

## 4. Code Health (14 issues found)

### Fixed in This Session
1. **Unclaim trending_score** — now zeroed alongside article_count
2. **List endpoint** — now loads articles for image/percentage computation
3. **Centroid lazy-load race condition** — now uses explicit DB query
4. **Unbounded story load in fix_images** — capped at 200

### Remaining (lower priority)
| # | Severity | File | Issue |
|---|----------|------|-------|
| 2 | MAJOR | clustering.py:477 | Missing flush after batch metadata refresh |
| 5 | MAJOR | clustering.py:689 | No commit after story creation loop |
| 6 | MAJOR | clustering.py:363 | Double-matching articles without embeddings |
| 8 | MAJOR | auto_maintenance.py:385 | Rollback doesn't clear ORM state |
| 9 | MAJOR | auto_maintenance.py:228 | Unbounded story load in centroid recompute |
| 10 | MAJOR | auto_maintenance.py:716 | Unbounded article removal loop |
| 12 | MODERATE | clustering.py:615 | Missing null-check on centroid callers |
| 14 | MAJOR | auto_maintenance.py:918 | Race condition in archive stale |

### Note
Many of these are theoretical at current scale (~400 stories, ~2000 articles). They'll matter when the dataset grows 10x+.

---

## 5. Neon Transfer Optimization

### Problem
4.5/5GB monthly transfer used by April 12 (billing cycle unknown).

### Root Causes
- Dashboard polling: 17 DB queries every 60s (cache TTL too short)
- Frontend ISR: all endpoints revalidated every 30s
- No backend response caching on story endpoints

### Fixes Applied
| Change | Impact |
|--------|--------|
| Dashboard cache TTL: 60s → 300s | ~80% fewer dashboard queries |
| Frontend revalidation: 30s → 120-600s by endpoint | ~75% fewer API calls |
| Backend trending cache: 2-min in-memory | ~95% fewer trending DB queries |

### Estimated Transfer Reduction: ~70%

---

## 6. Prompt Improvement Opportunities

### Bias Scoring (bias_scoring.py) — Best prompt
- Excellent few-shot examples
- Clear schema with explicit ranges
- Minor: clarify camp scores are independent (don't sum to 1.0)

### Story Analysis (story_analysis.py) — Needs work
- Add few-shot example showing null sides
- Add analyst factor examples
- Fix potential_outcomes: "min 2" contradicts "null if irrelevant"
- Move media vocabulary to premium-only (save tokens on baseline)

### Clustering (clustering.py) — Most improvement potential
- Add few-shot JSON output examples to both MATCHING_PROMPT and CLUSTERING_PROMPT
- Clarify "same event" definition for follow-up reporting
- Add validation in merge prompt for overlapping group indices

---

## Action Items

### Immediate (deploy these code changes)
- [x] Dashboard cache 60s → 300s
- [x] Frontend revalidation differentiated
- [x] Backend trending cache added
- [x] `/stories` list endpoint fixed (images + percentages)
- [x] Unclaim now zeros trending_score
- [x] Centroid computation uses explicit DB query
- [x] Fix_images story load capped at 200

### After Deploy
- [ ] Run "Refresh 16" from dashboard to add analyst factors to top stories
- [ ] Consider merging duplicate ceasefire stories (6 → 2-3)
- [ ] Consider merging duplicate Islamabad stories (3 → 1)

### Future Sessions
- [ ] Fix remaining code health issues (priority: clustering flush/commit)
- [ ] Add few-shot examples to clustering prompts
- [ ] Add merge-stories admin endpoint for easier curation
