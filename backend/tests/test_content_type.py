"""Unit tests for the content-type classifier.

Heuristic stage runs as pure functions on stub Article objects.
LLM-path test patches ``_call_openai_classify`` so the network is
never touched.

Fixtures are modeled after real khabaronline.ir output: a news outlet
that publishes a heavy mix of original reporting, op-eds (یادداشت),
interviews (گفت‌وگو), and quote-aggregation pieces.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import content_type as ct


def _stub(
    *,
    title: str = "",
    body: str = "",
    summary: str | None = None,
    url: str = "",
    rss_category: str | None = None,
):
    """Build the minimal article-shape the heuristic reads."""
    return SimpleNamespace(
        title_original=title,
        content_text=body,
        summary=summary,
        url=url,
        rss_category=rss_category,
    )


# ─── Heuristic stage ──────────────────────────────────────────────────
class TestHeuristicKeep:
    """Cases that should be kept as 'news' on heuristic alone."""

    def test_news_lede_with_announce_verb(self):
        art = _stub(
            title="مرکز آمار: تورم نقطه‌به‌نقطه به ۳۲ درصد رسید",
            body=(
                "مرکز آمار ایران اعلام کرد نرخ تورم نقطه‌به‌نقطه در ماه گذشته "
                "به ۳۲ درصد رسیده است. مقامات این مرکز افزودند روند کاهشی است."
            ),
            url="https://www.khabaronline.ir/news/2046123/economy/inflation",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "news"
        assert v.confidence >= 0.8

    def test_news_with_named_source_and_quote(self):
        art = _stub(
            title="رئیس بانک مرکزی: نرخ ارز تثبیت می‌شود",
            body=(
                "رئیس بانک مرکزی در نشست خبری امروز خبر داد که برای تثبیت "
                "نرخ ارز سه برنامه عملیاتی در دستور کار است."
            ),
            url="https://www.khabaronline.ir/news/2046999/economy",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "news"


class TestHeuristicDrop:
    """Cases that should be labeled non-'news' and skipped downstream."""

    def test_opinion_title_prefix(self):
        art = _stub(
            title="یادداشت/ چرا اقتصاد ایران به اصلاح ساختاری نیاز دارد",
            body="در سال‌های اخیر بسیاری از اقتصاددانان معتقدند ...",
            url="https://www.khabaronline.ir/news/2046444",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "opinion"
        assert v.confidence >= 0.85

    def test_opinion_url_pattern(self):
        art = _stub(
            title="بحران آب در فلات مرکزی",
            body="مقاله مفصلی درباره خشکسالی و مدیریت منابع آب ...",
            url="https://www.khabaronline.ir/opinion/2046555",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "opinion"

    def test_discussion_title_prefix(self):
        art = _stub(
            title="گفت‌وگو/ نگاهی متفاوت به سیاست خارجی ایران",
            body="در این گفت‌وگو با کارشناس مسائل بین‌الملل به بررسی ...",
            url="https://www.khabaronline.ir/news/2046321",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "discussion"

    def test_discussion_url_pattern(self):
        art = _stub(
            title="مصاحبه با وزیر سابق",
            body="...",
            url="https://www.khabaronline.ir/interview/2046111",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "discussion"

    def test_aggregation_repeated_attribution(self):
        body = (
            "به نقل از خبرگزاری ایسنا، مقامات اعلام کردند ... "
            "همچنین به گزارش فارس، یک منبع آگاه گفت ... "
            "به نقل از تسنیم، این منبع افزود ..."
        )
        art = _stub(
            title="مرور خبرها از منابع مختلف",
            body=body,
            url="https://www.khabaronline.ir/news/2046222",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "aggregation"

    def test_aggregation_heavy_quoting(self):
        # Body is mostly the contents of a long «...» quote pair.
        quote_body = "گزارش یک رسانه: «" + ("متن طولانی نقل قول است که شامل اطلاعات بسیار زیادی می‌شود و " * 8) + "»"
        art = _stub(
            title="بازنشر یک گزارش",
            body=quote_body,
            url="https://www.khabaronline.ir/news/2046333",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "aggregation"

    def test_other_url_analysis(self):
        art = _stub(
            title="سال انتخابات در منطقه",
            body="...",
            url="https://www.khabaronline.ir/analysis/2046777",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "other"

    def test_rss_category_opinion(self):
        art = _stub(
            title="چالش‌های پیش رو",
            body="...",
            url="https://www.khabaronline.ir/news/2046888",
            rss_category="Opinion",
        )
        v = ct.heuristic_classify(art)
        assert v is not None and v.label == "opinion"


class TestHeuristicAmbiguous:
    """Cases the heuristic can't resolve — they should fall through to LLM."""

    def test_short_neutral_body_returns_none(self):
        art = _stub(
            title="یک تیتر کوتاه و خنثی",
            body="متنی کوتاه بدون فعل خبری مشخص.",
            url="https://www.khabaronline.ir/news/2046601",
        )
        assert ct.heuristic_classify(art) is None


