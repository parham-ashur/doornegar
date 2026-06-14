// ─── Homepage picking logic ─────────────────────────────────────────
// Extracted from HomeBody.tsx (2026-06-12) so the selection policy is
// testable in isolation. Everything here is pure: no React, no fetch,
// no Date.now() — callers pass `nowMs` so tests can pin the clock.
// The render component (HomeBody) fetches data, calls
// computeHomepagePicks() + buildBattleItems(), and only does JSX.
//
// Editorial policy lives in HOMEPAGE_POLICY below — windows and
// thresholds that used to be magic numbers inline.

import type { StoryBrief } from "@/lib/types";

// The per-story analysis shape the homepage reads (subset of the
// /stories/analyses batch payload). HomeBody's fetchers return this.
export type StoryAnalysisBrief = {
  summary_fa?: string;
  briefing_fa?: string | null;
  bias_explanation_fa?: string;
  state_summary_fa?: string;
  diaspora_summary_fa?: string;
  dispute_score?: number;
  loaded_words?: { conservative: string[]; opposition: string[] };
};

export type AnalysesById = Record<string, StoryAnalysisBrief | null>;

// ─── Editorial age windows + thresholds ─────────────────────────────
// F1 — tiered freshness windows. The site's editorial intent is
// "anything older than ~7 days is dated; ~30 days is dead." Each
// homepage section gets its own cutoff so older content silently
// falls off the prime slots even when picks would otherwise be empty.
export const HOMEPAGE_POLICY = {
  HERO_MAX_AGE_MS: 72 * 3600 * 1000,        // 3d — hero must be hot
  HERO_DROUGHT_AGE_MS: 26 * 86400 * 1000,   // 26d — last-resort hero only when nothing fresher exists
  BLINDSPOT_MAX_AGE_MS: 7 * 86400 * 1000,   // 7d — F7 mirror
  DISPUTE_MAX_AGE_MS: 14 * 86400 * 1000,    // 14d — disputed slot
  BRIEFING_MAX_AGE_MS: 14 * 86400 * 1000,   // 14d — weekly briefing
  POPULAR_MAX_AGE_MS: 14 * 86400 * 1000,    // 14d — pop-score
  // Drought widen (2026-05-31): recovery fallback shared by the battle /
  // briefing / popular boxes when the strict window can't fill the slots
  // (e.g. the May cron lockdown left most stories 16-25d old).
  // Auto-tightens the moment fresh content returns.
  DROUGHT_AGE_MS: 26 * 86400 * 1000,
  // 80/20 is the threshold for "one-sided enough to be worth calling out
  // as a نگاه یک‌جانبه" — anything balanced beyond that erodes the
  // meaning of the slot.
  ONE_SIDED_MAJOR: 80,
  ONE_SIDED_MINOR: 20,
  // Backend-flagged blindspots get a looser live re-validation: the
  // backend already classified them as one-sided, we just confirm the
  // split hasn't flipped.
  ONE_SIDED_MAJOR_LOOSE: 70,
  ONE_SIDED_MINOR_LOOSE: 30,
} as const;

// ─── Story predicates ───────────────────────────────────────────────

// Skip stories that only have a source-logo fallback as their cover.
// Per Parham's rule, a story without a real image should never surface
// on the homepage. `has_real_image` is undefined on older cached
// responses; treat undefined as "assume true".
export const hasImage = (s: StoryBrief): boolean => s.has_real_image !== false;

export const ageMs = (s: StoryBrief, nowMs: number): number => {
  const src = s.last_updated_at || s.first_published_at;
  if (!src) return Number.POSITIVE_INFINITY;
  const t = Date.parse(src);
  return Number.isFinite(t) ? nowMs - t : Number.POSITIVE_INFINITY;
};

export const hasUpdate = (s: StoryBrief): boolean => !!s.update_signal?.has_update;

// Manual-pin override (Parham 2026-05-04): a story with priority > 0
// is the operator's explicit declaration that this IS the hero.
export const isPinned = (s: StoryBrief): boolean => (s.priority ?? 0) > 0;

