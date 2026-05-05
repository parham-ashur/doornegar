"""Tests for `app/services/bias_scoring.py` parsing helpers —
round 8 of survival roadmap item #9.

`_parse_llm_response` is the boundary between the LLM's free-form
text and the per-article scores stored in the DB. Three failure
classes that have happened or could happen:

1. LLM returns JSON in code fences — must strip both ``` and ```json
2. LLM returns out-of-range scores — must clamp to [-1, 1] / [0, 1]
3. LLM returns invalid framing labels — must filter to FRAMING_LABELS
4. JSON parse failure must return None (not raise) per the
   feedback_no_silent_fallbacks pattern (None propagates as 'skip',
   raising would fail the whole batch)

`_estimate_confidence` is read by the bias panel to surface "how
confident is this score?" — its formula must stay stable so historical
scores remain interpretable.

Run: `cd backend && pytest tests/test_bias_scoring_parsing.py -v`
"""

import json

from app.services.bias_scoring import (
    _parse_llm_response,
    _estimate_confidence,
    FRAMING_LABELS,
)


# ═════════════════════════════════════════════════════════════════════
# 1. _parse_llm_response — JSON extraction
# ═════════════════════════════════════════════════════════════════════

class TestParseLlmResponseExtraction:
    def test_plain_json_parses(self):
        out = _parse_llm_response('{"political_alignment": 0.5}')
        assert out is not None
        assert out["political_alignment"] == 0.5

    def test_strips_json_code_fence(self):
        out = _parse_llm_response('```json\n{"tone_score": 0.3}\n```')
        assert out is not None
        assert out["tone_score"] == 0.3

    def test_strips_bare_code_fence(self):
        out = _parse_llm_response('```\n{"tone_score": 0.3}\n```')
        assert out is not None
        assert out["tone_score"] == 0.3

    def test_invalid_json_returns_none(self):
        """The score_unscored_articles loop relies on None to mark a
        skip. Raising would fail the batch — same pattern as the
        feedback_no_silent_fallbacks defense."""
        assert _parse_llm_response("not json") is None
        assert _parse_llm_response("") is None

    def test_value_error_in_clamp_returns_none(self):
        """If a field isn't numeric (e.g. LLM returned "high" instead
        of 0.8), `float()` raises ValueError. Must return None, not
        crash the batch."""
        out = _parse_llm_response('{"political_alignment": "high"}')
        assert out is None


# ═════════════════════════════════════════════════════════════════════
# 2. _parse_llm_response — value clamping
# ═════════════════════════════════════════════════════════════════════

class TestParseLlmResponseClamping:
    """The LLM occasionally returns scores out of the documented range
    (1.5 instead of clamped 1.0, etc.). The frontend visualizations
    assume the documented ranges; uncapped values blow visual scaling."""

    def test_political_alignment_clamps_above_1(self):
        out = _parse_llm_response('{"political_alignment": 5.0}')
        assert out["political_alignment"] == 1.0

    def test_political_alignment_clamps_below_minus_1(self):
        out = _parse_llm_response('{"political_alignment": -10.0}')
        assert out["political_alignment"] == -1.0

    def test_tone_score_clamped_to_signed_range(self):
        out = _parse_llm_response('{"tone_score": 2.5}')
        assert out["tone_score"] == 1.0
        out = _parse_llm_response('{"tone_score": -2.5}')
        assert out["tone_score"] == -1.0

    def test_unsigned_scores_clamped_to_zero_one(self):
        # pro_regime_score, reformist_score, opposition_score,
        # emotional_language_score, factuality_score live in [0, 1].
        for field in [
            "pro_regime_score", "reformist_score", "opposition_score",
            "emotional_language_score", "factuality_score",
        ]:
            out = _parse_llm_response(json.dumps({field: 5.0}))
            assert out[field] == 1.0, f"{field} did not clamp at 1.0"
            out = _parse_llm_response(json.dumps({field: -3.0}))
            assert out[field] == 0.0, f"{field} did not clamp at 0.0"

    def test_in_range_values_preserved(self):
        out = _parse_llm_response(json.dumps({
            "political_alignment": 0.7,
            "factuality_score": 0.85,
        }))
        assert out["political_alignment"] == 0.7
        assert out["factuality_score"] == 0.85


