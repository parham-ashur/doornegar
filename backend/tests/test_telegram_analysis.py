"""Risk-prioritized tests for `app/services/telegram_analysis.py` —
round 4 of survival roadmap item #9.

Focus areas:
- `_normalize_channel_name`: free-text → canonical form. Used to
  resolve LLM-emitted supporter strings ("کانال احمد زیدآبادی") to
  real `TelegramChannel.username` rows. If this drifts, prediction
  enrichment silently produces 0% for everything.
- `link_posts_by_embedding` threshold constants: 0.35 baseline +
  0.10 aged bump @ 2d. Mirrors clustering's 0.40→0.55 friction so
  the two surfaces age stories at the same rate.
- `reassign_posts_by_embedding` rebalance gate: 0.08 drift gap +
  0.40 min score. Prevents thrash around borderline matches.

Run: `cd backend && pytest tests/test_telegram_analysis.py -v`
"""

from pathlib import Path

from app.services.telegram_analysis import _normalize_channel_name


def _telegram_src() -> str:
    return (
        Path(__file__).parent.parent / "app" / "services" / "telegram_analysis.py"
    ).read_text()


# ═════════════════════════════════════════════════════════════════════
# 1. _normalize_channel_name — the supporter-matching workhorse
# ═════════════════════════════════════════════════════════════════════

class TestNormalizeChannelName:
    """Used by `enrich_predictions_with_analyst_counts` to match
    LLM-emitted supporter strings against real TelegramChannel rows.
    Free-text variants the function must collapse:

      - leading @ ("@nasser_zera...")
      - guillemets (« »)
      - `کانال ` prefix the LLM adds
      - Arabic ي / ك vs Persian ی / ک
      - whitespace + casing

    A regression here means every prediction shows 0% supporter
    coverage even when the channels are present in the DB."""

    def test_empty_returns_empty(self):
        assert _normalize_channel_name("") == ""
        assert _normalize_channel_name(None) == ""

    def test_strips_at_prefix(self):
        assert _normalize_channel_name("@durov") == "durov"

    def test_strips_persian_guillemets(self):
        assert _normalize_channel_name("«bbcpersian»") == "bbcpersian"

    def test_strips_kanal_prefix(self):
        assert _normalize_channel_name("کانال احمد زیدآبادی") == "احمد زیدآبادی"

    def test_strips_channel_prefix(self):
        assert _normalize_channel_name("channel iranintl") == "iranintl"

    def test_collapses_arabic_yeh_to_persian(self):
        # ي (Arabic yeh, U+064A) → ی (Persian yeh, U+06CC)
        assert _normalize_channel_name("علي") == _normalize_channel_name("علی")

    def test_collapses_arabic_kaf_to_persian(self):
        # ك (Arabic kaf, U+0643) → ک (Persian kaf, U+06A9)
        assert _normalize_channel_name("كانال") == _normalize_channel_name("کانال")

    def test_lowercases_latin(self):
        assert _normalize_channel_name("BBCPersian") == "bbcpersian"

    def test_handles_combination(self):
        """Real LLM output: '«کانال @BBCPersian»' must collapse to
        the bare username 'bbcpersian'."""
        assert _normalize_channel_name("«کانال @BBCPersian»") == "bbcpersian"

    def test_strips_surrounding_whitespace(self):
        assert _normalize_channel_name("  durov  ") == "durov"

    def test_idempotent(self):
        """Applying twice must not change the output — used in
        equality checks downstream."""
        once = _normalize_channel_name("«@DUROV»")
        assert _normalize_channel_name(once) == once


# ═════════════════════════════════════════════════════════════════════
# 2. link_posts_by_embedding threshold constants
# ═════════════════════════════════════════════════════════════════════

class TestLinkPostsThresholds:
    """The Telegram-link path mirrors the article-clustering threshold
    ladder. From `project_freshness_model.md` (2026-04-29): article
    threshold bumps 0.40 → 0.55 at 2d; Telegram-link threshold bumps
    0.35 → 0.45 with the same 2d trigger.

    If anyone changes one without the other, the two surfaces age
    stories at different rates — Telegram posts attach to stale
    stories that articles correctly refused, then the homepage shows
    'fresh discourse' on a frozen-content cluster."""

    def test_baseline_threshold_is_0_35(self):
        src = _telegram_src()
        # Default arg value of `link_posts_by_embedding`.
        idx = src.find("async def link_posts_by_embedding(")
        end = src.find(")", idx + 50)
        sig = src[idx:end + 1]
        assert "threshold: float = 0.35" in sig, (
            "link_posts_by_embedding default threshold must be 0.35. "
            "Mirrors the article-matcher 0.40 baseline at a slightly "
            "looser setting because Telegram posts are shorter."
        )

    def test_aged_bump_constants_present(self):
        src = _telegram_src()
        assert "AGED_TG_THRESHOLD_BUMP = 0.10" in src, (
            "Aged-candidate bump must add 0.10 — produces 0.45 at 2d, "
            "mirroring the 0.40→0.55 article-clustering friction."
        )
        assert "AGED_TG_DAYS = 2" in src, (
            "Aged-candidate trigger must be 2 days, mirroring the "
            "AGED_CANDIDATE_DAYS = 2 in clustering.py."
        )

    def test_baseline_plus_bump_equals_clustering_aged(self):
        """The math invariant: 0.35 + 0.10 = 0.45. If anyone changes
        one constant without the other, the post-link aged threshold
        no longer mirrors the article-side aged threshold."""
        import re
        src = _telegram_src()
        baseline = float(
            re.search(r"threshold: float = ([\d.]+)", src).group(1)
        )
        bump = float(
            re.search(r"AGED_TG_THRESHOLD_BUMP = ([\d.]+)", src).group(1)
        )
        assert round(baseline + bump, 2) == 0.45, (
            f"baseline ({baseline}) + bump ({bump}) must equal 0.45 — "
            f"the documented aged-candidate Telegram threshold per "
            f"project_freshness_model.md (2026-04-29)."
        )