// ─── Localized title ────────────────────────────────────────────────
/**
 * Pick the display title for a story based on the active locale.
 * Preference order:
 *   1. translations[locale].title — the higher-quality voice-tuned
 *      story-level translation when it exists.
 *   2. title_{en|fa} — flat per-language fields (article-level).
 *   3. The other locale as a last resort so the page never goes empty.
 */
export function localizedStoryTitle(
  story: {
    title_fa?: string | null;
    title_en?: string | null;
    translations?: Record<string, { title?: string | null } | null> | null;
  },
  locale: string,
): string {
  const tl = story.translations?.[locale]?.title;
  if (tl) return tl;
  if (locale === "fa") return story.title_fa || story.title_en || "";
  // en, fr — prefer flat title_en (article-level), fall back to FA.
  return story.title_en || story.title_fa || "";
}

// ─── Update-badge helpers ───────────────────────────────────────────

export function toFaDigits(n: number): string {
  return String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

// Age-correct burst reason text. The backend writes "N مقاله جدید در
// ساعت گذشته" at cron time, but we display the signal for up to 4h.
// Stretch the window to match real time elapsed.
export function formatUpdateReason(
  sig: NonNullable<StoryBrief["update_signal"]>,
  nowMs: number = Date.now(),
): string | null {
  if (sig.kind === "burst" && typeof sig.new_count === "number" && sig.detected_at) {
    const ageMs = nowMs - new Date(sig.detected_at).getTime();
    const ageH = ageMs / 3600000;
    if (ageH > 0.5) {
      const windowH = Math.max(1, Math.ceil(ageH) + 1);
      return `${toFaDigits(sig.new_count)} مقاله جدید در ${toFaDigits(windowH)} ساعت گذشته`;
    }
  }
  return sig.reason_fa;
}

// F5 — orange "بروزرسانی" badge auto-expires after 24 hours. The
// trigger doesn't get re-evaluated until the next maintenance tick, so
// we TTL the rendered badge on the read side based on `detected_at`.
export const UPDATE_BADGE_TTL_MS = 24 * 3600 * 1000;

export function isUpdateBadgeFresh(
  sig: NonNullable<StoryBrief["update_signal"]> | null | undefined,
  nowMs: number = Date.now(),
): boolean {
  if (!sig?.has_update) return false;
  if (!sig.detected_at) return true; // legacy rows without detected_at — render once, falls off naturally on next refresh
  const t = Date.parse(sig.detected_at);
  if (!Number.isFinite(t)) return true;
  return nowMs - t < UPDATE_BADGE_TTL_MS;
}

// Defense-in-depth (Parham 2026-06-03): a stale coverage-shift signal
// can outlive the articles that triggered it. A badge that contradicts
// the current split is worse than no badge, so suppress a «… آغاز/
// تقویت شد» reason when the side it names has ~no current coverage.
export function coverageBadgeContradicts(story: StoryBrief): boolean {
  const sig = story.update_signal;
  if (!sig?.has_update || sig.kind !== "coverage_shift") return false;
  const r = sig.reason_fa || "";
  if (!r.includes("شد") || r.includes("کمرنگ")) return false; // only "began/strengthened"
  const inside = story.inside_border_pct ?? story.state_pct ?? 0;
  const outside = story.outside_border_pct ?? story.diaspora_pct ?? 0;
  if (r.includes("درون‌مرزی") && inside <= 2) return true;
  if (r.includes("برون‌مرزی") && outside <= 2) return true;
  return false;
}

export function showCoverageBadge(story: StoryBrief, nowMs: number = Date.now()): boolean {
  return isUpdateBadgeFresh(story.update_signal, nowMs) && !coverageBadgeContradicts(story);
}

// ─── Narrative-quality gates ────────────────────────────────────────

// Meta/absence statements masquerading as narratives. A summary that
// only says "this side has no coverage here" is not a narrative — it
// must not reach the تقابل روایت‌ها box (2026-06-04: «این زیرگروه …
// حضوری ندارد» leaked into تقابل with a contradictory state side).
export const META_PATTERNS: RegExp[] = [
  /^پوشش\s+(برون‌مرزی|درون‌مرزی)/,
  /روایت[^.]{0,40}(متمایز|شکل\s+نگرفت|غایب)/,
  /هیچ\s+رسانه/,
  /در\s+این\s+(خبر|مجموعه)[^.]{0,20}حضور\s+ندارن/,
  /رسانه[^.]{0,50}حضور\s+ندار/,
  /حضور[ی]?\s+ندار/,
  /پوششی[^.]{0,30}ندار/,
  /زیرگروه[^.]{0,40}(ندار|نیست|غایب)/,
];

export const hasTwoRealNarratives = (
  a: { state_summary_fa?: string | null; diaspora_summary_fa?: string | null } | null | undefined,
): boolean => {
  if (!a) return false;
  const ss = (a.state_summary_fa || "").trim();
  const ds = (a.diaspora_summary_fa || "").trim();
  if (ss.length < 60 || ds.length < 60) return false;
  for (const re of META_PATTERNS) {
    if (re.test(ss) || re.test(ds)) return false;
  }
  return true;
};

// ─── Battle (تقابل روایت‌ها) word lists ─────────────────────────────

export const buildWordList = (ws: string[]): string[] => {
  // Strip «», dedupe, drop too-short, sort shortest-first so the first
  // paint shows the most compact word; cap at 6 so the rotation cycle
  // doesn't stretch into minutes on noisy stories.
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of ws) {
    const w = raw.replace(/[«»]/g, "").trim();
    if (w.length < 3) continue;
    if (seen.has(w)) continue;
    seen.add(w);
    out.push(w);
  }
  out.sort((a, b) => a.length - b.length);
  return out.slice(0, 6);
};

