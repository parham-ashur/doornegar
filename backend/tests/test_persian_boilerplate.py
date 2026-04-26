"""Unit tests for the boilerplate stripper.

Pure function — no DB, no network. Fixtures are built from real
pollution observed in the 2026-04-26 embedder-comparison run.
"""

from app.nlp.persian import extract_text_for_embedding, strip_boilerplate


class TestUniversalStrip:
    def test_transferring_to_website_english(self):
        body = (
            "Transferring to the website...\n"
            "در ﺣﺎل اﻧﺘﻘﺎل ﺑﻪ ﺳﺎﯾﺖ ﻣﻮرد ﻧﻈﺮ ﻫﺴﺘﯿﺪ..."
        )
        out = strip_boilerplate(body)
        # Both the English line and the Persian-presentation-form line
        # should be gone — what's left is at most a stub.
        assert "Transferring" not in out
        assert "انتقال" not in out

    def test_strips_comments_section_block(self):
        body = (
            "نیروی دریایی آمریکا یک کشتی متعلق به ایران را در دریای عرب توقیف کرده است. "
            "گزارش خطا\n"
            "غیر قابل انتشار: ۱\n"
            "در انتظار بررسی: ۰\n"
            "انتشار یافته: ۱\n"
            "کاربر گفت: آخر این جنگ به دعوا می‌کشه"
        )
        out = strip_boilerplate(body)
        # Lede preserved, the comments scaffold gone.
        assert "نیروی دریایی" in out
        assert "گزارش خطا" not in out
        assert "غیر قابل انتشار" not in out
        assert "انتشار یافته" not in out

    def test_strips_kod_khabar_meta_line(self):
        body = (
            "محتوای واقعی مقاله اینجاست.\n"
            "کد خبر: ۱۳۶۹۱۸۶\n"
            "ادامه محتوا"
        )
        out = strip_boilerplate(body)
        assert "محتوای واقعی" in out
        assert "کد خبر" not in out

    def test_short_input_passthrough(self):
        assert strip_boilerplate("") == ""
        assert strip_boilerplate(None) == ""
        assert strip_boilerplate("یک خط کوتاه") == "یک خط کوتاه"


class TestSourceSpecific:
    def test_iran_international_image_caption_stripped(self):
        # Real pollution from the 2026-04-26 experiment: this caption
        # appeared in three unrelated articles and pulled them all
        # toward the same wrong cluster.
        caption = (
            "تصاویر رسیده به ایران اینترنشنال نشان میدهد که کلمه «جاویدنام» "
            "بر سنگ مزار شاهرخ همایونی نوجوان ۱۴ ساله املشی در آرامستان "
            "این شهر مخدوش شده است."
        )
        body = (
            "خبر اصلی درباره مذاکرات سیاسی است و نقش بازیگران منطقه‌ای را "
            "تحلیل می‌کند.\n" + caption
        )
        out = strip_boilerplate(body, source_slug="iran-international")
        assert "خبر اصلی درباره مذاکرات" in out
        assert "تصاویر رسیده به ایران اینترنشنال" not in out
        assert "شاهرخ همایونی" not in out

    def test_other_source_does_not_strip_iran_intl_pattern(self):
        # Articles legitimately mentioning Iran International in their
        # body (e.g., quoting a report) should not be stripped when
        # the source isn't iran-international.
        body = "به نقل از ایران اینترنشنال، یک مقام دولتی گفت..."
        out = strip_boilerplate(body, source_slug="tabnak")
        assert "ایران اینترنشنال" in out


class TestExtractTextForEmbedding:
    def test_source_slug_routes_through_stripper(self):
        title = "تیتر مقاله"
        body = (
            "خبر اصلی درباره اقتصاد است. "
            "تصاویر رسیده به ایران اینترنشنال نشان میدهد که این پست بی‌ارتباط است."
        )
        with_slug = extract_text_for_embedding(title, body, source_slug="iran-international")
        without_slug = extract_text_for_embedding(title, body)
        # Without slug → no stripping happens, caption stays.
        assert "اینترنشنال" in without_slug
        # With slug → caption removed, real content preserved.
        assert "اینترنشنال" not in with_slug
        assert "اقتصاد" in with_slug
        assert "تیتر مقاله" in with_slug

    def test_no_body_unchanged(self):
        out = extract_text_for_embedding("فقط تیتر", None, source_slug="iran-international")
        assert "فقط تیتر" in out
