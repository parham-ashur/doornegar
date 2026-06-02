"""Golden regression cases — real production mistakes, frozen as permanent tests.

THE CONVENTION (Parham 2026-06-02, feedback_iterative_prompt_improvement):
Every time a defect is found — by a canary, by Parham, or during a Niloofar
audit — turn it into a case HERE before (or alongside) shipping the fix. Each
case is a real incident: it names the date, the symptom, the root cause, the
responsible prompt/step, and asserts the fixed behaviour against the *actual*
inputs that broke. This is the "learn from mistakes" loop made mechanical —
the cure (a prompt/step change) is locked in so it can never silently regress.

Add a case with this shape:

    def test_case_<YYYY_MM_DD>_<slug>(self):
        '''SYMPTOM: ...  ROOT CAUSE: ...  RESPONSIBLE: <prompt/step>.'''
        ...assert the fixed behaviour on the real inputs...

Keep cases data-driven and free (no network/LLM) so the whole file runs in CI.
Cross-reference the deeper tripwires in test_war_audit_fixes.py rather than
duplicating them; this file is the human-readable incident catalogue.
"""


class TestGeoTheaterRegressions:
    def test_case_2026_06_01_drugboat_not_clustered_with_iran(self):
        """SYMPTOM: a US eastern-Pacific drug-boat strike («حمله آمریکا به
        شناور در شرق اقیانوس آرام») was clustered into an Iran Hormuz story and
        produced a false '200 deaths on Iranian vessels' headline.
        ROOT CAUSE: clustering judged similarity on embeddings/title with no
        geography awareness. RESPONSIBLE: clustering matcher (_locus_conflict /
        geo-theater gate). FIX: Layer-1 geo gate."""
        from app.services.clustering import _locus_set, _locus_conflict
        drugboat = _locus_set("حمله آمریکا به یک شناور قاچاق مواد مخدر در شرق اقیانوس آرام")
        iran = _locus_set("تبادل آتش ایران و آمریکا در تنگه هرمز؛ بندرعباس")
        assert "americas" in drugboat
        assert "iran" in iran
        assert _locus_conflict(drugboat, iran) is True, (
            "drug-boat (Americas) must NOT cluster with an Iran (Hormuz) story"
        )

    def test_case_geo_same_theater_does_not_conflict(self):
        """Guard the other direction: two Iran-theater texts must NOT be
        blocked (over-blocking would starve real clusters / inflate orphans)."""
        from app.services.clustering import _locus_set, _locus_conflict
        a = _locus_set("حمله به ناوشکن آمریکایی در تنگه هرمز")
        b = _locus_set("سپاه: کنترل هرمز در دست ایران است؛ بندرعباس")
        assert _locus_conflict(a, b) is False


class TestScopeFilterRegressions:
    def test_case_2026_06_02_sports_title_is_offtopic(self):
        """SYMPTOM: sports/weather/celebrity articles (e.g. «کاسمیرو در مسیر
        میامی», «ایران قهرمان وزنه‌برداری جهان») clustered into war/negotiation
        stories. ROOT CAUSE: the content-type classifier judged FORMAT not
        SCOPE — sports IS 'original reporting' → labeled 'news'. RESPONSIBLE:
        content_type classifier + heuristic. FIX: off_topic label + content-
        keyword off-domain heuristic."""
        from app.services.content_type import heuristic_classify

        class _Stub:
            def __init__(self, t):
                self.title_original = t
                self.content_text = self.summary = None
                self.url = ""
                self.rss_category = None
        for title in (
            "کاسمیرو در مسیر میامی برای تجدید دیدار با مسی",
            "ایران قهرمان مسابقات وزنه‌برداری جوانان جهان شد",
            "گواردیولا منچسترسیتی را به قله رساند",
        ):
            v = heuristic_classify(_Stub(title))
            assert v is not None and v.label == "off_topic", (
                f"off-topic regressed for: {title}"
            )

    def test_case_2026_06_02_offtopic_dropped_from_pool(self):
        """off_topic must be a real label that is NOT allowed by default, so
        the NLP/embed gate and clustering gate both exclude it."""
        from app.services.content_type import LABELS, DEFAULT_ALLOWED
        assert "off_topic" in LABELS
        assert "off_topic" not in DEFAULT_ALLOWED


class TestSelfRunningCanaries:
    def test_canaries_present_in_health_overview(self):
        """The 2026-06-02 self-running canaries must stay wired into
        /admin/health/overview so the morning briefing can surface drift
        (Step A of the self-running roadmap)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        for cid in (
            "homepage_grabbag",
            "homepage_offtopic_leak",
            "homepage_fresh_pool",
            "blindspot_fresh_pool",
        ):
            assert f'"{cid}"' in src, f"self-running canary '{cid}' missing from health/overview"
