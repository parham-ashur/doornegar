"""Risk-prioritized tests for `app/services/story_analysis.py` parsing
+ helpers — round 3 of survival roadmap item #9.

Focus: pure functions only (LLM call paths already covered by
`test_war_audit_fixes.py::TestStoryAnalysisGpt5JsonMode` etc.).
The parsing path is where silent-corruption bugs live: a JSON parse
that swallows malformed responses, a default-filling step that
overwrites real values, a bullet-joiner that returns "" instead of
None — all silently produce empty-card stories on the homepage.

Run: `cd backend && pytest tests/test_story_analysis_parsing.py -v`
"""

import json
import pytest

from app.services.story_analysis import (
    _parse_analysis_response,
    _compute_article_evidence,
    _join_side_bullets,
)


# ═════════════════════════════════════════════════════════════════════
# 1. _parse_analysis_response — JSON extraction and defaults
# ═════════════════════════════════════════════════════════════════════

class TestParseAnalysisResponseExtraction:
    """The LLM occasionally wraps JSON in code fences (```json ... ```)
    even when response_format=json_object is set. Parser must strip
    them before json.loads. Without this, every fenced reply looked
    like a parse failure and the story stayed un-summarized."""

    def test_plain_json_parses(self):
        raw = '{"title_fa": "عنوان"}'
        result = _parse_analysis_response(raw)
        assert result["title_fa"] == "عنوان"

    def test_json_fenced_code_block_stripped(self):
        raw = '```json\n{"title_fa": "عنوان"}\n```'
        result = _parse_analysis_response(raw)
        assert result["title_fa"] == "عنوان"

    def test_bare_fenced_code_block_stripped(self):
        raw = '```\n{"title_fa": "عنوان"}\n```'
        result = _parse_analysis_response(raw)
        assert result["title_fa"] == "عنوان"

    def test_invalid_json_raises_not_silent(self):
        """Per `feedback_no_silent_fallbacks.md`: parsing failures must
        raise, not return a dict-with-defaults. A silent default-fill
        on a malformed LLM response would mark the story as analyzed
        with empty content — invisibly broken, sentinel-trap territory.
        """
        with pytest.raises(RuntimeError, match="Failed to parse"):
            _parse_analysis_response("this is not json")

    def test_partial_json_truncated_raises(self):
        # gpt-5 with insufficient max_completion_tokens (the fix in
        # commit 3f7b2da) used to truncate JSON mid-string. Must raise.
        with pytest.raises(RuntimeError):
            _parse_analysis_response('{"title_fa": "incomplete')


class TestParseAnalysisDefaultFilling:
    """When the LLM returns a partial response (missing fields), the
    parser fills required keys with None. This keeps downstream
    consumers (auto_maintenance.step_summarize) from KeyError-ing
    when an older prompt version returns fewer fields."""

    REQUIRED_KEYS = {
        "title_fa", "title_en", "summary_fa", "narrative",
        "state_summary_fa", "diaspora_summary_fa",
        "independent_summary_fa", "bias_explanation_fa",
        "scores", "article_neutrality", "dispute_score",
        "loaded_words", "narrative_arc", "delta",
    }

    def test_all_required_keys_present_after_parse(self):
        result = _parse_analysis_response('{"title_fa": "x"}')
        for key in self.REQUIRED_KEYS:
            assert key in result, (
                f"_parse_analysis_response must default-fill {key}. "
                f"step_summarize reads it unconditionally; KeyError "
                f"on missing fields would crash the maintenance step."
            )

    def test_default_for_missing_key_is_none(self):
        result = _parse_analysis_response('{"title_fa": "x"}')
        # All defaults should be None — NOT empty string or zero.
        # Empty string would pass `if x:` checks falsely; None makes
        # the absence explicit.
        assert result["dispute_score"] is None
        assert result["scores"] is None
        assert result["bias_explanation_fa"] is None

    def test_real_value_not_overwritten_by_default(self):
        """Sanity: if the LLM returns a real value, the default-filler
        must not stomp it. This bug class is sneaky — easy to write a
        loop that always sets the default, never preserves the value."""
        result = _parse_analysis_response(json.dumps({
            "title_fa": "x",
            "dispute_score": 0.75,
        }))
        assert result["dispute_score"] == 0.75


