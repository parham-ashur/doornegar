"""2026-07-08: the dashboard's "without Farsi title" warning jumped
26 -> 177 in 24h. Root cause: process_unprocessed_articles only ever
translates articles whose content_type is in the source's
content_filters['allowed'] whitelist (nlp_pipeline.py) — off_topic /
opinion / discussion / aggregation / other articles never reach it, so
their title_fa stays NULL forever by design. step_backfill_farsi_titles
had no such filter, so its 300-per-run cap was spent on whichever 300
NULL-title rows the DB returned first (no content_type filter, no
ordering) — half the time on articles nobody will ever see — while real
"news" articles waited behind them. A production check found 87/177 were
off_topic (harmless) but 51 of the remaining 84 news articles were also
still unclustered and up to 5 days old, heading for silent deletion under
the 7-day retention rule without a reader ever seeing them.

Fix: both the backfill step and the dashboard's without_fa_title count now
share the same content_type whitelist predicate used by
process_unprocessed_articles (content_type IS NULL OR in the source's
allowed list), and the backfill step orders oldest-first so the
longest-stuck real articles clear before a fresh batch of off-topic noise.
"""

import inspect


def _backfill_source():
    import auto_maintenance
    return inspect.getsource(auto_maintenance.step_backfill_farsi_titles)


def _dashboard_source():
    from app.api.v1 import admin
    return inspect.getsource(admin.get_dashboard)


class TestBackfillFarsiTitlesSkipsUndisplayableContentTypes:
    def test_uses_same_whitelist_predicate_as_nlp_pipeline(self):
        body = _backfill_source()
        assert "content_filters" in body and "'allowed'" in body, (
            "backfill must gate on the same source.content_filters['allowed'] "
            "whitelist as process_unprocessed_articles, or it keeps burning "
            "its 300/run cap translating off_topic articles nobody will see"
        )

    def test_keeps_unclassified_articles_eligible(self):
        body = _backfill_source()
        assert "content_type.is_(None)" in body, (
            "articles not yet classified (content_type IS NULL) must stay "
            "eligible — they may turn out to be displayable news"
        )

    def test_orders_oldest_first(self):
        body = _backfill_source()
        assert "order_by(Article.ingested_at.asc())" in body, (
            "must process oldest-stuck articles first so real news doesn't "
            "get starved behind a fresh batch of off-topic noise"
        )


class TestDashboardWithoutFaTitleMatchesDisplayableScope:
    def test_dashboard_metric_uses_same_whitelist_predicate(self):
        body = _dashboard_source()
        assert body.count("content_filters") >= 1 and "'allowed'" in body, (
            "the dashboard's without_fa_title count must exclude "
            "permanently-undisplayable content types (off_topic/opinion/"
            "discussion/aggregation/other), or the warning threshold fires "
            "on a harmless, permanent backlog instead of real stuck news"
        )
