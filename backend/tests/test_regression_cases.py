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
        # and the gate must be wired for non-small stories, not just small ones.
        # 2026-07-01: the raw intersection check was made frequency-aware
        # (distinctive_shared = intersection minus over-represented tokens)
        # to stop a saturated word like "ایران" from counting as an anchor
        # during a single dominant story arc — the gate itself must still
        # be present and still require ≥1 shared token for non-small stories.
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        assert "has_anchor" in src and "generic_tokens" in src
        assert "len(distinctive_shared) >= 1" in src

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

    def test_generic_token_exclusion_2026_07_01(self):
        """SYMPTOM (2026-07-01 Niloofar audit): c8933c34, 5a10417d, 8f004864
        each ended up 90%+ off-topic articles because, once a story crossed
        the small-story protection's 10-article threshold, ANY article
        sharing just "ایران"/"آمریکا"/"ترامپ" with the story's corpus passed
        the shared-anchor gate — those tokens appear in nearly every active
        story during a war-saturated news cycle, so they stopped being
        distinctive. FIX: `_compute_generic_tokens` excludes tokens that
        appear in >= GENERIC_TOKEN_STORY_DF (0.15) fraction of this run's
        story signatures from counting as anchors, while leaving genuinely
        rare/distinctive tokens (a name, a specific place) untouched."""
        from app.services.clustering import _compute_generic_tokens, _title_tokens, GENERIC_TOKEN_STORY_DF

        story_titles = [
            "توافق ۱۴ بندی ایران و آمریکا؛ آتش‌بس دو هفته‌ای برقرار شد",
            "ترامپ: آمریکا به سرنگونی بالگرد در تنگه هرمز پاسخ می‌دهد",
            "حملات موشکی ایران به اسرائیل؛ فشار ترامپ بر نتانیاهو",
            "دستور بازداشت افراد مرتبط با پروژه داماد ترامپ در آلبانی",
            "مذاکرات ایران و آمریکا در دوحه؛ بیانیه مجلس خبرگان",
            "ایران هفت موشک به سمت کویت و بحرین شلیک کرد",
            "توافق صلح ایران و آمریکا؛ امضای تفاهم‌نامه در سوئیس",
        ]
        token_sets = [_title_tokens(t) for t in story_titles]
        generic = _compute_generic_tokens(token_sets, GENERIC_TOKEN_STORY_DF)

        # Saturated across most stories in this batch — must be excluded.
        assert "ایران" in generic
        assert "آمریکا" in generic
        assert "ترامپ" in generic
        # Distinctive to a single story — must NOT be excluded, it's a
        # genuine anchor (this is exactly the Kushner/Albania story that
        # otherwise absorbed 27 unrelated articles on generic anchors alone).
        assert "آلبانی" not in generic
        assert "داماد" not in generic

        # An incoming Yemen-missile article shares nothing but "ایران" with
        # the Albania story — with generic tokens excluded, that's no
        # longer a valid anchor.
        incoming = _title_tokens(
            "موشک بالستیک پرتاب‌شده از یمن در نزدیکی مرز با عربستان سعودی سقوط کرد"
        )
        albania_tokens = _title_tokens(
            "دستور بازداشت افراد مرتبط با پروژه داماد ترامپ در آلبانی"
        )
        raw_shared = incoming & albania_tokens
        distinctive_shared = raw_shared - generic
        assert len(distinctive_shared) == 0, (
            "unrelated Yemen article must not anchor onto the Albania story "
            f"once generic tokens are excluded (raw shared: {raw_shared})"
        )

    def test_generic_token_exclusion_empty_input(self):
        """Degenerate input (no stories yet) must not raise or divide by zero."""
        from app.services.clustering import _compute_generic_tokens
        assert _compute_generic_tokens([]) == set()


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