# ═════════════════════════════════════════════════════════════════════
# 3. reassign_posts_by_embedding rebalance gate
# ═════════════════════════════════════════════════════════════════════

class TestReassignThresholds:
    """`reassign_posts_by_embedding` walks already-linked posts and
    moves them when a better match exists. Two safeguards prevent
    thrash:

      - drift_gap = 0.08: alternative story must score this much
        higher than the current attachment
      - min_score = 0.40: alternative must clear an absolute floor
        (stricter than link's 0.35 — moving is a stronger claim)

    If either gets too loose, posts ping-pong between similar
    stories every cron tick."""

    def test_drift_gap_default(self):
        src = _telegram_src()
        idx = src.find("async def reassign_posts_by_embedding(")
        end = src.find(")", idx + 50)
        sig = src[idx:end + 1]
        assert "drift_gap: float = 0.08" in sig, (
            "reassign drift_gap must default to 0.08 — below this, "
            "posts thrash between similar stories."
        )

    def test_min_score_stricter_than_link_threshold(self):
        """Moving a post to a new story is a stronger claim than the
        initial attachment, so min_score must exceed the link
        threshold."""
        import re
        src = _telegram_src()
        link_threshold = float(
            re.search(r"threshold: float = ([\d.]+)", src).group(1)
        )
        # Find min_score in reassign signature specifically.
        idx = src.find("async def reassign_posts_by_embedding(")
        end = src.find(")", idx + 50)
        sig = src[idx:end + 1]
        m = re.search(r"min_score: float = ([\d.]+)", sig)
        assert m
        min_score = float(m.group(1))
        assert min_score > link_threshold, (
            f"reassign min_score ({min_score}) must be stricter than "
            f"link threshold ({link_threshold}) — reassignment is a "
            f"stronger claim than initial attachment."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. _clean_vec — defensive vector validation
# ═════════════════════════════════════════════════════════════════════

class TestCleanVecGuard:
    """Both link_posts_by_embedding and reassign define `_clean_vec`
    locally. Centroids in production have included dicts (legacy
    format), lists with None values (failed embeddings written as
    placeholders), and partially initialized vectors. Without this
    guard, cosine_similarity raises mid-loop and the entire batch
    fails."""

    def test_clean_vec_present_in_link_path(self):
        src = _telegram_src()
        # Both functions must define a _clean_vec helper that:
        # - rejects non-list (dict / scalar / None)
        # - rejects empty list
        # - rejects lists with None / non-numeric entries
        link_idx = src.find("async def link_posts_by_embedding(")
        link_end = src.find("\nasync def ", link_idx + 100)
        link_body = src[link_idx:link_end if link_end > 0 else len(src)]
        assert "_clean_vec" in link_body, (
            "link_posts_by_embedding must validate centroid vectors "
            "before passing them to cosine_similarity. Bare dict / "
            "None-laced lists in production caused crash-mid-batch."
        )
        assert "isinstance(v, list)" in link_body
        assert "x is None" in link_body

    def test_clean_vec_present_in_reassign_path(self):
        src = _telegram_src()
        idx = src.find("async def reassign_posts_by_embedding(")
        end = src.find("\nasync def ", idx + 100)
        body = src[idx:end if end > 0 else len(src)]
        assert "_clean_vec" in body, (
            "reassign_posts_by_embedding must also validate centroids "
            "— same risk as link_posts_by_embedding."
        )


# ═════════════════════════════════════════════════════════════════════
# 5. _build_track_records produces deterministic output
# ═════════════════════════════════════════════════════════════════════

class TestBuildTrackRecords:
    """`_build_track_records` summarizes channel leanings present in
    a post set. Pure function. The output is fed to the LLM prompt,
    so its format must stay stable; if the LLM-facing format
    silently changes, prompt accuracy degrades without any runtime
    error."""

    def test_empty_posts_returns_string(self):
        from app.services.telegram_analysis import _build_track_records
        # Must not crash on empty input
        result = _build_track_records([])
        assert isinstance(result, str)