// Cross-card variety (2026-05-31): the diaspora framing vocabulary
// genuinely converges — «سرکوب» / «حقوق بشر» recur across most
// government stories. preferUnused reorders each story's list to lead
// with a word no prior card has shown yet, falling back to the
// shortest-first order only when every word is already taken.
export const preferUnused = (ws: string[], used: Set<string>): string[] => {
  const fresh = ws.filter(w => !used.has(w));
  const stale = ws.filter(w => used.has(w));
  const ordered = fresh.length ? [...fresh, ...stale] : ws;
  if (ordered[0]) used.add(ordered[0]);
  return ordered;
};

export type BattleItem = {
  storyId: string;
  title: string;
  // Lists of distinct loaded words, sorted shortest-first. RotatingWord
  // cycles through them with a fade animation; if a story only yielded
  // one word the component renders it static (no flicker).
  conservativeWords: string[];
  oppositionWords: string[];
  stateSummary: string;
  diasporaSummary: string;
};

/**
 * Build the تقابل روایت‌ها cards from the reserved stories.
 *
 * Called AFTER the EN/FR translation hoist in HomeBody mutates the
 * analyses map — so the card text (and the re-run narrative gate) sees
 * the locale's translated summaries, while the original reservation in
 * computeHomepagePicks gated on the FA text. Keep that call order.
 */
export function buildBattleItems(
  battleReserved: StoryBrief[],
  analyses: AnalysesById,
  locale: string,
): BattleItem[] {
  const battleItems: BattleItem[] = [];
  const usedOppWords = new Set<string>();
  const usedConsWords = new Set<string>();
  for (const story of battleReserved) {
    if (battleItems.length >= 4) break;
    const analysis = analyses[story.id];
    if (!analysis) continue;
    if (!hasTwoRealNarratives(analysis)) continue;
    const words = analysis.loaded_words;
    const stateSummary = analysis.state_summary_fa || "";
    const diasporaSummary = analysis.diaspora_summary_fa || "";
    const biasText = analysis.bias_explanation_fa;
    if (words?.conservative?.length && words?.opposition?.length) {
      const cw = buildWordList(words.conservative);
      const ow = buildWordList(words.opposition);
      if (cw.length && ow.length) {
        battleItems.push({
          storyId: story.id,
          title: localizedStoryTitle(story, locale) || "",
          conservativeWords: preferUnused(cw, usedConsWords),
          oppositionWords: preferUnused(ow, usedOppWords),
          stateSummary,
          diasporaSummary,
        });
        continue;
      }
    }
    if (biasText) {
      const quotes = biasText.match(/«[^»]+»/g);
      if (quotes && quotes.length >= 2) {
        // Bias-text fallback: split the matched quotes into halves so each
        // side still gets a list to rotate through (instead of a single
        // word). Shortest-first ordering happens inside buildWordList.
        const half = Math.floor(quotes.length / 2);
        const cw = buildWordList(quotes.slice(0, Math.max(half, 1)));
        const ow = buildWordList(quotes.slice(Math.max(half, 1)));
        if (cw.length && ow.length) {
          battleItems.push({
            storyId: story.id,
            title: localizedStoryTitle(story, locale) || "",
            conservativeWords: preferUnused(cw, usedConsWords),
            oppositionWords: preferUnused(ow, usedOppWords),
            stateSummary,
            diasporaSummary,
          });
          continue;
        }
      }
    }
  }
  return battleItems;
}

