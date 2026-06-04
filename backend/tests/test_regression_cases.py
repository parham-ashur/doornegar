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

    def test_case_2026_06_03_bellwether_compares_fresh_not_just_prominent(self):
        """SYMPTOM: the FIRST cron bellwether (2026-06-03) reported 'Iran missile
        attacks on US bases' MISSING at conf 0.9 — but we covered it in TWO
        stories (22e0a9cb, f2f72a09). They were demoted (priority = -50), so
        they sorted below the top-12-by-priority window the comparator saw.
        ROOT CAUSE: _our_top_titles fed the LLM only the most-prominent slice,
        so demoted-but-present coverage read as absent. RESPONSIBLE:
        bellwether._our_top_titles. FIX: union the top-by-priority slice with
        ALL fresh stories (≤ fresh_days, any priority) before the comparison —
        the prompt's own rule is 'covered if we have anything on the event'."""
        import inspect
        from app.services.bellwether import _our_top_titles
        sig = inspect.signature(_our_top_titles)
        # The fresh-coverage union is parameterised — its absence is the bug.
        assert "fresh_days" in sig.parameters, (
            "bellwether must include fresh stories (any priority), not just "
            "the top-by-priority slice, or demoted coverage reads as missing"
        )
        src = inspect.getsource(_our_top_titles)
        assert "first_published_at" in src, "fresh-window filter must be present"
        # Must NOT re-filter the fresh set by priority (that would reintroduce the bug).
        fresh_block = src.split("fresh = ")[-1].split("prominent = ")[0]
        assert "priority" not in fresh_block, (
            "the fresh-coverage query must be priority-agnostic"
        )


