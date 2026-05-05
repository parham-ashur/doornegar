"""Risk-prioritized tests for `app/services/ingestion.py` pure helpers
— round 6 of survival roadmap item #9.

The ingestion path is the front door. Bugs here pollute the DB
silently:

- A stray favicon URL that bypasses `_is_icon_like` lands in
  `Article.image_url` and the homepage card shows a logo as the cover.
- A typo in `_url_excluded` lets per-source noise back into the
  cluster pool.
- A regression in `_extract_image_from_html` that accepts data: URIs
  blows row size and breaks JSON serialization.

Pure functions, no DB, no network. Fast.

Run: `cd backend && pytest tests/test_ingestion_helpers.py -v`
"""

from app.services.ingestion import (
    _url_excluded,
    _is_icon_like,
    _extract_rss_category,
    parse_published_date,
    detect_language,
    _extract_image_from_html,
)


# ═════════════════════════════════════════════════════════════════════
# 1. _is_icon_like — favicon / app-icon URL filter
# ═════════════════════════════════════════════════════════════════════

class TestIsIconLike:
    """Frontend's `imageFilters.ts` mirrors these patterns. Ingest-time
    filtering means the icon never reaches the DB; the frontend filter
    stays as a safety net for legacy rows. If either side drifts,
    homepage cards start showing logos instead of cover images."""

    def test_none_input(self):
        assert _is_icon_like(None) is False
        assert _is_icon_like("") is False

    def test_real_article_image_passes(self):
        assert _is_icon_like("https://cdn.example.com/articles/2026/05/photo.jpg") is False

    def test_favicon_rejected(self):
        assert _is_icon_like("https://example.com/favicon.ico") is True
        assert _is_icon_like("https://example.com/favicon-32.png") is True

    def test_apple_touch_icon_rejected(self):
        assert _is_icon_like("https://example.com/apple-touch-icon.png") is True

    def test_pwa_ico_pattern_rejected(self):
        assert _is_icon_like("https://example.com/path/ico-32x32.png") is True
        assert _is_icon_like("https://example.com/webApp/ico-512x512.png") is True

    def test_manifest_icon_rejected(self):
        assert _is_icon_like("https://example.com/manifest-icon-192.png") is True

    def test_query_string_does_not_break_match(self):
        assert _is_icon_like("https://example.com/favicon.ico?v=2") is True


# ═════════════════════════════════════════════════════════════════════
# 2. _url_excluded — per-source URL exclusions
# ═════════════════════════════════════════════════════════════════════

class TestUrlExcluded:
    """Each Iranian outlet has a per-source pattern list (e.g. exclude
    /sport/, /multimedia/) so non-news sections don't enter the
    article pool. A regression here means clustering wastes embedding
    budget on sports scores or photo galleries."""

    def test_no_source_returns_false(self):
        # When source_slug is None, can't look up patterns — must
        # accept everything (don't break ingest for legacy callers).
        assert _url_excluded("https://example.com/article", None) is False

    def test_no_patterns_for_source_returns_false(self):
        # Source slug we've never registered patterns for.
        assert _url_excluded("https://example.com/article", "no-such-source") is False


# ═════════════════════════════════════════════════════════════════════
# 3. _extract_rss_category — handles list-of-dicts AND string forms
# ═════════════════════════════════════════════════════════════════════

class TestExtractRssCategory:
    """feedparser exposes <category> in two shapes — list of dicts
    (with 'term' key) or bare string. Both occur across the Iranian
    feed corpus. Function must handle both without crashing AND
    produce trimmed, capped output."""

    def test_list_of_dicts_with_term(self):
        assert _extract_rss_category({"tags": [{"term": "Politics"}]}) == "Politics"

    def test_list_of_dicts_with_label_fallback(self):
        # Some feeds use 'label' instead of 'term'.
        assert _extract_rss_category({"tags": [{"label": "اقتصاد"}]}) == "اقتصاد"

    def test_string_category(self):
        assert _extract_rss_category({"category": "Politics"}) == "Politics"

    def test_no_category_returns_none(self):
        assert _extract_rss_category({}) is None

    def test_empty_string_category_returns_none(self):
        assert _extract_rss_category({"category": ""}) is None
        assert _extract_rss_category({"category": "   "}) is None

    def test_caps_at_120_chars(self):
        long = "x" * 200
        result = _extract_rss_category({"category": long})
        assert len(result) == 120

    def test_skips_empty_dict_entries(self):
        # Common feedparser output: a list with an empty dict mixed in.
        result = _extract_rss_category({
            "tags": [{}, {"term": "Real"}, {"term": "Second"}],
        })
        assert result == "Real"

    def test_handles_non_list_tags(self):
        # Some malformed feeds put a string in tags. Don't crash.
        # (Function returns None gracefully.)
        result = _extract_rss_category({"tags": "not-a-list"})
        # Either None or the string — both are non-crash outcomes.
        assert result is None or isinstance(result, str)


# ═════════════════════════════════════════════════════════════════════
# 4. parse_published_date — handles missing fields gracefully
# ═════════════════════════════════════════════════════════════════════