class TestParseAnalysisLegacyFallback:
    """The 4-subgroup `narrative` block is the new shape. The legacy
    homepage card still reads `state_summary_fa` and
    `diaspora_summary_fa`. When the LLM emits only the structured
    bullets and forgets the legacy synth, the parser flattens bullets
    into legacy strings so unmigrated readers don't see blank cards.
    """

    def test_inside_bullets_flatten_to_state_summary(self):
        result = _parse_analysis_response(json.dumps({
            "title_fa": "x",
            "narrative": {
                "inside": {
                    "principlist": ["جمله اول.", "جمله دوم."],
                },
                "outside": {
                    "moderate_diaspora": ["جمله سوم."],
                },
            },
        }))
        assert result["state_summary_fa"]
        assert "جمله اول" in result["state_summary_fa"]
        assert result["diaspora_summary_fa"]
        assert "جمله سوم" in result["diaspora_summary_fa"]

    def test_explicit_legacy_fields_not_overwritten(self):
        """If the LLM provides BOTH the new narrative shape AND the
        legacy summary fields, the explicit values win — flatten only
        fills when the legacy field is empty."""
        result = _parse_analysis_response(json.dumps({
            "title_fa": "x",
            "state_summary_fa": "صریح",
            "narrative": {
                "inside": {"principlist": ["پر کردن"]},
            },
        }))
        assert result["state_summary_fa"] == "صریح", (
            "Explicit state_summary_fa from the LLM must not be "
            "overwritten by the bullet-flatten fallback."
        )


# ═════════════════════════════════════════════════════════════════════
# 2. _join_side_bullets defensive shape handling
# ═════════════════════════════════════════════════════════════════════

class TestJoinSideBullets:
    """The flattener must not crash on weird inputs from the LLM —
    nested lists, None values, empty strings, non-dict containers.
    Each guard here corresponds to a real LLM-output mode observed
    in production logs."""

    def test_none_returns_none(self):
        assert _join_side_bullets(None) is None

    def test_non_dict_returns_none(self):
        assert _join_side_bullets("not a dict") is None
        assert _join_side_bullets([]) is None

    def test_empty_dict_returns_none(self):
        """No bullets to join → None, NOT empty string. Empty string
        would pass `if state_summary_fa:` and silently render an
        empty card paragraph."""
        assert _join_side_bullets({}) is None

    def test_dict_of_empty_lists_returns_none(self):
        assert _join_side_bullets({"principlist": [], "reformist": []}) is None

    def test_skips_non_string_bullets(self):
        # LLM occasionally emits a number or null in a bullet list.
        out = _join_side_bullets({
            "principlist": ["valid", 42, None, "also valid"],
        })
        assert "valid" in out
        assert "also valid" in out
        # Numbers / None must not crash or appear as "42" / "None".
        assert "42" not in out
        assert "None" not in out

    def test_skips_non_list_subgroup_values(self):
        out = _join_side_bullets({
            "principlist": ["good"],
            "reformist": "not a list",  # malformed — must not crash
        })
        assert out == "good"


# ═════════════════════════════════════════════════════════════════════
# 3. _compute_article_evidence — deterministic features
# ═════════════════════════════════════════════════════════════════════

class TestComputeArticleEvidence:
    """`_compute_article_evidence` runs *without* an LLM — it counts
    loaded-word hits and Persian quote pairs deterministically. These
    counts back the auditability claim ("the score is reproducible
    even if the LLM disappears"). If this regresses, the bias panel
    loses its evidence column."""

    def test_returns_three_keys(self):
        evidence = _compute_article_evidence({"content": "متن", "title": "عنوان"})
        assert set(evidence.keys()) == {"loaded_hits", "quote_count", "word_count"}

    def test_balanced_quote_pair_counts_one(self):
        evidence = _compute_article_evidence({
            "content": "گزارش گفت «این یک نقل قول» در ادامه آمد.",
            "title": "",
        })
        assert evidence["quote_count"] == 1

    def test_unbalanced_quotes_use_min(self):
        """3 opens, 1 close → 1 valid pair. Without the min(), an
        attacker could spike the count by spamming opening quotes."""
        evidence = _compute_article_evidence({
            "content": "«« «word»",  # 3 opens, 1 close
            "title": "",
        })
        assert evidence["quote_count"] == 1

    def test_empty_content_safe(self):
        evidence = _compute_article_evidence({"content": None, "title": None})
        assert evidence["quote_count"] == 0
        assert evidence["word_count"] == 0
        # Loaded hits dict must exist (empty counts), not be None.
        assert isinstance(evidence["loaded_hits"], dict)

    def test_word_count_roughly_correct(self):
        evidence = _compute_article_evidence({
            "content": "یک دو سه چهار پنج",
            "title": "عنوان",
        })
        # 5 content + 1 title = 6 tokens by split().
        assert evidence["word_count"] == 6

    def test_loaded_hits_keyed_by_subgroup(self):
        """The 4-subgroup taxonomy means loaded_hits must have one
        key per subgroup. If a key disappears, the bias panel's
        per-side word-cloud breaks for that subgroup."""
        from app.services.story_analysis import LOADED_WORDS_FA
        evidence = _compute_article_evidence({"content": "", "title": ""})
        # All subgroups present (even with 0 hits)
        for subgroup in LOADED_WORDS_FA.keys():
            assert subgroup in evidence["loaded_hits"]
            assert evidence["loaded_hits"][subgroup] == 0