class TestClusteringQuality:
    """The 2026-06-03 clustering-quality pass (6 fixes). Parham found grab-bags:
    a singer's obituary holding Marilyn Monroe + weather + Cuba flights; PS752
    families holding a Taliban divorce law; the negotiations cluster holding a
    Japan bear attack. Root cause: embeddings capture THEME not EVENT, and the
    0.60-0.85 LLM band approved same-theme-different-event pairs. These lock the
    six fixes."""

    def test_case_2026_06_03_obituary_grabbag_no_shared_anchor(self):
        """SYMPTOM: «هما میرافشار» obituary clustered with «مرلین مونرو»,
        weather, Cuba flights. ROOT CAUSE: no shared-anchor requirement in the
        LLM band — two 'celebrity death' titles sit ~0.7 cosine. RESPONSIBLE:
        clustering match-to-existing gate. FIX (#1): every LLM candidate must
        share ≥1 content token / quote / number. These two titles share none."""
        from app.services.clustering import _title_tokens
        a = _title_tokens("هما میرافشار، ملکه ترانه‌سرایی ایران، در ۸۹ سالگی درگذشت")
        b = _title_tokens("صدمین سالگرد تولد مرلین مونرو؛ راز مرگ او")
        assert len(a & b) == 0, "obituary titles must share no content token (anchor)"
        # and the gate must be wired for non-small stories, not just small ones
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        assert "has_anchor" in src and "len(a_tokens & s_tokens) >= 1" in src

    def test_auto_reject_cosine_raised_to_063(self):
        """#3: the permissive 0.60-0.85 band was shrunk to 0.63-0.85."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        assert "AUTO_REJECT_COSINE = 0.63" in src

    def test_case_2026_06_03_drugboat_union_find_geo_gate(self):
        """#6: the new-cluster union-find now geo-gates too, so an eastern-
        Pacific drug-boat strike can't union with an Iran-strikes article even
        at high cosine."""
        from app.services.clustering import _locus_set, _locus_conflict
        boat = _locus_set("حمله نظامی آمریکا به قایق قاچاق مواد مخدر در شرق اقیانوس آرام")
        iran = _locus_set("حملات ایران به پایگاه‌های نظامی آمریکا؛ سپاه")
        assert "americas" in boat and "iran" in iran
        assert _locus_conflict(boat, iran) is True
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        # geo-gate present inside the union-find loop
        assert '"loci": _locus_set(title),  # #6' in src

    def test_roundup_headlines_are_aggregation(self):
        """#4: multi-topic roundups ('تازه‌ترین خبرهای جهان', 'چند خبر کوتاه')
        glue onto any cluster — classified aggregation (dropped)."""
        from app.services.content_type import heuristic_classify

        class _Stub:
            def __init__(self, t):
                self.title_original = t
                self.content_text = self.summary = None
                self.url = ""
                self.rss_category = None
        for t in (
            "تازه‌ترین خبرهای جهان دوشنبه ۱۱ خرداد از رادیو بی‌بی‌سی",
            "چند خبر کوتاه از ایران",
        ):
            v = heuristic_classify(_Stub(t))
            assert v is not None and v.label == "aggregation", t

    def test_medoid_centroid_for_large_clusters(self):
        """#5a: large clusters use the medoid (anchored to a real member), not
        the blurry mean, so accretion needs similarity to a concrete article."""
        from app.services.clustering import _compute_centroid, MEDOID_CENTROID_MIN
        assert MEDOID_CENTROID_MIN == 25
        # mean of a big set with one outlier would drift; medoid stays anchored.
        base = [[1.0, 0.0, 0.0]] * 30
        c = _compute_centroid(base)
        assert c and abs(c[0] - 1.0) < 1e-6

    def test_freeze_oversized_exempts_edited_heroes(self):
        """#5b: the size-freeze guardrail freezes auto-grown umbrellas but
        EXEMPTS is_edited (human-curated) stories like the pinned war hero
        Parham chose not to freeze."""
        from app.services import clustering
        assert hasattr(clustering, "freeze_oversized_active_stories")
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        i = src.find("async def freeze_oversized_active_stories")
        body = src[i:i + 1600]
        assert "is_edited.is_(False)" in body
        assert "article_count >= _settings.max_cluster_size" in body
        # wired into the coherence step
        am = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "freeze_oversized_active_stories" in am


class TestC3LearningLoop:
    """The incident ledger + self-review packet (C3, 2026-06-03): the durable
    'learn from mistakes' record. Each real defect becomes an incident mapped to
    the responsible prompt/step; the self-review packet surfaces non-ok canaries
    + open incidents in one read for the chat ritual."""

    def test_incident_ledger_service_exists(self):
        from app.services import incident_ledger as il
        for fn in ("log_incident", "list_incidents", "self_review_packet", "seed_incidents"):
            assert hasattr(il, fn), f"incident_ledger.{fn} missing"
        assert il.INCIDENT_EVENT == "incident"

    def test_seed_incidents_cover_this_sessions_defects(self):
        """The seed ledger must carry the real 2026-06 defects so the loop
        starts populated, each naming its responsible prompt/step."""
        from app.services.incident_ledger import SEED_INCIDENTS
        slugs = {i["slug"] for i in SEED_INCIDENTS}
        assert {
            "pinned-umbrella-accretion",
            "bellwether-demoted-coverage-false-positive",
            "offtopic-label-produces-zero",
        } <= slugs
        for inc in SEED_INCIDENTS:
            # the mapping to a responsible prompt/step is the load-bearing field
            assert inc.get("responsible"), f"incident {inc['slug']} names no responsible step"
            assert inc.get("symptom") and inc.get("root_cause")

    def test_self_review_endpoints_wired(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        for route in ('"/incidents"', '"/incidents/seed"', '"/self-review"'):
            assert route in src, f"self-review route {route} not wired into admin.py"


class TestDoornamaBackfill:
    """2026-06-03: the pinned hero f5088d84 showed bias bullets instead of the
    دورنما prose Parham asked for. ROOT CAUSE: doornama is generated INSIDE the
    per-story summarize loop, but a stable/pinned hero whose article set hasn't
    changed is skipped by the maturity/hash gate — so the doornama block never
    runs for the #1 card. CURE: a decoupled backfill pass at the end of
    step_summarize that generates a briefing for any doornama_top_id missing one,
    driven by the pure predicate doornama.needs_briefing_backfill()."""

    def test_case_2026_06_03_stable_hero_with_narratives_needs_briefing(self):
        """SYMPTOM: #1 hero had narratives but empty briefing_fa, so the card
        fell back to bias bullets. RESPONSIBLE: step_summarize doornama gating."""
        from app.services.doornama import needs_briefing_backfill
        extras = {
            "state_summary_fa": "این سمت ...",
            "diaspora_summary_fa": "آن سمت ...",
            "bias_explanation_fa": "تحلیل ...",
            # no briefing_fa — the exact production state of f5088d84 at 15:00
        }
        assert needs_briefing_backfill(extras) is True

    def test_existing_briefing_is_not_repaid(self):
        """Idempotency: a hero that already has a briefing must be skipped so the
        backfill never re-pays the LLM on a stable day."""
        from app.services.doornama import needs_briefing_backfill
        assert needs_briefing_backfill({
            "state_summary_fa": "x", "briefing_fa": "روایت یکپارچه ...",
        }) is False
        # whitespace-only briefing counts as missing
        assert needs_briefing_backfill({
            "state_summary_fa": "x", "briefing_fa": "   ",
        }) is True

    def test_no_narrative_inputs_means_nothing_to_synthesize(self):
        from app.services.doornama import needs_briefing_backfill
        assert needs_briefing_backfill({}) is False
        assert needs_briefing_backfill(None) is False
        assert needs_briefing_backfill("not a dict") is False

    def test_backfill_pass_wired_into_step_summarize(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "needs_briefing_backfill" in src, "backfill predicate not used in pipeline"
        assert "doornama_backfilled" in src, "backfill stat not reported"


class TestMetaTitleGuardrail:
    """2026-06-03: three homepage stories carried titles like «تحلیل سوگیری در
    پوشش خبری اعدام فتح‌الله آوری و مقایسه رویکرد رسانه‌ها» — describing OUR bias
    analysis instead of the news event. ROOT CAUSE: the title prompt forbids
    those words but gpt-5-mini ignores the negative instruction. CURE: a
    deterministic gate (story_analysis.is_meta_title / pick_clean_title) rejects
    meta-titles at every write site and falls back to a real article headline."""

    def test_case_2026_06_03_real_meta_titles_are_caught(self):
        from app.services.story_analysis import is_meta_title
        for bad in (
            "تحلیل سوگیری در پوشش خبری اعدام فتح‌الله آوری و مقایسه رویکرد رسانه‌ها",
            "تحلیل سوگیری و ارزیابی خبر توافق صلح احتمالی",
            "تحلیل سوگیری و چالش‌های خبری",
        ):
            assert is_meta_title(bad) is True, f"missed meta-title: {bad}"

    def test_real_news_headlines_pass(self):
        from app.services.story_analysis import is_meta_title
        for good in (
            "فتح‌الله آوری، معترض دی‌ماه ۱۴۰۴، اعدام شد",
            "حملات موشکی و پهپادی ایران به کویت؛ ۱ کشته و ۶۳ زخمی",
            "تبادل آتش در تنگه هرمز؛ ترامپ آتش‌بس را اعلام کرد",
        ):
            assert is_meta_title(good) is False, f"false positive on: {good}"

    def test_pick_clean_title_falls_back_to_article_headline(self):
        from app.services.story_analysis import pick_clean_title
        # LLM proposed a meta-title; current is also meta → use the real headline
        out = pick_clean_title(
            "تحلیل سوگیری در پوشش خبری اعدام فتح‌الله آوری",
            "تحلیل سوگیری و چالش‌های خبری",
            ["اعتراضات دی‌ماه ۱۴۰۴؛ فتح‌الله آوری اعدام شد"],
        )
        assert out == "اعتراضات دی‌ماه ۱۴۰۴؛ فتح‌الله آوری اعدام شد"

    def test_pick_clean_title_prefers_clean_proposed(self):
        from app.services.story_analysis import pick_clean_title
        out = pick_clean_title("فتح‌الله آوری اعدام شد", "عنوان قدیمی", ["x"])
        assert out == "فتح‌الله آوری اعدام شد"

    def test_pick_clean_title_returns_none_when_all_meta(self):
        from app.services.story_analysis import pick_clean_title
        assert pick_clean_title("تحلیل سوگیری الف", "پوشش خبری ب", ["مقایسه رویکرد رسانه‌ها"]) is None

    def test_guardrail_wired_at_all_title_write_sites(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        # both summarize paths + QC use the gate
        assert src.count("pick_clean_title") >= 2, "title guardrail missing from a summarize path"
        assert "is_meta_title" in src, "QC path not gated against meta-titles"


class TestNarrativeSampleStratification:
    """2026-06-03: story d8489917 had inside-border articles (and Telegram) yet
    the narrative said «این زیرگروه در مجموعهٔ مقالات حاضر حضوری ندارد». ROOT
    CAUSE: step_summarize_newly_visible sampled the 10 MOST RECENT articles
    (pure recency); on a big story a whole alignment fell outside the sample, so
    the LLM correctly-per-its-input declared that subgroup absent. CURE: both
    summarize paths now stratify the sample by alignment (≥2 slots each)."""

    def test_both_summarize_paths_stratify_by_alignment(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        # main step_summarize uses by_align; newly_visible now uses _by_align too
        assert "by_align" in src and "_by_align" in src, "a summarize path is not stratified"
        assert src.count("slots") >= 2 or src.count("slots_per_align") + src.count("_slots") >= 2, \
            "alignment slotting missing from a summarize path"

    def test_sample_cap_scales_with_story_size(self):
        """Parham 2026-06-04: 10 was too thin for big stories. The cap now
        scales — small stories stay cheap at 10, big ones get 16-20."""
        import auto_maintenance as am
        assert am._summary_sample_cap(0) == 10
        assert am._summary_sample_cap(29) == 10
        assert am._summary_sample_cap(30) == 16
        assert am._summary_sample_cap(59) == 16
        assert am._summary_sample_cap(60) == 20
        assert am._summary_sample_cap(150) == 20
        assert am._summary_sample_cap(None) == 10

    def test_both_summarize_paths_use_scaled_cap(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert src.count("_summary_sample_cap(story.article_count)") >= 2, \
            "scaled cap not applied to both summarize paths"