class TestTitleNumericFigureGuidance:
    """2026-07-14 Niloofar audit: two of the war's most-visible homepage
    stories carried titles with a STALE casualty count (the first-seen low
    number from early articles) even though later articles in the same
    cluster reported the Health Ministry's higher running total; a third
    story stated a single-outlet, unconfirmed superlative ("43 million
    funeral attendees", Fars-only) as settled fact. ROOT CAUSE: the title
    prompt told the model to include a number if one existed, but never said
    which number to pick when articles disagree or when only one outlet
    makes an extraordinary claim. Manually patched via journalist_audit.py
    that day; this locks the same guidance into the automated prompt so the
    pattern doesn't require a Niloofar catch every time it recurs."""

    def test_prompt_instructs_latest_official_figure_on_conflict(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        assert "جدیدترین" in STORY_ANALYSIS_PROMPT
        assert "وزارت بهداشت" in STORY_ANALYSIS_PROMPT

    def test_prompt_instructs_attributing_unconfirmed_single_source_figures(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        assert "فقط از یک منبع گزارش شده" in STORY_ANALYSIS_PROMPT
        assert "فارس: حضور" in STORY_ANALYSIS_PROMPT


class TestNarrativeOutletNameConcreteExamples:
    """2026-07-14 Niloofar audit: an outlet name (New York Times) leaked into
    a state/diaspora narrative field despite the general 'no outlet names in
    these fields' rule stated earlier in the prompt. ROOT CAUSE: the rule
    lived only in prose far from the actual output slot, unlike title_fa
    (which restates its banned-words rule WITH a مثال غلط/مثال درست pair
    right in the schema hint — see TestMetaTitleGuardrail). This gives
    state_summary_fa/diaspora_summary_fa the same concrete-example
    reinforcement at the point of generation. A single occurrence isn't
    strong enough evidence for a deterministic strip/reject gate (unlike
    meta-titles, which recurred 3x) — see [[project_grabbag_detection]] on
    why over-eager auto-gates in this codebase have twice been reverted."""

    def test_state_summary_field_has_concrete_wrong_right_example(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        i = STORY_ANALYSIS_PROMPT.find('"state_summary_fa"')
        field = STORY_ANALYSIS_PROMPT[i:i + 700]
        assert "مثال غلط" in field and "مثال درست" in field

    def test_diaspora_summary_field_has_concrete_wrong_right_example(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        i = STORY_ANALYSIS_PROMPT.find('"diaspora_summary_fa"')
        field = STORY_ANALYSIS_PROMPT[i:i + 500]
        assert "مثال غلط" in field and "مثال درست" in field


class TestBiasExplanationGroundingRule:
    """2026-07-14 Niloofar audit: story aa6bac86 (Javad Alikordi, sentenced to
    18 years) had a bias_explanation_fa that included Sharif University
    student-expulsion content — a real event, but from a DIFFERENT story, not
    mentioned in either of this story's 2 actual articles. ROOT CAUSE: the
    'ground every claim in the present articles' rule (قاعدهٔ دوم) explicitly
    listed state_summary_fa/diaspora_summary_fa/independent_summary_fa/the
    subgroup bullets, but never named bias_explanation_fa — the exact field
    where the fabrication landed. This is the 'fabricated relationship trap'
    ([[feedback_niloofar_exhaustive]]) recurring on the generation side, not
    just an audit-catch pattern. Locks bias_explanation_fa into the same
    grounding rule + a same-topic-different-story concrete example."""

    def test_grounding_rule_names_bias_explanation_fa(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        i = STORY_ANALYSIS_PROMPT.find("قاعدهٔ دوم")
        rule = STORY_ANALYSIS_PROMPT[i:i + 900]
        assert "bias_explanation_fa" in rule

    def test_grounding_rule_forbids_similar_but_different_story_content(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        i = STORY_ANALYSIS_PROMPT.find("قاعدهٔ دوم")
        rule = STORY_ANALYSIS_PROMPT[i:i + 900]
        assert "شبیه" in rule  # explicit "even if topically similar" guard

    def test_bias_explanation_field_hint_repeats_the_guard(self):
        from app.services.story_analysis import STORY_ANALYSIS_PROMPT
        i = STORY_ANALYSIS_PROMPT.find('"bias_explanation_fa"')
        field = STORY_ANALYSIS_PROMPT[i:i + 500]
        assert "خبر دیگر" in field


class TestNiloofarFixesStaySummarizeEligible:
    """2026-07-15: apply_fix() (the entire journalist_audit.py --apply-from
    workflow Niloofar audits use) set is_edited=True on every content fix and
    NEVER wrote summary_anchor. admin.py's PATCH /admin/stories/{id} was
    already fixed (its '#6' comment) to move away from that exact
    freeze-forever pattern -- it writes summary_anchor and leaves
    is_edited=False specifically so `(is_edited=False) | (summary_anchor IS
    NOT NULL)`, the eligibility gate both step_summarize and
    step_summarize_newly_visible use, keeps picking the story up. Because
    journalist_audit.py never wrote the anchor, EVERY story a Niloofar audit
    ever touched was silently excluded from automated re-analysis forever --
    its title/bias narrative could only ever go stale again through another
    manual audit. That's the opposite of
    [[feedback_iterative_prompt_improvement]]'s stated goal ('Niloofar role
    should become less needed'): every touch increased future dependency on
    Niloofar instead of decreasing it. CURE: _write_summary_anchor() mirrors
    admin.py's anchor_writers dict. Deliberately does NOT flip is_edited to
    False (unlike admin.py) -- the OR in the gate means writing the anchor
    alone is enough, and leaving is_edited=True preserves the OTHER
    protections that key off it (oversized-active freeze exemption for
    growing pinned war heroes, auto-merge protection) which a growing,
    actively-edited war story still needs."""

    def _apply_fix_source(self) -> str:
        from pathlib import Path
        return (Path(__file__).parent.parent / "scripts" / "journalist_audit.py").read_text()

    def test_anchor_helper_exists_and_sets_anchored_at(self):
        src = self._apply_fix_source()
        assert "def _write_summary_anchor(" in src
        assert 'anchor["anchored_at"]' in src

    def test_content_fix_types_write_the_anchor(self):
        src = self._apply_fix_source()
        body_start = src.find("async def apply_fix(")
        assert body_start != -1
        body = src[body_start:]
        for marker in (
            'fix_type == "rename_story"',
            'fix_type == "update_summary"',
            'fix_type == "update_narratives"',
            'fix_type == "write_preliminary_summary"',
        ):
            i = body.find(marker)
            assert i != -1, f"branch not found: {marker}"
            branch = body[i:i + 6000]
            next_branch = branch.find("\n        elif fix_type ==", 1)
            if next_branch != -1:
                branch = branch[:next_branch]
            assert "_write_summary_anchor(" in branch, f"{marker} never writes the anchor -- silently freezes forever"

    def test_update_image_does_not_write_the_anchor(self):
        """manual_image_url isn't part of the anchor's continuity domain and
        a past bug (feedback_manual_image_vs_is_edited) already showed
        is_edited resets can drop a pinned cover image -- update_image must
        stay untouched by this fix."""
        src = self._apply_fix_source()
        body_start = src.find("async def apply_fix(")
        assert body_start != -1
        body = src[body_start:]
        i = body.find('fix_type == "update_image"')
        assert i != -1
        branch = body[i:i + 800]
        next_branch = branch.find("\n        elif fix_type ==", 1)
        if next_branch != -1:
            branch = branch[:next_branch]
        assert "_write_summary_anchor(" not in branch


class TestHitlNarrativeEndpointStaysSummarizeEligible:
    """2026-07-15: same bug as TestNiloofarFixesStaySummarizeEligible, found
    independently in a THIRD manual-edit code path -- PATCH
    /hitl/stories/{story_id}/narrative (app/api/v1/hitl.py) also set
    is_edited=True with no summary_anchor, permanently excluding any story
    edited through the HITL dashboard's narrative editor from automated
    re-analysis. admin.py's PATCH /admin/stories/{id} (already fixed, its
    own '#6' comment) and admin.py's /admin/stories/seed (already fixed,
    2026-06-03, its own comment references story f5088d84 losing its
    doornama briefing over this exact gap) both already had the correct
    pattern -- it just never propagated to this endpoint. Now shares
    app/services/summary_anchor.apply_editorial_anchor(), created so a
    fourth occurrence requires actively skipping the shared helper rather
    than reinventing (and forgetting) the anchor write."""

    def test_narrative_endpoint_writes_anchor_and_clears_is_edited(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "hitl.py").read_text()
        i = src.find("async def update_story_narrative(")
        assert i != -1
        body = src[i:i + 2500]
        assert "apply_editorial_anchor(" in body
        assert "story.is_edited = False" in body

    def test_shared_anchor_helper_does_not_touch_is_edited(self):
        """The helper must stay call-site-agnostic on is_edited -- the right
        value differs (admin.py/hitl.py want False, journalist_audit.py
        deliberately keeps True for the oversized-freeze exemption)."""
        from app.services.summary_anchor import apply_editorial_anchor
        from types import SimpleNamespace
        story = SimpleNamespace(summary_anchor=None, is_edited=True)
        apply_editorial_anchor(story, title_fa="x")
        assert story.is_edited is True
        assert story.summary_anchor["title_fa"] == "x"
        assert "anchored_at" in story.summary_anchor


class TestRenameStoryCanTranslateToo:
    """2026-07-15: the Niloofar persona doc (item 13, translation parity) has
    told the audit to 'include a new_title_en field in a rename_story payload'
    since it was written — but apply_fix()'s rename_story branch only ever
    read new_title_fa. Any past attempt at that documented workaround was a
    silent no-op: fix_data['new_title_en'] was accepted and ignored, title_en
    stayed stale, and nothing errored. ROOT CAUSE: the only OTHER path that
    can write title_en (write_preliminary_summary) forces a mandatory
    new_summary_fa rewrite, so a plain 'fix the title in both languages'
    edit had no working fix_type at all. CURE: rename_story now writes
    title_en when new_title_en is present in fix_data (optional, backward
    compatible)."""

    def test_rename_story_branch_reads_new_title_en(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "scripts" / "journalist_audit.py").read_text()
        i = src.find('fix_type == "rename_story"')
        branch = src[i:i + 900]
        assert "new_title_en" in branch, "rename_story still can't touch title_en"
        assert "story.title_en" in branch, "rename_story reads new_title_en but never assigns it"


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


class TestStaleAggregatesAfterPostprocess:
    """2026-06-03: story 538d848c sat in نگاه یک‌جانبه (a diaspora-only blindspot,
    0% inside) yet carried a «پوشش درون‌مرزی آغاز شد» badge and served state_pct=17.
    ROOT CAUSE: quality_postprocess (FULL_PIPELINE step 50) drops an article AFTER
    homepage_aggregates (step 31) already recomputed coverage, so the denormalized
    percentages + the downstream update_signal went stale until the next cron.
    CURE: recompute the affected story's aggregates blob right after the removal."""

    def test_recompute_helper_exists(self):
        from app.services import homepage_aggregates as ha
        assert hasattr(ha, "recompute_story_aggregates"), "per-story recompute helper missing"

    def test_quality_postprocess_recomputes_after_removal(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        # the QC step must call the recompute when it drops an article
        assert "recompute_story_aggregates(db, story.id)" in src, \
            "quality_postprocess does not recompute aggregates after flagging an article"
        assert "_removed_any" in src, "article-removal tracking flag missing"


class TestNarrativeContradictionSelfHeal:
    """2026-06-04: stale pinned/umbrella stories kept old narratives that
    contradicted their coverage — د8489917 was 40% inside yet its state side
    said «این زیرگروه … حضوری ندارد». ROOT CAUSE: the analysis was generated
    before the alignment-stratified sample fix and the maturity lock then froze
    it. CURE: step_summarize detects the contradiction and forces a re-analysis
    past the lock (bounded per run); the stratified sample then yields a correct
    narrative, so it converges."""

    def test_case_2026_06_04_absent_state_with_inside_coverage(self):
        from auto_maintenance import narrative_contradicts_coverage
        # د8489917's real state: 40% inside, state narrative says absent.
        assert narrative_contradicts_coverage(
            "این زیرگروه در مجموعهٔ مقالات حاضر حضوری ندارد.", "روایت واقعی برون‌مرزی …",
            40, 60,
        ) == "state"

    def test_genuine_one_sided_story_is_not_flagged(self):
        from auto_maintenance import narrative_contradicts_coverage
        # A real diaspora-only blindspot: 0% inside, state side absent — correct.
        assert narrative_contradicts_coverage(
            "این زیرگروه حضوری ندارد.", "روایت برون‌مرزی واقعی …", 0, 100,
        ) is None

    def test_two_real_narratives_not_flagged(self):
        from auto_maintenance import narrative_contradicts_coverage
        assert narrative_contradicts_coverage(
            "روایت درون‌مرزی واقعی و مفصل …", "روایت برون‌مرزی واقعی …", 40, 60,
        ) is None

    def test_absence_marker_detects_variants(self):
        from auto_maintenance import _narrative_absence_marker
        for t in ("حضوری ندارد", "حضور ندارند", "پوششی درباره این رویداد ندارد",
                  "این زیرگروه نمایندگی ندارد"):
            assert _narrative_absence_marker(t) is True, f"missed: {t}"
        assert _narrative_absence_marker("روایت کامل و واقعی از رویداد") is False
        assert _narrative_absence_marker(None) is False

    def test_self_heal_wired_into_step_summarize(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "narrative_contradicts_coverage(" in src, "contradiction detector not used in pipeline"
        assert "contradiction_fixes" in src, "contradiction self-heal stat not reported"
        assert "MAX_CONTRADICTION_FIXES" in src, "self-heal is not budget-bounded"


class TestSelfRunningInstrumentation:
    """2026-06-05: closing the KPI instrumentation gaps ([[project_self_running_kpis]]).
    (1) detected_by on incidents makes the Human-Intervention-Rate North-Star real;
    (2) article_count_drift gets a self-heal (it had a canary but no fix)."""

    def test_incident_detected_by_and_hir(self):
        from app.services import incident_ledger as il
        assert "human" in il._DETECTORS and "canary" in il._DETECTORS
        assert hasattr(il, "human_intervention_rate"), "HIR computation missing"
        # log_incident must accept detected_by (keyword)
        import inspect
        assert "detected_by" in inspect.signature(il.log_incident).parameters

    def test_seed_incidents_tag_detection_source(self):
        from app.services.incident_ledger import SEED_INCIDENTS
        for inc in SEED_INCIDENTS:
            assert inc.get("detected_by") in ("canary", "human", "audit", "self_heal"), \
                f"seed incident {inc['slug']} not tagged with a detection source"

    def test_admin_incident_schema_has_detected_by(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        assert 'detected_by: str = "unknown"' in src, "POST /incidents can't set detected_by"

    def test_article_count_drift_self_heal_wired(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        # recount now zeroes genuinely-empty stories (the 0-attached drift the
        # canary flagged but recount used to skip)
        assert "emptied_fixed" in src, "recount does not reconcile 0-attached stories"
        assert "NOT EXISTS (SELECT 1 FROM articles" in src, "0-attached reconciliation query missing"
        ha = (Path(__file__).parent.parent / "app" / "services" / "homepage_aggregates.py").read_text()
        # QC-touched stories get their count reconciled immediately
        assert "article_count=_live_articles" in ha, "recompute_story_aggregates doesn't fix article_count"


class TestTelegramQualityPass:
    """2026-06-05: story 9db0e678 (Lebanon ceasefire) showed off-topic + spam
    telegram posts (a Pakistan «ML Strategy» post with «❌🔴🏃‍♀️…سیب دارم چه ۳۰بی»)
    and a 3-camp analyst summary hallucinated from ~1 post. Three fixes:
    (a) disable the per-article link rescue for broad umbrellas, (b) a spam-post
    filter, (c) require ≥2 distinct analyst voices + clear stale analyses."""

    def test_a_broad_umbrella_disables_rescue(self):
        from app.services.telegram_analysis import _broad_umbrella_skips_rescue, BROAD_UMBRELLA_RECENT_ARTICLES
        assert _broad_umbrella_skips_rescue(40) is True   # Lebanon umbrella
        assert _broad_umbrella_skips_rescue(5) is False    # small coherent story
        assert BROAD_UMBRELLA_RECENT_ARTICLES <= 20

    def test_a_rescue_links_need_higher_score(self):
        from app.services.telegram_analysis import _passes_link_threshold, RESCUE_MIN_SCORE
        # a per-article rescue at the base threshold must NOT attach
        assert _passes_link_threshold(0.40, True, 0.35) is False
        # a centroid match at the same score DOES
        assert _passes_link_threshold(0.40, False, 0.35) is True
        # a strong rescue still attaches
        assert _passes_link_threshold(RESCUE_MIN_SCORE + 0.01, True, 0.35) is True

    def test_b_spam_post_filter(self):
        from app.services.telegram_analysis import is_low_quality_telegram_post
        assert is_low_quality_telegram_post("❌🔴🏃‍♀️🏃‍♀️") is True
        assert is_low_quality_telegram_post("🔥🔥🔥🔥🔥🔥 برو") is True
        assert is_low_quality_telegram_post("سلام") is True          # stub
        assert is_low_quality_telegram_post(None) is True
        # real commentary (even with an emoji) is kept
        assert is_low_quality_telegram_post(
            "این آتش‌بس شکست خواهد خورد چون هیچ تضمینی برای اجرای آن نیست 🔥"
        ) is False

    def test_c_floor_and_grounding_wired(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "telegram_analysis.py").read_text()
        # require ≥2 posts AND ≥2 distinct channels
        assert "len(_distinct_channels) < 2" in src, "analyst summary not gated on ≥2 voices"
        # prompt grounding rule: don't invent absent camps
        assert "کمپِ غایب را اختراع نکن" in src, "pass-2 grounding rule missing"
        am = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "cleared_stale" in am, "stale telegram analyses are not cleared when the pool goes thin"


class TestPipelineResilience:
    """2026-06-05: the 15:55 cron failed two steps — summarize greenlet-crashed
    when Neon killed the connection mid-run (an unguarded rollback), and
    audit_clusters timed out at 300s (it does LLM cohesion confirmation now, so
    the 'no LLM / 300s' budget was stale). A long run must degrade gracefully,
    not lose the whole step."""

    def test_summarize_survives_dead_connection(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        # the per-story failure path must guard its rollback and break, not
        # let a failing rollback greenlet-crash the step
        assert "returning partial results" in src, "summarize does not degrade gracefully on connection loss"

    def test_audit_clusters_timeout_raised(self):
        from pathlib import Path
        import re
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        m = re.search(r'"audit_clusters":\s*(\d+)', src)
        assert m and int(m.group(1)) >= 600, "audit_clusters timeout must be >= 600s (LLM cohesion confirm)"


class TestPoliticalSportsOverride:
    """2026-06-06: a MAJOR Iran story — US visa diplomacy around the World Cup
    football team (NYT / White House / sanctions) — was dropped as off_topic
    because the sports blocklist contains «تیم ملی فوتبال»; 12 articles never
    clustered and the story never reached the site. CURE: a diplomatic-signal
    override so political-football news classifies as news, while routine match
    reports stay off_topic."""

    def _mk(self, t):
        from types import SimpleNamespace
        return SimpleNamespace(title_fa=t, title_original=t, content_text="", summary="", url="", rss_category="")

    def test_visa_diplomacy_football_is_not_offtopic(self):
        from app.services.content_type import heuristic_classify
        for t in (
            "تیم ملی فوتبال ایران در جام جهانی مجوز ویزای آمریکا دریافت کرد",
            "الجزیره: آمریکا به ۱۵ عضو کادر تیم ملی ویزا نداد",
            "مهدی تاج: پاسپورت‌ها را به سفارت آمریکا دادیم",
        ):
            v = heuristic_classify(self._mk(t))
            label = getattr(v, "label", v)
            assert label != "off_topic", f"diplomatic football story dropped as off_topic: {t}"

    def test_pure_sports_still_offtopic(self):
        from app.services.content_type import heuristic_classify
        for t in (
            "تیم ملی فوتبال ایران برابر پرتغال به پیروزی رسید",
            "لیگ برتر فوتبال؛ پرسپولیس قهرمان شد",
        ):
            v = heuristic_classify(self._mk(t))
            label = getattr(v, "label", v)
            assert label == "off_topic", f"routine sports leaked as non-off_topic: {t}"

class TestMergeProtectionAndGrabbagDetection:
    """2026-06-06: the cron's merge step absorbed a hand-seeded, priority-50
    visa story into a 35-article war umbrella («visa؛ drones»), erasing the
    pin. Parham caught it by EYE — detection-source ratio was 0.0, because
    the homepage_grabbag canary only fires at >= 120 articles, so the 35-art
    grab-bag sailed under it.

    Two-part fix:
      PREVENT — merge-protect is_edited / pinned stories (see
                test_clustering_safety.py::TestMergeProtectsPinnedStories).
      DETECT  — a mid-size grab-bag canary (this class) so the NEXT one trips
                a signal instead of needing Parham's eyes ([[project_self_running_kpis]]
                Pillar 4 Detection)."""

    def _admin_src(self):
        from pathlib import Path
        return (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()

    def test_midsize_grabbag_canary_exists(self):
        src = self._admin_src()
        assert '"midsize_grabbag_risk"' in src, "mid-size grab-bag canary not registered"

    def test_canary_targets_the_gap_below_120(self):
        src = self._admin_src()
        # Must cover the band the >=120 homepage_grabbag canary misses.
        assert "BETWEEN :lo AND :hi" in src
        assert '"lo": 12' in src and '"hi": 119' in src, \
            "mid-size band must be 12-119 (the gap below the 120 grab-bag canary)"

    def test_canary_uses_persian_semicolon_tell_on_auto_titles(self):
        src = self._admin_src()
        # The grab-bag tell: an auto-generated compound title joining two
        # events with «؛». Scoped to is_edited = FALSE so hand-curated
        # compound titles don't false-positive.
        assert "title_fa LIKE '%؛%'" in src, "canary must use the «؛» compound-title tell"
        assert "is_edited = FALSE" in src, \
            "canary must scope to auto-titled stories so hand-edited «؛» titles are excluded"

    def test_canary_surfaces_in_self_review(self):
        # self_review_packet reuses health_overview canaries, so the new
        # canary feeds the detection-source ratio with no extra wiring.
        from pathlib import Path
        il = (Path(__file__).parent.parent / "app" / "services" / "incident_ledger.py").read_text()
        assert "from app.api.v1.admin import health_overview" in il

class TestManualImagePreservedAcrossResummarize:
    """2026-06-07: Parham set a story image; it reverted after every cron.
    Cause: step_summarize rebuilt the summary_en blob from scratch and
    dropped the manual_image_url override that the read-time path
    (stories.py / hitl.py) relies on. The admin force-resummarize path
    preserved it; the cron's three summarize paths did not. All three must
    carry manual_image_url forward now."""

    def _src(self):
        from pathlib import Path
        return (Path(__file__).parent.parent / "auto_maintenance.py").read_text()

    def test_all_summarize_paths_preserve_manual_image(self):
        src = self._src()
        # At least 3 carry-forward sites in step_summarize (Path 1, Path 2,
        # Path 3) — one per re-analysis path that rewrites summary_en.
        n = src.count("manual_image_url")
        assert n >= 3, (
            f"expected manual_image_url preserved in all 3 cron summarize "
            f"paths, found {n} reference(s)"
        )

    def test_stale_clear_exempts_curated_stories(self):
        src = self._src()
        # The stale_cleared path nulls summary_en — it MUST stay scoped to
        # is_edited=False so a curated story (manual images flip is_edited)
        # never has its image wiped here.
        idx = src.find("story.summary_en = None")
        assert idx > 0, "stale_cleared null-out (summary_en = None) not found"
        # the SELECT guarding the null-out is just above it
        window = src[max(0, idx - 1200):idx]
        assert "Story.is_edited.is_(False)" in window, (
            "stale_cleared null-out must remain scoped to is_edited=False"
        )

    def test_read_time_override_still_trusted(self):
        from pathlib import Path
        st = (Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py").read_text()
        assert 'get("manual_image_url")' in st, (
            "read-time path must still apply the manual_image_url override"
        )

class TestImageQualityPicker:
    """2026-06-07: the auto cover-image picker kept choosing low-quality
    thumbnails because its only tiebreaker was URL length. image_quality_score
    gives it a real URL-derived quality signal so big article photos win over
    thumbnails / logos. Used by both homepage_aggregates._pick_image (cron →
    blob) and the stories.py read-time scorer."""

    def test_large_beats_thumbnail(self):
        from app.services.homepage_aggregates import image_quality_score as q
        big = q("https://cdn.example.com/news/photo-1200x800.jpg")
        thumb = q("https://cdn.example.com/news/photo-150x150.jpg")
        assert big > thumb, f"large({big}) should outrank thumbnail({thumb})"

    def test_thumbnail_markers_penalized(self):
        from app.services.homepage_aggregates import image_quality_score as q
        assert q("https://x.com/thumb/a.jpg") < q("https://x.com/a.jpg")
        assert q("https://x.com/large/a.jpg") > q("https://x.com/a.jpg")

    def test_width_query_hint(self):
        from app.services.homepage_aggregates import image_quality_score as q
        assert q("https://img.x.com/a.jpg?w=1200") > q("https://img.x.com/a.jpg?w=120")

    def test_picker_prefers_quality_over_stable_thumbnail(self):
        # A stable (R2) 150px thumbnail must NOT beat a 1200px article photo.
        from types import SimpleNamespace
        from app.config import settings
        from app.services import homepage_aggregates as ha
        r2 = settings.r2_public_url or "https://r2.example.com"
        story = SimpleNamespace(title_fa="حمله موشکی به پایگاه", title_en=None)
        thumb = SimpleNamespace(
            image_url=f"{r2}/cover-150x150.jpg",
            title_fa="حمله موشکی به پایگاه", title_original=None, title_en=None,
            source=SimpleNamespace(slug="a", logo_url=None, is_active=True),
        )
        big = SimpleNamespace(
            image_url="https://news.example.com/photo-1200x800.jpg",
            title_fa="حمله موشکی به پایگاه", title_original=None, title_en=None,
            source=SimpleNamespace(slug="b", logo_url=None, is_active=True),
        )
        url, real = ha._pick_image(story, [thumb, big])
        assert real is True
        assert url == big.image_url, f"picker chose {url!r}, expected the 1200px photo"

    def test_avatar_and_sprite_filtered(self):
        from app.services.homepage_aggregates import _is_bad_image
        assert _is_bad_image("https://x.com/users/avatar123.jpg")
        assert _is_bad_image("https://x.com/assets/sprite.png")
        assert not _is_bad_image("https://x.com/news/real-photo-1200x800.jpg")

class TestActiveFrozenStoriesNotBuried:
    """2026-06-09: the Iran–Israel war (ongoing ~30 days, 40+ fresh
    articles/day) was frozen for being >7d old, demoted to priority -50,
    and BURIED for days under a stale pinned hero — with no un-demote
    path, so it stayed stuck. step_demote_umbrella_stories is now
    activity-aware: a frozen story still absorbing fresh coverage is NOT
    sunk, and one already at -50 that's breaking again is re-promoted.
    Sort-order only — freeze still blocks new articles, so the
    runaway-umbrella protection is intact ([[project_freshness_buries_active_wars]])."""

    def _src(self):
        from pathlib import Path
        return (Path(__file__).parent.parent / "auto_maintenance.py").read_text()

    def _demote_body(self):
        src = self._src()
        i = src.find("async def step_demote_umbrella_stories")
        assert i >= 0
        j = src.find("\nasync def ", i + 50)
        return src[i:j if j > 0 else len(src)]

    def test_demote_is_activity_aware(self):
        b = self._demote_body()
        assert "ACTIVE_MIN_ARTICLES" in b and "ACTIVE_WINDOW_DAYS" in b, \
            "demote step must gate on recent article activity"
        # Counts recent articles per candidate via published_at window.
        assert "Article.published_at >= window_start" in b

    def test_active_frozen_story_is_exempt_and_repromoted(self):
        b = self._demote_body()
        assert 'stats["repromoted"]' in b, "must re-promote frozen-but-active stories stuck at -50"
        assert 'stats["exempt_active"]' in b, "must exempt active frozen stories from demotion"
        assert "story_umbrella_repromoted" in b, "re-promotion must log an event"
        # Re-promotion lifts back to priority 0.
        assert "values(priority=0)" in b

    def test_demote_still_respects_pins_and_manual_hide(self):
        b = self._demote_body()
        # Candidate range excludes manual pins (>0) and the -100 hide.
        assert "Story.priority <= 0" in b and "Story.priority > -100" in b

    def test_freeze_semantics_unchanged(self):
        # The fix must NOT touch frozen_at or let new articles join — it
        # only changes priority. Guard: no frozen_at writes in the body.
        b = self._demote_body()
        assert "frozen_at = " not in b and "values(frozen_at" not in b, \
            "demote step must not alter freeze state — sort-order only"

class TestCanaryIncidentSync:
    """2026-06-10: the detection-source ratio was stuck at 0.0 even though the
    midsize_grabbag canary was actively firing — because canary catches were
    never written to the ledger. step_sync_canary_incidents auto-logs a
    detected_by='canary' incident on transition so the ratio can finally move
    ([[project_self_running_kpis]] Pillar 4)."""

    def test_sync_function_and_step_exist(self):
        from app.services import incident_ledger as il
        assert hasattr(il, "sync_canary_incidents")
        assert hasattr(il, "INCIDENT_WORTHY_CANARIES")
        import auto_maintenance as m
        assert hasattr(m, "step_sync_canary_incidents")

    def test_step_wired_into_pipeline_near_end(self):
        import auto_maintenance as m
        keys = [k for k, _, _ in m.FULL_PIPELINE]
        assert "canary_incident_sync" in keys, "canary sync step not in FULL_PIPELINE"
        # Runs just before delete_aged (which must stay last per strict
        # retention) so it observes essentially final pipeline state.
        assert keys[-1] == "delete_aged"
        assert keys[keys.index("canary_incident_sync") + 1] == "delete_aged"

    def test_only_quality_canaries_are_incident_worthy(self):
        from app.services.incident_ledger import INCIDENT_WORTHY_CANARIES
        # The content-quality signals must be covered…
        assert {"midsize_grabbag_risk", "homepage_grabbag", "bellwether_missing_story",
                "trending_freshness", "article_count_drift"} <= INCIDENT_WORTHY_CANARIES
        # …and operational/cost noise must NOT be (would inflate the ratio).
        for noisy in ("rss_silent_7d", "translation_orphan_articles",
                      "translation_cost_rate_24h", "maintenance_fails_last_run"):
            assert noisy not in INCIDENT_WORTHY_CANARIES

    def test_transition_only_logging(self):
        # Source guard: the sync only logs when status flips (prev not already
        # open for a firing canary), so a persistent canary doesn't spam a new
        # row every cron and game the row-counted ratio.
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "incident_ledger.py").read_text()
        i = src.find("async def sync_canary_incidents")
        body = src[i:i + 3000]
        assert "prev_open" in body and "if not prev_open" in body, \
            "sync must be transition-only (check prev open state before logging)"
        assert 'detected_by="canary"' in body

class TestBreakingNewsUnclusteredCanary:
    """2026-06-11: the US–Iran war coverage (helicopter→US strikes→Iran
    retaliation) arrived in the ingest but stayed story_id=NULL, so the
    breaking story never reached the homepage and Parham caught the stale
    hero by eye (detection-source ratio = 0.0). The breaking_news_unclustered
    canary measures the fresh orphan BACKLOG so this class of miss is caught
    by a signal next time ([[project_self_running_kpis]] Pillar 2)."""

    def test_canary_registered(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        assert '"breaking_news_unclustered"' in src, "canary id missing from health_overview"
        # Measures the orphan backlog past one cluster pass (6h–48h window),
        # not the just-arrived cohort, so normal between-cron lag doesn't trip it.
        assert "INTERVAL '48 hours'" in src and "INTERVAL '6 hours'" in src
        assert "a.story_id IS NULL" in src

    def test_canary_mirrors_clustering_gate(self):
        """Canary-name-is-a-contract (feedback_canary_design): the orphan count
        MUST mirror the clustering candidate gate (clustering.py ~L2943) — only
        content_type-set + allowed-list + cluster_attempts<3 articles 'should'
        be in a story. The first version counted bare story_id IS NULL and
        false-alarmed at 68% on design-orphans (opinion/off-topic/in-flight)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        i = src.find('_orphan_window = ')
        body = src[i:i + 900]
        assert "a.content_type IS NOT NULL" in body
        assert "content_filters -> 'allowed'" in body and "to_jsonb(a.content_type)" in body
        assert "a.cluster_attempts < 3" in body

    def test_canary_is_incident_worthy(self):
        from app.services.incident_ledger import INCIDENT_WORTHY_CANARIES
        assert "breaking_news_unclustered" in INCIDENT_WORTHY_CANARIES

    def test_canary_has_rate_gate(self):
        """WARN only when BOTH the count AND the rate are high — a bare count
        would fire during quiet periods, a bare rate during tiny windows."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        i = src.find('"breaking_news_unclustered"')
        body = src[i:i + 1200]
        assert "fresh_orphan >= 25 and fresh_orphan_pct >= 30" in body


class TestTrendingFreshnessMeasuresActivity:
    """2026-06-10: trending_freshness fired RED (9.5d) during the Iran-Israel
    war — a FALSE alarm. It measured story-START age (first_published_at), but
    after the activity-aware demote fix, a 30-day war that's updated daily
    legitimately sits in trending. The canary must measure LAST ACTIVITY
    (last_updated_at), or it's permanently red during any long active story."""

    def _admin_src(self):
        from pathlib import Path
        return (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()

    def test_age_computed_from_last_updated(self):
        src = self._admin_src()
        i = src.find("oldest_trending_age_days = 0.0")
        block = src[i:i + 900]
        # The query selects (first_published_at, last_updated_at, ...) = tr[0], tr[1].
        # Freshness must come from last activity (tr[1]), not story-start (tr[0]).
        assert "pub = tr[1] or tr[0]" in block, (
            "trending_freshness must measure last_updated_at (activity), not "
            "first_published_at — else it false-fires during long active wars"
        )

    def test_query_still_excludes_frozen(self):
        # The canary set is non-frozen trending stories; that invariant stays.
        src = self._admin_src()
        i = src.find("trending_rows = ")
        block = src[i:i + 400]
        assert "frozen_at IS NULL" in block
        assert "last_updated_at" in block  # column must be selected to use tr[1]

class TestBlindspotLabelSelfHealAndCanary:
    """2026-06-10: «نگاه یک‌جانبه» showed only ONE card while the
    blindspot_fresh_pool canary read 9/green. Cause: is_blindspot/blindspot_type
    are set once at clustering time and never recomputed, so stories tagged
    state_only had drifted to ~56% diaspora; the homepage (which re-checks live
    percentages) refused them, but the canary counted the stale label. Two
    fixes: (a) self-heal the label from live source pcts each cron; (b) the
    canary counts per-side by the SAME live gate the frontend uses."""

    def test_blindspot_from_pcts(self):
        from app.services.homepage_aggregates import blindspot_from_pcts
        assert blindspot_from_pcts(90, 10) == (True, "state_only")
        assert blindspot_from_pcts(5, 80) == (True, "diaspora_only")
        # The drifted case that broke the page: tagged state_only but 44/56.
        assert blindspot_from_pcts(44, 56) == (False, None)
        assert blindspot_from_pcts(50, 50) == (False, None)
        # Loose boundary mirrors the frontend (>=70 / <=30).
        assert blindspot_from_pcts(70, 30) == (True, "state_only")

    def test_self_heal_wired_into_both_write_paths(self):
        from pathlib import Path
        ha = (Path(__file__).parent.parent / "app" / "services" / "homepage_aggregates.py").read_text()
        am = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        # recompute_story_aggregates (QC path) writes the healed label.
        assert "is_blindspot=_is_blind" in ha and "blindspot_type=_blind_type" in ha
        # The cron homepage_aggregates step writes it too.
        assert "blindspot_from_pcts" in am and "is_blindspot=_is_blind" in am

    def test_canary_counts_per_side_by_live_pcts(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        # Per-side counts using live homepage_aggregates percentages, not the
        # stale is_blindspot label.
        assert "blind_state_side" in src and "blind_diaspora_side" in src
        assert "(homepage_aggregates->>'state_pct')::numeric >= 70" in src
        # Canary goes non-green when EITHER side is empty.
        assert "min(hp_blind_state, hp_blind_diaspora) < 1" in src


class TestEmbeddingNullCanariesMirrorNlpGate:
    """2026-06-11: the dashboard warned «266/610 (43.6%) NULL embedding — NLP
    degraded» on a HEALTHY system. The H2 issue and /admin/embedding/health
    counted every ingested article, but non-allowed content types (off_topic/
    opinion/…) never reach the embedder — NULL by design (the same
    design-orphan trap as breaking_news_unclustered). Both probes must mirror
    the eligibility gate in nlp_pipeline.process_unprocessed_articles, like
    the health-overview embedding_null_rate_24h canary already does."""

    GATE = "content_filters -> 'allowed') @> to_jsonb(a.content_type)"

    def _admin_src(self):
        from pathlib import Path
        return (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()

    def test_dashboard_h2_counts_eligible_only(self):
        src = self._admin_src()
        i = src.find("# H2 — embedding null rate")
        body = src[i:i + 1400]
        assert i != -1
        assert self.GATE in body
        assert "a.content_type IS NOT NULL" in body
        # Message says what it now measures.
        assert "NLP-eligible articles" in body

    def test_embedding_health_endpoint_counts_eligible_only(self):
        src = self._admin_src()
        i = src.find('@router.get("/embedding/health")')
        body = src[i:i + 3600]
        assert i != -1
        assert self.GATE in body
        # null_pct / zero_pct are rates over the ELIGIBLE denominator.
        assert "max(1, eligible)" in body
        # Design-skips and unclassified rows stay visible, separately.
        assert "skipped_by_design" in body and "pending_classification" in body


class TestMaintenanceLogsEndpointSurvivesEditorialRows:
    """2026-06-11: POST /admin/weekly-digest stores raw Persian markdown in
    maintenance_logs.results (status='weekly_digest'). GET /maintenance/logs
    json.loads()'ed every row, so the day after an editorial post the whole
    listing died with a misleading «create the maintenance_logs table» hint —
    breaking verification step 3."""

    def _admin_src(self):
        from pathlib import Path
        return (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()

    def test_editorial_statuses_excluded_from_listing(self):
        src = self._admin_src()
        i = src.find('@router.get("/maintenance/logs")')
        body = src[i:i + 2600]
        assert i != -1
        assert "status NOT IN ('weekly_digest', 'weekly_digest_ops')" in body

    def test_per_row_parse_is_defensive(self):
        src = self._admin_src()
        i = src.find('@router.get("/maintenance/logs")')
        body = src[i:i + 2600]
        # One bad row must not take down the listing.
        assert "_safe_json" in body and "_unparsed" in body


class TestRssShortDeletionsPerSourceVisibility:
    """2026-06-11 funnel review: the drop-short step deleted 316/319 RSS-stub
    articles with no per-source visibility. An outlet whose full-text fetch
    systematically fails (geo-block, URL change) publishes stub feeds → every
    article deleted → the outlet silently vanishes from coverage. The step now
    reports rss_short_by_source so one outlet dominating the list is visible
    in the run stats."""

    def test_breakdown_present_in_drop_short_step(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        i = src.find("SHORT_THRESHOLD = 400")
        body = src[i:i + 3200]
        assert i != -1
        assert "rss_short_by_source" in body
        assert "JOIN sources s ON s.id = a.source_id" in body


class TestPerStepCpuInstrumentation:
    """2026-06-12: Railway compute audit showed maintenance-cron burning
    ~as much vCPU as the 24/7 API despite ~100 min/day of runtime — the
    same optimizing-blind problem the Phase F.1 egress meter solved.
    The run loop now records RUSAGE_SELF deltas per step (`_cpu` next to
    `_egress`) so the CPU-reduction work targets measured hot spots, not
    guesses."""

    def test_cpu_meter_wired_into_step_loop(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "RUSAGE_SELF" in src
        i = src.find('result["_cpu"]')
        assert i != -1, "_cpu stats missing from step result"
        body = src[i:i + 300]
        assert "user_s" in body and "sys_s" in body
        # Snapshot must happen BEFORE the step runs (next to tup_before).
        assert src.find("_cpu_before = _resource.getrusage") < src.find("step_t0 = time.time()")


class TestRssShortSignalVsNoiseSplit:
    """2026-06-14 deep-dive: the drop-short step reported a raw
    `rss_short_deleted` (141/142 on a healthy run) that read as a
    catastrophe but was ~92% expected off_topic/opinion pruning — the NLP
    gate never fetches full text for non-news, so those orphans are SUPPOSED
    to be deleted. The honest signal is only NLP-eligible (news) articles
    that got here, meaning their full-text fetch genuinely failed. The step
    now splits the number: `rss_short_news_deleted` (the real loss),
    `rss_short_by_type` (full transparency), and an ELIGIBLE-ONLY
    `rss_short_by_source` so a dominating outlet signals a broken fetch
    instead of lighting up on expected noise. Same false-alarm class as the
    NULL-embedding / design-orphan canaries."""

    def test_news_vs_noise_split_present(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        i = src.find("SHORT_THRESHOLD = 400")
        body = src[i:i + 3200]
        assert i != -1
        # the eligibility predicate must mirror the NLP gate exactly
        assert "(s.content_filters -> 'allowed') @> to_jsonb(a.content_type)" in body
        assert "was_eligible" in body
        assert "rss_short_news_deleted" in body
        assert "rss_short_by_type" in body
        # per-source breakdown is now eligible-only
        assert "if row.was_eligible:" in body


class TestBellwetherLogsEvidence:
    """2026-06-14: the bellwether canary logged only its verdict
    (missing/missed_story/confidence), so a `missing=true conf 0.9` flag was
    un-actionable — nobody could tell a real coverage gap from the comparator
    failing to credit an umbrella story for a sub-angle. The check now
    persists the lead headlines it saw (`outlet_leads`) and the titles it
    compared against (`compared_titles`) into the logged event signals."""

    def test_evidence_fields_persisted(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "bellwether.py").read_text()
        assert 'result["outlet_leads"]' in src
        assert 'result["compared_titles"]' in src
        # evidence must be captured before the LLM verdict so it persists
        # even when the comparator returns None / errors.
        assert src.find('result["outlet_leads"]') < src.find("verdict = await _llm_compare")


class TestBellwetherFiltersSportsNoise:
    """2026-06-14: the bellwether false-positived (missing=true conf 0.9) on a
    story we clearly covered. Logged evidence showed why: Iran International's
    homepage <h2>/<h3> led with World Cup headlines (جام جهانی، فیفا، ورزشگاه)
    during a tournament, crowding the real Iran-US lead out of the top-10 slice
    fed to the LLM. _extract_headlines now drops sports/entertainment + site
    chrome so the political/conflict leads survive."""

    def test_sports_and_nav_dropped_real_news_kept(self):
        from app.services.bellwether import _extract_headlines
        html = (
            "<title>صفحه اصلی | ایران اینترنشنال</title>"
            "<h2>جام جهانی ۲۰۲۶؛ کوراسائو در آستانه یک رکورد تاریخی</h2>"
            "<h2>مهدی تاج: آمریکا به پروتکل‌های فیفا پایبند نبوده است</h2>"
            "<h3>خبرهای کوتاه</h3>"
            "<h2>توافق احتمالی ایران و آمریکا در ژنو؛ تجمعات مخالفان در تهران</h2>"
            "<h3>حملات اسرائیل به ضاحیه بیروت؛ سه کشته بر جای گذاشت</h3>"
        )
        heads = _extract_headlines(html)
        joined = " || ".join(heads)
        assert "جام جهانی" not in joined and "فیفا" not in joined
        assert "صفحه اصلی" not in joined and "خبرهای کوتاه" not in joined
        assert any("توافق احتمالی ایران و آمریکا" in h for h in heads)
        assert any("حملات اسرائیل به ضاحیه" in h for h in heads)


class TestBellwetherPromptRequiresClosestExisting:
    """2026-06-14 follow-up: tighten the comparator so it must name the closest
    existing aggregator title before declaring a story missing, and bias toward
    missing=false on doubt — the un-credited-umbrella false-alarm class. The
    closest_existing field is persisted as the LLM's own justification."""

    def test_prompt_and_field_present(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "bellwether.py").read_text()
        assert "closest_existing" in src
        # the verdict must persist the justification field
        assert 'result["closest_existing"]' in src
        # prompt must instruct naming the closest title + the doubt→false bias
        assert "closest" in _COMPARE_PROMPT_TEXT(src).lower()
        assert "missing=false" in _COMPARE_PROMPT_TEXT(src).lower() or "missing=FALSE" in _COMPARE_PROMPT_TEXT(src)


def _COMPARE_PROMPT_TEXT(src: str) -> str:
    i = src.find("_COMPARE_PROMPT = ")
    return src[i:i + 1600] if i != -1 else ""


class TestBellwetherClosestExistingGuardrail:
    """2026-06-15: even with the tightened prompt, gpt-4.1-nano named an EXACT
    match in our titles («…۱۱ موشک به سمت تل‌آویو…», #13 in compared_titles)
    yet still returned missing=true. The deterministic guardrail suppresses the
    flag when the LLM's own closest_existing strongly overlaps one of our
    titles — we don't trust its boolean over its own evidence. Must NOT suppress
    a genuinely different (low-overlap) closest title."""

    def test_exact_match_suppresses_false_positive(self):
        from app.services.bellwether import _closest_matches_ours
        ours = [
            "توافق احتمالی ایران و آمریکا در ژنو",
            "حملات اسرائیل به جنوب لبنان؛ کشته شدن یک مقام محلی",
            "حملات موشکی ایران به اسرائیل؛ ۱۱ موشک به سمت تل‌آویو شلیک شد",
        ]
        # the exact self-contradiction case from the 2026-06-15 run
        assert _closest_matches_ours(
            "حملات موشکی ایران به اسرائیل؛ ۱۱ موشک به سمت تل‌آویو شلیک شد", ours
        )
        # lightly reworded / glyph-variant echo still matches
        assert _closest_matches_ours(
            "حملات موشكي ايران به اسراييل: ۱۱ موشك به سمت تل آويو", ours
        )

    def test_different_event_not_suppressed(self):
        from app.services.bellwether import _closest_matches_ours
        ours = [
            "توافق احتمالی ایران و آمریکا در ژنو",
            "حملات موشکی ایران به اسرائیل؛ ۱۱ موشک به سمت تل‌آویو شلیک شد",
        ]
        # a real gap the LLM couldn't match to anything close
        assert not _closest_matches_ours("اعتصاب سراسری معلمان در ۳۰ شهر ایران", ours)
        assert not _closest_matches_ours("", ours)


class TestManualImageNotGatedOnIsEdited:
    """2026-06-14: a manually-pinned cover image (`manual_image_url` in the
    summary_en blob, written by update_image) stopped being served whenever
    a story got a title/summary edit. Cause: the editorial system migrated
    from freeze-forever (is_edited=True) to the refreshable summary_anchor
    model, which deliberately sets is_edited=False — but the read-time image
    override still gated on is_edited=True, so the edit silently dropped the
    operator's chosen image and fell through to the auto-picked aggregate.
    The override must honor manual_image_url whenever present + valid,
    independent of is_edited (which is exactly what _pick_image defers to)."""

    def test_manual_image_override_independent_of_is_edited(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py").read_text()
        i = src.find('candidate = _blob.get("manual_image_url")')
        assert i != -1, "manual_image_url override missing"
        # the guard immediately preceding the override must NOT gate on is_edited
        guard = src[max(0, i - 260):i]
        assert "is_edited" not in guard, (
            "manual_image override re-gated on is_edited — a title/summary edit "
            "will silently drop the operator's pinned cover image again"
        )


class TestContentExtractionTitleOverlapGuard:
    """2026-07-16: trafilatura extracted the identical unrelated
    boilerplate text ("Dey-month prisoners" widget) from two different
    iranintl.com article URLs with different titles and different page
    sizes — a wrong-page-extraction bug, not a fetch failure (both
    fetches returned HTTP 200 with distinct content). 6 articles were
    silently contaminated in production before this was caught. Fixed
    by rejecting extracted content that shares zero distinctive terms
    with the article's own title, falling back to the RSS summary
    instead of storing cross-contaminated text."""

    def test_rejects_content_with_no_title_overlap(self):
        from app.services.nlp_pipeline import _extraction_matches_title
        title = "ترامپ: آمریکا نگهبان تنگه هرمز خواهد بود؛ قرارگاه خاتم‌الانبیا: اجازه نمی‌دهیم"
        wrong_content = (
            "شاهدان عینی گفتند زندانیان به آب گرم، جای خواب کافی و دارو "
            "دسترسی ندارند و در معرض انواع بیماری‌ها قرار گرفته‌اند."
        )
        assert _extraction_matches_title(wrong_content, title) is False

    def test_accepts_content_with_title_overlap(self):
        from app.services.nlp_pipeline import _extraction_matches_title
        title = "حملات تازه آمریکا به بندر لنگه یک کشته و دو زخمی به جا گذاشت"
        matching_content = (
            "حملات تازه آمریکا به بندر لنگه یک کشته و دو زخمی به جا گذاشت "
            "در حملات تازه آمریکا به مناطقی در جنوب ایران یک نفر کشته شد."
        )
        assert _extraction_matches_title(matching_content, title) is True

    def test_empty_title_does_not_block(self):
        from app.services.nlp_pipeline import _extraction_matches_title
        assert _extraction_matches_title("some content", None) is True
        assert _extraction_matches_title("some content", "") is True

    def test_guard_wired_into_extraction_loop(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "nlp_pipeline.py").read_text()
        i = src.find("if not article.content_text and article.url:")
        assert i != -1
        window = src[i:i + 700]
        assert "_extraction_matches_title" in window, (
            "content-extraction loop no longer calls the title-overlap guard "
            "before storing extracted content"
        )


class TestEmbeddingJsonbNoneAsNull:
    """2026-07-16: Article.embedding is a nullable JSONB column. Without
    none_as_null=True, SQLAlchemy serializes `article.embedding = None`
    as the JSONB *value* `null`, not SQL NULL -- `embedding IS NULL`
    (used by the sentinel-column retry gate and the dedup pool query in
    process_unprocessed_articles) silently fails to match those rows.
    A row "cleared" this way passed `embedding.isnot(None)` in the dedup
    pool query, then crashed cosine_similarity with a Python None instead
    of a vector, taking down the whole step_process batch."""

    def test_embedding_column_uses_none_as_null(self):
        from app.models.article import Article
        from sqlalchemy.dialects.postgresql import JSONB
        col_type = Article.__table__.c.embedding.type
        assert isinstance(col_type, JSONB)
        assert col_type.none_as_null is True, (
            "Article.embedding lost none_as_null=True -- `.embedding = None` "
            "will silently store a JSONB null value instead of SQL NULL again"
        )

    def test_dedup_loop_skips_non_list_embeddings(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "nlp_pipeline.py").read_text()
        i = src.find("for recent_id, recent_emb in recent_pool:")
        assert i != -1
        window = src[i:i + 900]
        assert "isinstance(recent_emb, list)" in window, (
            "dedup loop no longer guards against malformed (non-list) "
            "embeddings before calling cosine_similarity -- one bad row "
            "can crash the entire step_process batch"
        )


class TestOrphanArticleDeletionRespectsReclusterWindow:
    """2026-07-19: step_delete_aged's orphan-article branch
    (`Article.story_id.is_(None)`) had NO age condition -- it deleted
    EVERY currently-unclustered article on EVERY cron run, including
    ones ingested minutes earlier in that same run. This silently
    defeated step_recluster_orphans's entire retry design
    (MIN_ORPHAN_AGE_HOURS=6, retried up to a 7-day aged_out_cutoff):
    an orphan could never survive long enough to reach the 6h
    eligibility floor, because delete_aged (last step, same cron fire)
    removed it first. Confirmed live via hra-news (a real human-rights
    RSS source publishing several articles/day but averaging only ~1
    successfully-clustered article per week) and maintenance-log spikes
    of 148-271 single-run deletions. Fix: gate the orphan branch on the
    same grace_cutoff (7 days) already used for story-level retention,
    matching step_recluster_orphans's own retry ceiling."""

    def test_orphan_branch_is_age_gated(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        idx = src.find("async def step_delete_aged")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        block = src[idx:next_def if next_def > 0 else idx + 9000]
        i = block.find("Article.story_id.in_(delete_story_list)")
        assert i != -1, "step_delete_aged's article deletion query moved or was renamed"
        window = block[i:i + 300]
        assert "Article.story_id.is_(None)" in window
        assert "grace_cutoff" in window, (
            "step_delete_aged's orphan-article branch is missing an age "
            "gate -- it will delete every unclustered article on every "
            "run again, defeating step_recluster_orphans's 6h-7d retry "
            "window before any orphan can reach it"
        )

    def test_recluster_orphans_min_age_unchanged(self):
        # Sanity anchor: the fix assumes MIN_ORPHAN_AGE_HOURS=6 is the
        # eligibility floor an orphan must survive to. If this constant
        # changes, re-check that delete_aged's grace_cutoff still gives
        # recluster_orphans room to run before deletion.
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "MIN_ORPHAN_AGE_HOURS = 6" in src


class TestPruneNoiseRequiresClassificationBeforeDeletion:
    """2026-07-19: step_prune_noise's second pass (RSS-origin orphans
    with short/null content_text) fired on ANY orphan >1h old,
    regardless of content_type -- so an article still sitting in the
    classify_content_type or step_process queue (content_type IS NULL,
    never even looked at yet) was treated identically to a confirmed
    stub. Maintenance logs showed single-run spikes of 148-271
    deletions where ~95% were content_type IS NULL. Fix: require
    content_type IS NOT NULL (classify_content_type drains up to
    1200/run, so this is a fast and reliable "was this actually looked
    at" signal) and raise the age floor 1h->6h to match
    MIN_ORPHAN_AGE_HOURS, giving step_process's smaller 50/run
    extraction batch room to catch up first."""

    def test_second_pass_requires_classification_and_six_hour_floor(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        i = src.find("SHORT_THRESHOLD = 400")
        assert i != -1
        body = src[i:i + 1200]
        assert "a.content_type IS NOT NULL" in body, (
            "prune_noise's second pass no longer requires content_type "
            "IS NOT NULL -- it will delete never-classified backlog "
            "again instead of confirmed stubs"
        )
        assert "INTERVAL '6 hours'" in body, (
            "prune_noise's second pass age floor regressed below the "
            "6h MIN_ORPHAN_AGE_HOURS alignment"
        )
        assert "INTERVAL '1 hour'" not in body