# ═════════════════════════════════════════════════════════════════════
# 3. Framing-label whitelist enforcement
# ═════════════════════════════════════════════════════════════════════

class TestFramingLabels:
    """The FRAMING_LABELS whitelist exists because the LLM occasionally
    invents labels ("hostility", "patriotism") that don't fit the
    9-category taxonomy. The frontend renders these as chips; new
    labels create unstyled chips and break the bar chart."""

    def test_invalid_labels_filtered(self):
        out = _parse_llm_response(json.dumps({
            "framing_labels": ["conflict", "INVENTED_LABEL", "security"],
        }))
        assert "conflict" in out["framing_labels"]
        assert "security" in out["framing_labels"]
        assert "INVENTED_LABEL" not in out["framing_labels"]

    def test_all_invalid_labels_yields_empty_list(self):
        out = _parse_llm_response(json.dumps({
            "framing_labels": ["INVENTED_A", "INVENTED_B"],
        }))
        assert out["framing_labels"] == []

    def test_all_documented_labels_pass(self):
        # Every label in the constant must round-trip.
        out = _parse_llm_response(json.dumps({
            "framing_labels": list(FRAMING_LABELS),
        }))
        assert set(out["framing_labels"]) == set(FRAMING_LABELS)

    def test_framing_labels_constant_non_empty(self):
        # If FRAMING_LABELS becomes empty, every framing list filters
        # to []. Sanity check that the taxonomy still exists.
        assert len(FRAMING_LABELS) >= 5, (
            "FRAMING_LABELS dropped below 5 entries — likely an "
            "accidental truncation. Frontend bar chart needs the "
            "9-category taxonomy."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. _estimate_confidence — weighted-completeness formula
# ═════════════════════════════════════════════════════════════════════

class TestEstimateConfidence:
    """The bias panel surfaces this as "تحلیل با اطمینان X٪". Formula:

      base = (count of [political_alignment, tone_score,
              factuality_score, emotional_language_score]) / 4 * 0.85
      + 0.10 if reasoning_en
      + 0.05 if framing_labels non-empty
      capped at 1.0

    If anyone "simplifies" the formula, historical scores become
    incomparable across the formula change."""

    def test_all_fields_full_confidence_about_1(self):
        scores = {
            "political_alignment": 0.5,
            "tone_score": 0.3,
            "factuality_score": 0.8,
            "emotional_language_score": 0.4,
            "reasoning_en": "Detailed analysis.",
            "framing_labels": ["conflict"],
        }
        # 4/4 * 0.85 = 0.85 + 0.10 + 0.05 = 1.0
        assert _estimate_confidence(scores) == 1.0

    def test_partial_completeness(self):
        # 2/4 * 0.85 = 0.425; no bonuses
        scores = {
            "political_alignment": 0.5,
            "tone_score": 0.3,
        }
        assert _estimate_confidence(scores) == 0.425

    def test_reasoning_bonus_only(self):
        # 0/4 + reasoning bonus 0.10 = 0.10
        assert _estimate_confidence({"reasoning_en": "x"}) == 0.10

    def test_framing_bonus_only(self):
        # 0/4 + framing 0.05 = 0.05
        assert _estimate_confidence({"framing_labels": ["conflict"]}) == 0.05

    def test_empty_scores_zero_confidence(self):
        assert _estimate_confidence({}) == 0.0

    def test_capped_at_1(self):
        # Even with all bonuses + full fields, can't exceed 1.0.
        scores = {
            "political_alignment": 1.0,
            "tone_score": 1.0,
            "factuality_score": 1.0,
            "emotional_language_score": 1.0,
            "reasoning_en": "x",
            "framing_labels": ["conflict", "security", "morality"],
        }
        assert _estimate_confidence(scores) <= 1.0

    def test_none_values_count_as_missing(self):
        # Per the function: `scores.get(f) is not None`.
        # An explicit None in the dict means the LLM said "I don't know".
        scores = {
            "political_alignment": None,
            "tone_score": 0.5,
        }
        # Only tone_score counts → 1/4 * 0.85 = 0.2125
        assert _estimate_confidence(scores) == 0.2125