// ─── The homepage picks ─────────────────────────────────────────────

export type HomepagePicks = {
  conservativeBlind: StoryBrief | undefined;
  oppositionBlind: StoryBrief | undefined;
  hero: StoryBrief | undefined;
  battleReserved: StoryBrief[];
  leftTextStories: StoryBrief[];
  mostViewed: (StoryBrief & { _popScore: number })[];
};

/**
 * Compute every homepage slot from the fetched data. Pure — pass the
 * clock in. Sections reserve stories in a fixed order (blindspots →
 * hero → تقابل → «در روزهای گذشته» → پرمخاطب‌ترین) via a shared
 * usedIds set so no story appears twice.
 *
 * @param stories        trending, already image-filtered
 * @param blindspots     blindspot list, already image-filtered
 * @param blindspotsAll  blindspot list BEFORE the image filter — a
 *                       photo-less one-sided blindspot beats an empty
 *                       slot (diaspora t.me mirrors often have no OG
 *                       image; the card renders the newspaper
 *                       placeholder via the has_real_image gate)
 * @param analyses       per-story analysis map (FA text at this point)
 */
export function computeHomepagePicks({
  stories,
  blindspots,
  blindspotsAll,
  analyses,
  nowMs,
}: {
  stories: StoryBrief[];
  blindspots: StoryBrief[];
  blindspotsAll: StoryBrief[];
  analyses: AnalysesById;
  nowMs: number;
}): HomepagePicks {
  const P = HOMEPAGE_POLICY;
  const age = (s: StoryBrief) => ageMs(s, nowMs);
  const withinAge = (limit: number) => (s: StoryBrief): boolean => age(s) < limit;

  const stateHeavy = (s: StoryBrief) =>
    (s.state_pct || 0) >= P.ONE_SIDED_MAJOR && (s.diaspora_pct || 0) <= P.ONE_SIDED_MINOR;
  const diasporaHeavy = (s: StoryBrief) =>
    (s.diaspora_pct || 0) >= P.ONE_SIDED_MAJOR && (s.state_pct || 0) <= P.ONE_SIDED_MINOR;
  const stateHeavyLoose = (s: StoryBrief) =>
    (s.state_pct || 0) >= P.ONE_SIDED_MAJOR_LOOSE && (s.diaspora_pct || 0) <= P.ONE_SIDED_MINOR_LOOSE;
  const diasporaHeavyLoose = (s: StoryBrief) =>
    (s.diaspora_pct || 0) >= P.ONE_SIDED_MAJOR_LOOSE && (s.state_pct || 0) <= P.ONE_SIDED_MINOR_LOOSE;

  // Blind spots: prefer fresh + has_update (badge explains why it still
  // deserves the slot), then fresh without update (new blindspot), then
  // the unfiltered (photo-less) formal list, then the most heavily
  // one-sided story on that axis — never beyond 7d. Slots stay empty
  // when there's nothing fresh, which is honest signal.
  const blindFresh = withinAge(P.BLINDSPOT_MAX_AGE_MS);
  const conservativeBlind =
    blindspots.find(s => s.blindspot_type === "state_only" && blindFresh(s) && hasUpdate(s) && stateHeavyLoose(s)) ||
    blindspots.find(s => s.blindspot_type === "state_only" && blindFresh(s) && stateHeavyLoose(s)) ||
    blindspotsAll.find(s => s.blindspot_type === "state_only" && blindFresh(s) && stateHeavyLoose(s)) ||
    [...stories].filter(stateHeavy).filter(blindFresh).sort((a, b) =>
      (b.state_pct - b.diaspora_pct) - (a.state_pct - a.diaspora_pct)
    )[0] ||
    undefined;
  const oppositionBlind =
    blindspots.find(s => s.blindspot_type === "diaspora_only" && blindFresh(s) && hasUpdate(s) && diasporaHeavyLoose(s)) ||
    blindspots.find(s => s.blindspot_type === "diaspora_only" && blindFresh(s) && diasporaHeavyLoose(s)) ||
    blindspotsAll.find(s => s.blindspot_type === "diaspora_only" && blindFresh(s) && diasporaHeavyLoose(s)) ||
    [...stories].filter(diasporaHeavy).filter(blindFresh).sort((a, b) =>
      (b.diaspora_pct - b.state_pct) - (a.diaspora_pct - a.state_pct)
    )[0] ||
    undefined;

  // ── Deduplication: track which stories are placed ──
  const usedIds = new Set<string>();
  if (conservativeBlind) usedIds.add(conservativeBlind.id);
  if (oppositionBlind) usedIds.add(oppositionBlind.id);

  const sorted = [...stories];
  const hasBiasNarrative = (s: StoryBrief): boolean => {
    const a = analyses[s.id];
    return !!(a && (a.state_summary_fa || a.diaspora_summary_fa) && a.bias_explanation_fa);
  };

  // Hero picker fallback chain — most specific first so we surface the
  // richest story that qualifies. The bias-narrative gate sits at the
  // top because the hero card is useless without it; once the gate is
  // exhausted we fall through to the older signals so the slot never
  // goes empty on a thin news day. Manual pin (priority > 0) wins
  // outright — still requires bias narrative + 72h freshness so the
  // card isn't visually broken. The drought tail (26d) only fires when
  // every fresher rung is empty (2026-05-31 post-lockdown homepage).
  const heroFresh = withinAge(P.HERO_MAX_AGE_MS);
  const heroSafe = withinAge(P.BRIEFING_MAX_AGE_MS);
  const heroDrought = withinAge(P.HERO_DROUGHT_AGE_MS);
  const hero =
    sorted.find(s => isPinned(s) && hasBiasNarrative(s) && heroFresh(s)) ||
    sorted.find(s => hasBiasNarrative(s) && heroFresh(s) && hasUpdate(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => hasBiasNarrative(s) && heroFresh(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => hasBiasNarrative(s) && heroFresh(s)) ||
    sorted.find(s => hasBiasNarrative(s) && heroSafe(s)) ||
    sorted.find(s => heroFresh(s) && hasUpdate(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => heroFresh(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => heroSafe(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(heroFresh) ||
    sorted.find(heroSafe) ||
    sorted.find(s => heroDrought(s) && hasBiasNarrative(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => heroDrought(s) && hasBiasNarrative(s)) ||
    sorted.find(heroDrought);
  if (hero) usedIds.add(hero.id);

  // ── تقابل روایت‌ها reservation (Parham 2026-06-03) ────────────────
  // The «clash of narratives» box needs two genuinely-opposed sides. On
  // a war-news day EVERY story is two-sided, and the most-viewed /
  // left-text strips below would consume the fresh disputed stories
  // first — so reserve its picks HERE, before those strips.
  const battleGate = (s: StoryBrief, maxAgeMs: number): boolean => {
    if (!(s.state_pct > 0 && s.diaspora_pct > 0) || s.is_blindspot) return false;
    if (usedIds.has(s.id)) return false;
    if (age(s) >= maxAgeMs) return false;
    const a = analyses[s.id];
    if (!hasTwoRealNarratives(a)) return false;
    const lw = a?.loaded_words;
    if (lw?.conservative?.length && lw?.opposition?.length) return true;
    // Bias-text quote fallback (matches buildBattleItems).
    const quotes = a?.bias_explanation_fa?.match(/«[^»]+»/g);
    return !!(quotes && quotes.length >= 2);
  };
  const battleSpread = (a: StoryBrief, b: StoryBrief) =>
    Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct);
  let battleReserved = [...sorted].filter(s => battleGate(s, P.DISPUTE_MAX_AGE_MS)).sort(battleSpread);
  if (battleReserved.length < 3) {
    // Drought widen — same recovery logic as the other boxes.
    battleReserved = [...sorted].filter(s => battleGate(s, P.DROUGHT_AGE_MS)).sort(battleSpread);
  }
  battleReserved = battleReserved.slice(0, 4);
  battleReserved.forEach(s => usedIds.add(s.id));

  // Weekly briefing: left-text "در روزهای گذشته" block. 3 hero-style
  // cards — two-side narratives + telegram strip, no image. ≤14d so
  // this section reflects the past week, not the past month.
  //
  // Selection nudge (Parham 2026-06-14): each entry renders a bias
  // comparison + telegram strip, so a story with no narratives/summary
  // becomes a title-only stub that reads as "empty." Among the eligible
  // pool — already in priority/trending order — surface content-rich
  // stories first. A NUDGE, not a hard filter: it's a stable sort by a
  // richness tier (full two-side comparison > any summary/bias > none),
  // preserving the existing freshness/priority order WITHIN each tier
  // (the `idx` tiebreak), and thin stories still backfill when fewer
  // than 3 rich ones exist. The render side also has a fallback chain
  // (summary_fa → coverage line) so a thin pick is never literally
  // blank — this just leads with the most informative stories.
  const briefingRichness = (s: StoryBrief): number => {
    const a = analyses[s.id];
    if (!a) return 0;
    if (a.state_summary_fa && a.diaspora_summary_fa) return 2; // full درون‌مرزی/برون‌مرزی comparison
    if (a.bias_explanation_fa || (a.summary_fa && a.summary_fa.length > 40)) return 1;
    return 0;
  };
  const pickBriefing = (pool: StoryBrief[]): StoryBrief[] =>
    pool
      .map((s, idx) => ({ s, idx, r: briefingRichness(s) }))
      .sort((a, b) => b.r - a.r || a.idx - b.idx)
      .map(x => x.s)
      .slice(0, 3);
  const briefingFresh = withinAge(P.BRIEFING_MAX_AGE_MS);
  let leftTextStories = pickBriefing(sorted.filter(s => !usedIds.has(s.id) && briefingFresh(s)));
  if (leftTextStories.length < 3) {
    const briefingDrought = withinAge(P.DROUGHT_AGE_MS);
    leftTextStories = pickBriefing(sorted.filter(s => !usedIds.has(s.id) && briefingDrought(s)));
  }
  leftTextStories.forEach(s => usedIds.add(s.id));

  // Most viewed: top 3 by popularity score. ≤14d so a 3-week-old viral
  // story doesn't dominate forever; two drought tiers because
  // popularity accumulates over weeks — the genuinely most-viewed
  // stories are often the 27-30d war umbrellas (Parham 2026-06-04),
  // and retention already caps the DB at 30d, so the final tier is
  // "any homepage-eligible story" rather than letting the box blank.
  const popularFresh = withinAge(P.POPULAR_MAX_AGE_MS);
  let popularPool = [...sorted].filter(s => !usedIds.has(s.id) && popularFresh(s));
  if (popularPool.length < 3) {
    popularPool = [...sorted].filter(s => !usedIds.has(s.id) && withinAge(P.DROUGHT_AGE_MS)(s));
  }
  if (popularPool.length < 3) {
    popularPool = [...sorted].filter(s => !usedIds.has(s.id));
  }
  const mostViewed = popularPool
    .map(s => {
      const views = s.view_count || 0;
      const recencyHours = s.updated_at ? (nowMs - new Date(s.updated_at).getTime()) / 3600000 : 100;
      const recencyBonus = Math.max(0, 1 - recencyHours / 72); // decays over 3 days
      const score = views * 2 + s.trending_score + recencyBonus * 10 + s.article_count * 0.5;
      return { ...s, _popScore: score };
    })
    .sort((a, b) => b._popScore - a._popScore)
    .slice(0, 3);
  mostViewed.forEach(s => usedIds.add(s.id));

  return {
    conservativeBlind,
    oppositionBlind,
    hero,
    battleReserved,
    leftTextStories,
    mostViewed,
  };
}