# ─── LLM stage ────────────────────────────────────────────────────────
class TestLLMPath:
    @pytest.mark.asyncio
    async def test_batch_via_llm_parses_response(self, monkeypatch):
        """When heuristic punts, the LLM helper's mocked output drives
        the verdicts."""
        articles = [
            _stub(title="مقاله یک", body="متن یک", url="https://example.ir/a/1"),
            _stub(title="مقاله دو", body="متن دو", url="https://example.ir/a/2"),
        ]

        fake_response = (
            '[{"id": 1, "label": "news", "confidence": 0.82},'
            ' {"id": 2, "label": "opinion", "confidence": 0.76}]'
        )
        mock_call = AsyncMock(return_value=fake_response)
        monkeypatch.setattr(ct, "_call_openai_classify", mock_call)
        monkeypatch.setattr(ct.settings, "openai_api_key", "test-key")

        verdicts = await ct._classify_batch_via_llm(articles)
        assert mock_call.await_count == 1
        assert len(verdicts) == 2
        assert verdicts[0] is not None and verdicts[0].label == "news"
        assert verdicts[1] is not None and verdicts[1].label == "opinion"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none_slots(self, monkeypatch):
        """A raised exception must NOT crash the pipeline. Articles get
        None verdicts and stay unclassified for the next run."""
        articles = [_stub(title="a", body="b", url="https://e.ir/x")]
        mock_call = AsyncMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(ct, "_call_openai_classify", mock_call)
        monkeypatch.setattr(ct.settings, "openai_api_key", "test-key")

        verdicts = await ct._classify_batch_via_llm(articles)
        assert verdicts == [None]

    @pytest.mark.asyncio
    async def test_llm_skipped_when_no_api_key(self, monkeypatch):
        """No OPENAI_API_KEY → skip the LLM call, leave articles None."""
        articles = [_stub(title="a", body="b", url="https://e.ir/x")]
        mock_call = AsyncMock()
        monkeypatch.setattr(ct, "_call_openai_classify", mock_call)
        monkeypatch.setattr(ct.settings, "openai_api_key", "")

        verdicts = await ct._classify_batch_via_llm(articles)
        mock_call.assert_not_awaited()
        assert verdicts == [None]


class TestParseLLMResponse:
    def test_strips_markdown_fence(self):
        raw = '```json\n[{"id": 1, "label": "news", "confidence": 0.9}]\n```'
        out = ct._parse_llm_response(raw, n=1)
        assert out[0] is not None and out[0].label == "news"

    def test_rejects_unknown_label(self):
        raw = '[{"id": 1, "label": "satire", "confidence": 0.9}]'
        out = ct._parse_llm_response(raw, n=1)
        assert out == [None]

    def test_clamps_confidence(self):
        raw = '[{"id": 1, "label": "news", "confidence": 7.5}]'
        out = ct._parse_llm_response(raw, n=1)
        assert out[0] is not None and out[0].confidence == 1.0

    def test_garbage_input(self):
        raw = "the model wrote prose instead of JSON, sorry"
        out = ct._parse_llm_response(raw, n=3)
        assert out == [None, None, None]
