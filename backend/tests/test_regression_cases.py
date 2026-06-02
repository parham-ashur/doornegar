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


class TestClusterHygiene:
    def test_offtopic_drain_exists_and_mirrors_gate(self):
        """SYMPTOM: homepage_offtopic_leak canary = 173 — off-topic articles
        clustered before the 2026-06-02 gate persist in visible stories
        (clustered articles don't re-cluster). ROOT CAUSE: the gate prevents
        NEW pollution but nothing drains legacy. RESPONSIBLE: step_audit_cluster_
        coherence. FIX: detach_offtopic_from_visible_stories, wired into the
        coherence step, self-heals the canary to 0."""
        from app.services import clustering
        assert hasattr(clustering, "detach_offtopic_from_visible_stories")
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        i = src.find("async def detach_offtopic_from_visible_stories")
        body = src[i:i + 2000]
        # Must mirror the canary / cluster-gate predicate exactly.
        assert "content_filters -> 'allowed') @> to_jsonb(a.content_type)" in body
        assert "st.archived_at IS NULL AND st.article_count >= 5" in body
        # Wired into the coherence step.
        am = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "detach_offtopic_from_visible_stories" in am


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
            "bellwether_missing_story",
        ):
            assert f'"{cid}"' in src, f"self-running canary '{cid}' missing from health/overview"


class TestBellwether:
    def test_bellwether_step_wired_and_service_exists(self):
        """Step B: the missing-main-story monitor — the only failure mode the
        internal canaries can't catch (a story we never ingested). Service +
        pipeline step + canary must all be present."""
        from app.services import bellwether
        assert hasattr(bellwether, "run_bellwether_check")
        assert bellwether.EVENT_TYPE == "bellwether_check"
        from pathlib import Path
        am = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "async def step_bellwether_check" in am
        assert '("bellwether", "Bellwether missing-main-story check", "step_bellwether_check")' in am

    def test_bellwether_headline_extraction(self):
        """Headline extraction must pull <h1>/<h2>/<title> text without an LLM."""
        from app.services.bellwether import _extract_headlines
        html = "<title>Outlet — صفحه اصلی</title><h1>توافق ایران و آمریکا نزدیک است</h1>" \
               "<h2>حمله به تنگه هرمز ادامه دارد</h2><div>noise</div>"
        heads = _extract_headlines(html)
        assert any("توافق ایران و آمریکا" in h for h in heads)
        assert any("تنگه هرمز" in h for h in heads)