class TestParsePublishedDate:
    """RSS feeds vary on whether they expose published_parsed,
    updated_parsed, both, or neither. Function must:
    - prefer published_parsed (the canonical 'when did this go live?')
    - fall back to updated_parsed
    - return None if neither exists (caller decides to use ingest time)
    - never crash on weird inputs"""

    def test_no_dates_returns_none(self):
        assert parse_published_date({}) is None

    def test_published_parsed_used(self):
        from time import gmtime
        # struct_time for 2026-05-05 12:00:00 UTC
        t = gmtime(1777993200)
        result = parse_published_date({"published_parsed": t})
        assert result is not None
        assert result.year == 2026

    def test_falls_back_to_updated_parsed(self):
        from time import gmtime
        t = gmtime(1777993200)
        result = parse_published_date({"updated_parsed": t})
        assert result is not None

    def test_published_preferred_over_updated(self):
        from time import gmtime
        published = gmtime(1700000000)  # 2023
        updated = gmtime(1777993200)    # 2026
        result = parse_published_date({
            "published_parsed": published,
            "updated_parsed": updated,
        })
        assert result.year == 2023, "published_parsed must win — it's the canonical 'live at' time."

    def test_invalid_struct_doesnt_crash(self):
        # Defensive: feedparser sometimes hands us a list or None.
        assert parse_published_date({"published_parsed": "not-a-struct"}) is None

    def test_returns_utc_aware(self):
        from time import gmtime
        t = gmtime(1777993200)
        result = parse_published_date({"published_parsed": t})
        # Tests around the codebase assume tz-aware UTC. Verify.
        assert result.tzinfo is not None


# ═════════════════════════════════════════════════════════════════════
# 5. detect_language — fa/ar collapse + safe defaults
# ═════════════════════════════════════════════════════════════════════

class TestDetectLanguage:
    """The Persian/Arabic detector is famously noisy on short Persian
    text — single sentences often misclassify as Arabic. The codebase
    folds 'ar' to 'fa' for that reason. Detection failures default to
    'fa' because the corpus is overwhelmingly Persian."""

    def test_arabic_detection_collapses_to_fa(self):
        # Even when langdetect returns 'ar', we treat it as 'fa'.
        # We can't easily force langdetect to output 'ar' here, but
        # we can test the contract: short Persian text returns 'fa'.
        result = detect_language("سلام دنیا. این یک متن نمونه است.")
        assert result == "fa"

    def test_default_on_failure_is_fa(self):
        # langdetect raises on empty/garbage input → fallback to 'fa'.
        assert detect_language("") == "fa"

    def test_english_stays_english(self):
        # English text must NOT be collapsed to 'fa' — there are
        # English articles in the diaspora pool.
        long_en = (
            "The president announced new economic measures today. "
            "Critics argued that these proposals would have minimal "
            "impact on inflation rates over the next quarter."
        )
        result = detect_language(long_en)
        assert result == "en"


# ═════════════════════════════════════════════════════════════════════
# 6. _extract_image_from_html — feed-level image extraction
# ═════════════════════════════════════════════════════════════════════

class TestExtractImageFromHtml:
    """RSS summaries often embed `<img>` tags. Extracting from there
    is faster than scraping the article page, but the HTML can include
    tracking pixels, logos, and small icons. The extractor must:
    - require an absolute URL (no `/relative/path`)
    - reject data: URIs (would store base64 in DB)
    - reject tiny images (<100px width or height)
    - reject known logo/icon/tracker patterns"""

    def test_no_img_tag_returns_none(self):
        assert _extract_image_from_html("plain text", []) is None

    def test_finds_first_image_in_summary(self):
        html = '<p>Lead</p><img src="https://cdn.example.com/news.jpg" />'
        assert _extract_image_from_html(html, []) == "https://cdn.example.com/news.jpg"

    def test_relative_url_rejected(self):
        """RSS feeds occasionally publish relative <img src="/foo.jpg">.
        We can't resolve it without the feed's base URL, so reject."""
        html = '<img src="/local/path.jpg" />'
        assert _extract_image_from_html(html, []) is None

    def test_data_uri_rejected(self):
        """data: URIs would store an entire base64 image in the DB row.
        For a hero card on the homepage that's hundreds of KB per row."""
        html = '<img src="data:image/png;base64,iVBORw0KGgo..." />'
        assert _extract_image_from_html(html, []) is None

    def test_tiny_width_rejected(self):
        html = '<img src="https://cdn.example.com/bug.gif" width="1" height="1" />'
        assert _extract_image_from_html(html, []) is None

    def test_tiny_height_rejected(self):
        html = '<img src="https://cdn.example.com/spacer.png" width="500" height="50" />'
        assert _extract_image_from_html(html, []) is None

    def test_logo_pattern_rejected(self):
        html = '<img src="https://cdn.example.com/site-logo.png" />'
        assert _extract_image_from_html(html, []) is None

    def test_tracking_pixel_rejected(self):
        html = '<img src="https://analytics.example.com/tracking-pixel.gif" />'
        assert _extract_image_from_html(html, []) is None

    def test_content_list_atom_form(self):
        """Atom feeds put HTML in `content` (a list of dicts) instead
        of `summary`. Extractor must check both."""
        content = [{"value": '<img src="https://cdn.example.com/photo.jpg" />'}]
        assert (
            _extract_image_from_html("", content) == "https://cdn.example.com/photo.jpg"
        )

    def test_skips_tag_then_finds_real_image(self):
        """When the first <img> is rejected (logo), keep walking and
        return the next valid one."""
        html = (
            '<img src="https://cdn.example.com/header-logo.png" />'
            '<img src="https://cdn.example.com/article-photo.jpg" />'
        )
        assert (
            _extract_image_from_html(html, [])
            == "https://cdn.example.com/article-photo.jpg"
        )
