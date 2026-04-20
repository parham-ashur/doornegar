import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";
import type { StoryBrief } from "@/lib/types";
import TelegramDiscussions from "@/components/home/TelegramDiscussions";
import WeeklyDigest from "@/components/home/WeeklyDigest";
import { formatRelativeTime, toFa } from "@/lib/utils";
import { predictionText, claimText } from "@/lib/telegram-text";
import { normalizedSidePercentages, independentShare } from "@/lib/narrativeGroups";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Cache TTLs tuned for a homepage where stories update on the hour, not the
// minute. Every miss is a round trip from Vercel (US or EU) to Railway in the
// US, so bumping these from 30/60/120 to 300/600/600 cuts origin pressure
// dramatically without noticeably aging the content.
// TTLs intentionally short: our SSR fetches swallow errors and return
// `{}` / `null` as fallback (so the page still renders partial data when
// the API is slow). Next.js ISR caches those fallback values as if they
// were real, which can leave the homepage stuck on empty-state for up
// to the TTL window. Short TTLs heal that within a few minutes.
const TRENDING_TTL = 300;        // 5 min
const ANALYSIS_TTL = 300;        // 5 min
const TELEGRAM_TTL = 300;        // 5 min

async function fetchAPI<T>(path: string): Promise<T | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`${API}${path}`, { next: { revalidate: TRENDING_TTL }, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchSummary(storyId: string): Promise<string | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: ANALYSIS_TTL } });
    if (!res.ok) return null;
    const data = await res.json();
    return data.summary_fa || null;
  } catch {
    return null;
  }
}

async function fetchAnalysis(storyId: string): Promise<{ summary_fa?: string; bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: ANALYSIS_TTL } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchAnalysesBatch(storyIds: string[]): Promise<Record<string, { summary_fa?: string; bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null>> {
  if (storyIds.length === 0) return {};
  // Dedupe + stable-sort so identical sets share a cache key.
  const ids = Array.from(new Set(storyIds)).sort();
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    const res = await fetch(
      `${API}/api/v1/stories/analyses?ids=${ids.join(",")}`,
      { next: { revalidate: ANALYSIS_TTL }, signal: controller.signal },
    );
    clearTimeout(timeout);
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};
  }
}

async function fetchTelegramAnalysis(storyId: string): Promise<{ discourse_summary?: string; predictions?: any[]; key_claims?: any[]; predictions_display?: any[]; key_claims_display?: any[]; worldviews?: { pro_regime?: string; opposition?: string } } | null> {
  try {
    const controller = new AbortController();
    // 15s timeout: stories without cached analysis regenerate on-demand
    // via a two-pass LLM call that can easily take 10s+. The old 8s cap
    // was aborting those before they finished, dropping the entry from
    // the sidebar pool even when the analysis was about to land.
    const timeout = setTimeout(() => controller.abort(), 15000);
    // 60-second Data Cache window. no-store was pounding Railway with
    // 15 parallel fetches on every SSR (one per top-trending story) and
    // pushing TTFB to 2-3s. A 60s window means worst case ~15 upstream
    // calls per minute per region — light, and after maintenance writes
    // fresh analysis the homepage reflects it inside a minute. Short
    // enough to sidestep the original stuck-cache bug (which was at
    // 300s+) while still batching normal request bursts.
    const res = await fetch(`${API}/api/v1/social/stories/${storyId}/telegram-analysis`, { next: { revalidate: 60 }, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.status !== "ok" || !data.analysis) return null;
    // Homepage prefers Niloofar-polished versions. Raw fields stay for the
    // story detail page where "موضوع: X |" grouping is still useful.
    const a = data.analysis;
    return {
      ...a,
      predictions: a.predictions_display || a.predictions,
      key_claims: a.key_claims_display || a.key_claims,
    };
  } catch {
    return null;
  }
}

function Meta({ story }: { story: StoryBrief }) {
  const published = story.first_published_at
    ? formatRelativeTime(story.first_published_at, "fa")
    : null;
  const updated = story.updated_at
    ? formatRelativeTime(story.updated_at, "fa")
    : null;
  const showUpdated = updated && story.updated_at && story.first_published_at
    && Math.abs(new Date(story.updated_at).getTime() - new Date(story.first_published_at).getTime()) > 3600000;
  // Normalized side percentages always sum to 100 so the reader doesn't
  // see 76% + 22% = 98 and wonder where the other 2 went. Raw state_pct
  // / diaspora_pct leave implicit room for independent outlets (not in
  // either political side); we surface that share in parentheses when
  // it's non-trivial (≥5%).
  const { inside: insidePct, outside: outsidePct } = normalizedSidePercentages(story);
  const indepPct = independentShare(story);
  const hasSides = insidePct > 0 || outsidePct > 0;
  return (
    <div className="mt-1.5" dir="rtl">
      <div className="flex items-center justify-between text-[13px] leading-5">
        <p className="text-slate-400 dark:text-slate-500">
          {toFa(story.source_count)} رسانه · {toFa(story.article_count)} مقاله
          {published && <span>{" · "}نشر {published}</span>}
          {showUpdated && <span>{" · "}به‌روز {updated}</span>}
        </p>
        {hasSides && (
          <p className="shrink-0">
            {insidePct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">درون‌مرزی {toFa(insidePct)}٪</span>}
            {insidePct > 0 && outsidePct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
            {outsidePct > 0 && <span className="text-[#ea580c] dark:text-orange-400">برون‌مرزی {toFa(outsidePct)}٪</span>}
            {indepPct >= 5 && (
              <span className="text-slate-400 dark:text-slate-500">
                {" · "}مستقل {toFa(indepPct)}٪
              </span>
            )}
          </p>
        )}
      </div>
    </div>
  );
}

// "به‌روز" callout showing the sentence-level diff vs last night's
// snapshot. Rendered ABOVE the bias comparison / narrative sides when
// update_signal.delta carries new sentences. Each new fragment is
// shown in a colored (green) background with a "به‌روز" pill at its
// front so the reader can scan what's new without re-reading the
// whole narrative. Empty when nothing changed sentence-level (e.g.
// the trigger was a pct shift rather than a bias rewrite).
function UpdateDeltaCallout({
  story,
  field,
  className = "mb-2",
}: {
  story: StoryBrief;
  field: "bias" | "state" | "diaspora";
  className?: string;
}) {
  const delta = story.update_signal?.delta;
  if (!delta) return null;
  const items: string[] =
    field === "bias" ? delta.bias_new :
    field === "state" ? delta.state_new :
    delta.diaspora_new;
  if (!items || items.length === 0) return null;
  return (
    <div
      dir="rtl"
      className={`${className} border-r-2 border-emerald-500 bg-emerald-50/70 dark:bg-emerald-900/15 px-2.5 py-1.5 space-y-1`}
    >
      {items.map((sentence, i) => (
        <p
          key={i}
          className="text-[13px] leading-5 text-emerald-900 dark:text-emerald-100"
        >
          <span className="inline-block ml-1 align-middle text-[10px] font-black text-emerald-700 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-900/40 px-1 py-0.5">
            به‌روز
          </span>
          {sentence}
        </p>
      ))}
    </div>
  );
}

// Age-correct burst reason text. The backend writes "N مقاله جدید در
// ساعت گذشته" at cron time, but we display the signal for up to 4h.
// Stretch the window to match real time elapsed: articles arrived in
// the [detected_at-1h, detected_at] slice, and we're rendering `age`
// later, so they're actually "within the past ceil(age)+1 hours."
function toFaDigits(n: number): string {
  return String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}
function formatUpdateReason(sig: NonNullable<StoryBrief["update_signal"]>): string | null {
  if (sig.kind === "burst" && typeof sig.new_count === "number" && sig.detected_at) {
    const ageMs = Date.now() - new Date(sig.detected_at).getTime();
    const ageH = ageMs / 3600000;
    if (ageH > 0.5) {
      const windowH = Math.max(1, Math.ceil(ageH) + 1);
      return `${toFaDigits(sig.new_count)} مقاله جدید در ${toFaDigits(windowH)} ساعت گذشته`;
    }
  }
  return sig.reason_fa;
}

// Compact update pill for homepage story cards. Two variants:
//   - Orange "بروزرسانی · <reason>"  — a trigger fired (side flip,
//     coverage shift, burst, or the 24h-snapshot signal). Significant.
//   - Green "مقالهٔ جدید · <time ago>" — a new article was clustered
//     into the story within the last 2 hours but no trigger was
//     significant enough to flag orange. Tells the user the story just
//     got fresh coverage without claiming something major happened.
// If neither condition holds, renders nothing.
function UpdateBadge({ story, className = "mt-1.5" }: { story: StoryBrief; className?: string }) {
  // Orange — significant update
  if (story.update_signal?.has_update) {
    const reason = formatUpdateReason(story.update_signal);
    return (
      <span
        className={`${className} inline-block border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 px-1.5 py-0.5 text-[10px] font-bold text-orange-700 dark:text-orange-300`}
      >
        بروزرسانی{reason ? ` · ${reason}` : ""}
      </span>
    );
  }
  // Green — new article within last 2h, no trigger. `last_updated_at`
  // ticks in step_cluster whenever an article is assigned to the story.
  const lu = story.last_updated_at;
  if (lu) {
    const age = Date.now() - new Date(lu).getTime();
    if (age > 0 && age < 2 * 3600 * 1000) {
      return (
        <span
          className={`${className} inline-block border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300`}
        >
          مقالهٔ جدید · {formatRelativeTime(lu, "fa")}
        </span>
      );
    }
  }
  return null;
}

// ─── Main page ─────────────────────────────────────────────────

export default async function HomePage({
  params: { locale },
  searchParams,
}: {
  params: { locale: string };
  searchParams?: Promise<{ desktop?: string }> | { desktop?: string };
}) {
  setRequestLocale(locale);
  // ?desktop=1 is still honored by the stories-beta carousel's 7th slot
  // iframe; it hides the mobile layout so the desktop layout renders alone.
  const sp = (await Promise.resolve(searchParams)) ?? {};
  const forceDesktop = sp.desktop === "1";
  // Stage 1: all independent fetches in parallel — trending,
  // blindspots, weekly digest. None depend on story IDs.
  const [stories, blindspots, weeklyDigestData] = await Promise.all([
    fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=50").then(d => d || []),
    fetchAPI<StoryBrief[]>("/api/v1/stories/blindspots?limit=10").then(d => d || []),
    fetchAPI<{ status: string; content?: string }>("/api/v1/stories/weekly-digest"),
  ]);

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
        <p className="mt-2 text-sm text-slate-500">پس از اجرای خط‌لوله داده، موضوعات خبری اینجا نمایش داده می‌شوند</p>
      </div>
    );
  }

  // ── Freshness filter + significant-update rule ──────────────────────
  // Parham's rule: a story can stay in the hero or blindspot slot across
  // days ONLY if its narrative has shifted meaningfully since yesterday
  // — "gained new articles" is not enough. The server-side
  // `update_signal.has_update` boolean captures this (dispute_score move
  // ≥ 0.2, or subgroup pct move ≥ 15pp, or ≥3 new articles + rewritten
  // bias comparison). When `has_update` is true, the story is both
  // eligible to repeat AND shown with an orange "بروزرسانی" badge +
  // the delta reason.
  //
  // Combined with the 24h freshness signal (`last_updated_at`), we get
  // three states:
  //   - Fresh + has_update  → prime candidate. Show badge.
  //   - Fresh, no update    → new story in the cluster. Normal hero.
  //   - Stale (>24h)        → not eligible; slot rotates.
  const FRESH_WINDOW_MS = 24 * 60 * 60 * 1000;
  const nowMs = Date.now();
  const isFresh = (s: StoryBrief): boolean => {
    if (!s.last_updated_at) return false;
    const t = Date.parse(s.last_updated_at);
    return Number.isFinite(t) && (nowMs - t) < FRESH_WINDOW_MS;
  };
  const hasUpdate = (s: StoryBrief): boolean => !!s.update_signal?.has_update;

  // Blind spots: prefer fresh + has_update (badge explains why it still
  // deserves the slot), then fresh without update (new blindspot), then
  // fall back to the most recent stale one rather than leave the slot
  // empty — a one-sided story from yesterday is still informative.
  // Formal blindspots (state_only / diaspora_only) come from the backend's
  // classifier. On most news days one side's blindspot bucket is empty —
  // today e.g. 10 state_only, 0 diaspora_only — which would leave the
  // opposite column empty on the homepage. Fall back to the most heavily
  // one-sided story on that axis so both نگاه یک‌جانبه slots always show
  // something, even if the backend hasn't formally flagged it as a
  // blindspot. 60/40 is the pragmatic threshold for "one-sided enough
  // to be worth calling out" without crossing into strict blindspot
  // territory (which the backend reserves for ≥80/20 coverage gaps).
  const ONE_SIDED_MAJOR = 60;  // % covered by the dominant side
  const ONE_SIDED_MINOR = 40;  // % covered by the minority side
  const stateHeavy = (s: StoryBrief) =>
    (s.state_pct || 0) >= ONE_SIDED_MAJOR && (s.diaspora_pct || 0) <= ONE_SIDED_MINOR;
  const diasporaHeavy = (s: StoryBrief) =>
    (s.diaspora_pct || 0) >= ONE_SIDED_MAJOR && (s.state_pct || 0) <= ONE_SIDED_MINOR;

  const conservativeBlind =
    blindspots.find(s => s.blindspot_type === "state_only" && isFresh(s) && hasUpdate(s)) ||
    blindspots.find(s => s.blindspot_type === "state_only" && isFresh(s)) ||
    blindspots.find(s => s.blindspot_type === "state_only") ||
    // Fallback: most extreme state-heavy story among trending.
    [...stories].filter(stateHeavy).filter(isFresh).sort((a, b) =>
      (b.state_pct - b.diaspora_pct) - (a.state_pct - a.diaspora_pct)
    )[0] ||
    [...stories].filter(stateHeavy).sort((a, b) =>
      (b.state_pct - b.diaspora_pct) - (a.state_pct - a.diaspora_pct)
    )[0] ||
    undefined;
  const oppositionBlind =
    blindspots.find(s => s.blindspot_type === "diaspora_only" && isFresh(s) && hasUpdate(s)) ||
    blindspots.find(s => s.blindspot_type === "diaspora_only" && isFresh(s)) ||
    blindspots.find(s => s.blindspot_type === "diaspora_only") ||
    // Fallback: most extreme diaspora-heavy story among trending.
    [...stories].filter(diasporaHeavy).filter(isFresh).sort((a, b) =>
      (b.diaspora_pct - b.state_pct) - (a.diaspora_pct - a.state_pct)
    )[0] ||
    [...stories].filter(diasporaHeavy).sort((a, b) =>
      (b.diaspora_pct - b.state_pct) - (a.diaspora_pct - a.state_pct)
    )[0] ||
    undefined;

  // ── Deduplication: track which stories are placed ──
  const usedIds = new Set<string>();

  // Blind spots first (already picked above)
  if (conservativeBlind) usedIds.add(conservativeBlind.id);
  if (oppositionBlind) usedIds.add(oppositionBlind.id);

  const sorted = [...stories];

  // Pre-fetch analyses for the top-15 trending so the hero picker can
  // require a populated bias comparison. Without this check the hero
  // sometimes landed on a story whose state_summary_fa / diaspora_
  // summary_fa hadn't been generated yet — the card would render with
  // just a title and no two-side narrative, defeating the point of the
  // site. Reusing these analyses below as the primary batch.
  const prefetchIds = sorted.slice(0, 15).map(s => s.id);
  const prefetchedAnalyses = await fetchAnalysesBatch(prefetchIds);
  const hasBiasNarrative = (s: StoryBrief): boolean => {
    const a = prefetchedAnalyses[s.id];
    return !!(a && (a.state_summary_fa || a.diaspora_summary_fa) && a.bias_explanation_fa);
  };

  // Hero picker fallback chain — most specific first so we surface the
  // richest story that qualifies. The bias-narrative gate sits at the
  // top because the hero card is useless without it; once the gate is
  // exhausted we fall through to the older signals so the slot never
  // goes empty on a thin news day.
  const hero =
    sorted.find(s => hasBiasNarrative(s) && isFresh(s) && hasUpdate(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => hasBiasNarrative(s) && isFresh(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => hasBiasNarrative(s) && isFresh(s)) ||
    sorted.find(hasBiasNarrative) ||
    sorted.find(s => isFresh(s) && hasUpdate(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => isFresh(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => isFresh(s) && hasUpdate(s)) ||
    sorted.find(isFresh) ||
    sorted.find(s => s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted[0];
  if (hero) usedIds.add(hero.id);

  // Weekly briefing: left-text "در روزهای گذشته" block. 3 hero-style
  // cards — two-side narratives + telegram strip, no image.
  const leftTextStories = sorted.filter(s => !usedIds.has(s.id)).slice(0, 3);
  leftTextStories.forEach(s => usedIds.add(s.id));

  // Most viewed: top 3. Narrower half-column now (grid-cols-2 cell in
  // row 2), so fewer cards at richer density reads better.
  const now = Date.now();
  const mostViewed = [...sorted]
    .filter(s => !usedIds.has(s.id))
    .map(s => {
      const views = s.view_count || 0;
      const recencyHours = s.updated_at ? (now - new Date(s.updated_at).getTime()) / 3600000 : 100;
      const recencyBonus = Math.max(0, 1 - recencyHours / 72); // decays over 3 days
      const score = views * 2 + s.trending_score + recencyBonus * 10 + s.article_count * 0.5;
      return { ...s, _popScore: score };
    })
    .sort((a, b) => b._popScore - a._popScore)
    .slice(0, 3);
  mostViewed.forEach(s => usedIds.add(s.id));

  // Most disputed: not already used
  const disputedCandidates = [...stories]
    .filter(s => s.state_pct > 0 && s.diaspora_pct > 0 && !s.is_blindspot && !usedIds.has(s.id))
    .sort((a, b) => Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct));
  let mostDisputed = disputedCandidates[0] || null;
  let secondDisputed = disputedCandidates[1] || null;
  let thirdDisputed = disputedCandidates[2] || null;
  if (mostDisputed) usedIds.add(mostDisputed.id);
  if (secondDisputed) usedIds.add(secondDisputed.id);
  if (thirdDisputed) usedIds.add(thirdDisputed.id);

  // Common ground: not already used
  const commonGround = [...stories]
    .filter(s => s.state_pct > 10 && s.diaspora_pct > 10 && !s.is_blindspot && !usedIds.has(s.id))
    .sort((a, b) => Math.abs(a.state_pct - a.diaspora_pct) - Math.abs(b.state_pct - b.diaspora_pct))
    .slice(0, 2);
  commonGround.forEach(s => usedIds.add(s.id));
  // Overflow: everything not yet used
  const overflow = sorted.filter(s => !usedIds.has(s.id));

  // ── Overflow: build sections sequentially, each consuming what it needs ──
  // Section types cycle: text(3) → images(4) → feature(2) → text(3) → images(4) → feature(2)...
  // Odd cycles: mirror the feature rows
  type Section = { type: "text"; stories: StoryBrief[] }
    | { type: "images"; stories: StoryBrief[] }
    | { type: "hero-thumb"; stories: StoryBrief[] }
    | { type: "hero-repeat"; stories: StoryBrief[] };

  const sections: Section[] = [];
  // Pattern: hero-thumb(2) → hero-repeat(4) → text(3)
  const pattern = [
    { type: "hero-thumb" as const, size: 2 },
    { type: "hero-repeat" as const, size: 4 },
    { type: "text" as const, size: 3 },
  ];
  let cursor = 0;

  // Only one cycle, then stop
  for (const step of pattern) {
    if (cursor >= overflow.length) break;
    const chunk = overflow.slice(cursor, cursor + step.size);
    if (chunk.length === 0) break;
    sections.push({ type: step.type, stories: chunk } as Section);
    cursor += chunk.length;
  }

  // ── Batch-fetch all analyses the homepage needs in ONE backend call ──
  // Was: N parallel GET /stories/{id}/analysis (up to ~30+ round trips).
  // Now: single GET /stories/analyses?ids=... — one RTT, shared cache key.
  const allIds = new Set<string>();
  if (hero) allIds.add(hero.id);
  for (const s of [...leftTextStories, ...mostViewed, ...overflow, ...disputedCandidates]) {
    allIds.add(s.id);
  }
  for (const sec of sections) {
    for (const s of sec.stories) allIds.add(s.id);
  }
  // ── Parallel stage 2: analyses + telegram + hero telegram ──
  // All of these need story IDs from stage 1 but are independent of
  // each other. Running them in a single Promise.all cuts the critical
  // path from 4 sequential stages (~5s) to 2 (~3s).
  //
  // Telegram source pool: top-15 trending fresh stories (falling back to
  // plain top-15 if fewer than 3 fresh). Only 17 analysts cover most of
  // Iran's news, so commentary is sparse — top-5 often had 2-3 stories
  // with no_data (hero + slot-4 today), leaving the sidebar empty even
  // though other stories further down had rich analysis. 15 gives enough
  // depth that the sidebar picks up whatever IS available; the component
  // only renders what it gets, so extra slots are free.
  const freshTopStories = sorted.filter(isFresh);
  const telegramSourceStories = freshTopStories.length >= 3 ? freshTopStories : sorted;
  const telegramAnalysisIds = telegramSourceStories.slice(0, 15).map(s => s.id);
  // leftTextStories AND mostViewed both get telegram strips now, so
  // fetch their analyses in parallel with everything else. Each group
  // goes into its own lookup map indexed by story id.
  // Only fetch analyses we don't already have from the hero-picker prefetch.
  const missingIds = Array.from(allIds).filter(id => !(id in prefetchedAnalyses));
  // Always call fetchAnalysesBatch (it short-circuits on empty input) so the
  // Promise.all union type stays concrete. Earlier I used Promise.resolve({})
  // as the shortcut which widened the type to {} and broke build-time TS.
  const [extraAnalyses, heroTelegram, telegramResults, leftTextTelegramResults, mostViewedTelegramResults] = await Promise.all([
    fetchAnalysesBatch(missingIds),
    hero ? fetchTelegramAnalysis(hero.id) : Promise.resolve(null),
    Promise.all(telegramAnalysisIds.map(id => fetchTelegramAnalysis(id))),
    Promise.all(leftTextStories.map(s => fetchTelegramAnalysis(s.id))),
    Promise.all(mostViewed.map(s => fetchTelegramAnalysis(s.id))),
  ]);
  const allAnalyses = { ...prefetchedAnalyses, ...extraAnalyses };
  const leftTextTelegramById: Record<string, any> = {};
  leftTextStories.forEach((s, i) => {
    if (leftTextTelegramResults[i]) leftTextTelegramById[s.id] = leftTextTelegramResults[i];
  });
  const mostViewedTelegramById: Record<string, any> = {};
  mostViewed.forEach((s, i) => {
    if (mostViewedTelegramResults[i]) mostViewedTelegramById[s.id] = mostViewedTelegramResults[i];
  });

  const allSummaries: Record<string, string | null> = {};
  for (const id of Array.from(allIds)) {
    allSummaries[id] = allAnalyses[id]?.summary_fa || null;
  }

  // Re-sort disputed candidates by dispute_score (higher = more disputed), falling back to pct gap
  const disputedResorted = [...disputedCandidates].sort((a, b) => {
    const scoreA = allAnalyses[a.id]?.dispute_score ?? null;
    const scoreB = allAnalyses[b.id]?.dispute_score ?? null;
    if (scoreA !== null && scoreB !== null) return scoreB - scoreA;
    if (scoreA !== null) return -1;
    if (scoreB !== null) return 1;
    return Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct);
  });
  mostDisputed = disputedResorted[0] || null;
  secondDisputed = disputedResorted[1] || null;
  thirdDisputed = disputedResorted[2] || null;

  // Pre-compute تقابل روایت‌ها battle items here so we can exclude those
  // story IDs from بیشترین اختلاف نگاه below. Without this, both boxes
  // on the right column pulled from the same top-2 disputed stories,
  // producing duplicate cards. Each story should appear in at most one
  // of the two boxes (the third — "most visited" — is allowed to repeat).
  type BattleItem = {
    storyId: string;
    title: string;
    conservative: string;
    opposition: string;
    stateSummary: string;
    diasporaSummary: string;
  };
  const battleItems: BattleItem[] = [];
  const pickShort = (ws: string[]): string => {
    const cleaned = ws.map(w => w.replace(/[«»]/g, "").trim()).filter(w => w.length >= 4);
    if (!cleaned.length) return ws[0]?.replace(/[«»]/g, "") || "";
    cleaned.sort((a, b) => a.length - b.length);
    return cleaned[0];
  };
  // Scan the top 6 disputed candidates so we can still fill 2 battle
  // items when the very top story lacks loaded_words / bias quotes.
  for (const story of disputedResorted.slice(0, 6)) {
    if (battleItems.length >= 2) break;
    const analysis = allAnalyses[story.id];
    if (!analysis) continue;
    const words = analysis.loaded_words;
    const stateSummary = analysis.state_summary_fa || "";
    const diasporaSummary = analysis.diaspora_summary_fa || "";
    const biasText = analysis.bias_explanation_fa;
    if (words?.conservative?.length && words?.opposition?.length) {
      battleItems.push({
        storyId: story.id,
        title: story.title_fa || "",
        conservative: `«${pickShort(words.conservative)}»`,
        opposition: `«${pickShort(words.opposition)}»`,
        stateSummary,
        diasporaSummary,
      });
      continue;
    }
    if (biasText) {
      const quotes = biasText.match(/«[^»]+»/g);
      if (quotes && quotes.length >= 2) {
        battleItems.push({
          storyId: story.id,
          title: story.title_fa || "",
          conservative: quotes[0],
          opposition: quotes[1],
          stateSummary,
          diasporaSummary,
        });
        continue;
      }
    }
  }
  const battleIds = new Set(battleItems.map(b => b.storyId));

  // بیشترین اختلاف نگاه: next disputed stories not already claimed by
  // the battle box above. Falls back to the mostDisputed/secondDisputed
  // set when the exclusion leaves nothing, so the box doesn't disappear
  // on stories with no loaded_words.
  const disputedForLowerBox = disputedResorted.filter(s => !battleIds.has(s.id)).slice(0, 2);
  const mostDisputedBottom = disputedForLowerBox[0] || null;
  const secondDisputedBottom = disputedForLowerBox[1] || null;

  const prefetchedTelegram: { storyId: string; analysis: any }[] = [];
  telegramAnalysisIds.forEach((id, i) => {
    if (telegramResults[i]) prefetchedTelegram.push({ storyId: id, analysis: telegramResults[i] });
  });

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-0 md:px-6 lg:px-8">

      {/* ════════════════════════════════════════════ */}
      {/* MOBILE LAYOUT — original scrolling list (phones only) */}
      {/* The new stories-carousel design is available at /stories-beta */}
      {/* while we iterate on it. Swap back here when ready. */}
      {/* ════════════════════════════════════════════ */}
      {!forceDesktop && (
        <MobileHome
          hero={hero}
          stories={sorted}
          summaries={allSummaries}
          locale={locale}
          conservativeBlind={conservativeBlind}
          oppositionBlind={oppositionBlind}
          allAnalyses={allAnalyses}
          heroTelegram={heroTelegram}
          prefetchedTelegram={prefetchedTelegram}
        />
      )}

      {/* ════════════════════════════════════════════ */}
      {/* DESKTOP LAYOUT (tablet and up, or force-enabled) */}
      {/* ════════════════════════════════════════════ */}
      <div className={forceDesktop ? "block" : "hidden md:block"}>

      {/* ═══ TOP SECTION: Blind spots | Hero | Telegram ═══ */}
      <div className="grid grid-cols-12 gap-0 border-b-2 border-slate-300 dark:border-slate-700">

        {/* RIGHT: Telegram discussions — no fixed max-height; CSS grid
            stretches this column to match the hero's natural height
            (image + title + bias + tg strip ≈ 780px). Previously
            capped at 700px which left a visible gap under the hero. */}
        <div className="col-span-3 py-6 pl-6 border-l border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden">
          <h3 className="text-[15px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800 shrink-0">
            تحلیل روایت‌های تلگرام
          </h3>
          <div className="flex-1 min-h-0 overflow-hidden">
            <TelegramDiscussions prefetchedData={prefetchedTelegram} locale={locale} />
          </div>
        </div>

        {/* CENTER: Hero story — image + title below */}
        {hero && (
          <div className="col-span-6 py-6 px-5">
            <Link href={`/${locale}/stories/${hero.id}`} className="group block">
              <div className="aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage
                  src={hero.image_url}
                  className="h-full w-full object-cover"
                  sizes="(max-width: 1024px) 100vw, 50vw"
                  priority
                />
              </div>
              <h1 className="mt-4 text-[28px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-3">
                {hero.title_fa}
              </h1>
            </Link>
            {/* Two-tier hero update chip. Orange "بروزرسانی" fires when
                a trigger is flagged (side flip, coverage shift, burst,
                or a rewritten bias comparison). Green "مقالهٔ جدید"
                fires when new articles arrived within the last 2h but
                no trigger qualified — still useful to show the hero is
                actively gaining coverage. */}
            {hero.update_signal?.has_update ? (() => {
              const heroReason = formatUpdateReason(hero.update_signal);
              return (
                <div className="mt-2 inline-flex items-center gap-2 border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 px-2 py-1">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-orange-500" />
                  <span className="text-[11px] font-bold text-orange-700 dark:text-orange-300">بروزرسانی</span>
                  {heroReason && (
                    <span className="text-[11px] text-orange-700/80 dark:text-orange-300/80">
                      {heroReason}
                    </span>
                  )}
                </div>
              );
            })() : (
              hero.last_updated_at &&
              Date.now() - new Date(hero.last_updated_at).getTime() < 2 * 3600 * 1000 && (
                <div className="mt-2 inline-flex items-center gap-2 border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-1">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span className="text-[11px] font-bold text-emerald-700 dark:text-emerald-300">مقالهٔ جدید</span>
                  <span className="text-[11px] text-emerald-700/80 dark:text-emerald-300/80">
                    {formatRelativeTime(hero.last_updated_at, "fa")}
                  </span>
                </div>
              )
            )}
            <Meta story={hero} />
            {/* Two-side bias comparison (flat, homepage-density) */}
            {(() => {
              const analysis = allAnalyses[hero.id];
              const stateSummary = analysis?.state_summary_fa;
              const diasporaSummary = analysis?.diaspora_summary_fa;
              const bias = analysis?.bias_explanation_fa;
              if (!stateSummary && !diasporaSummary) {
                const points = bias?.split(/[.؛]/).map((p: string) => p.trim()).filter((p: string) => p.length > 10).slice(0, 2) || [];
                if (!points.length) return null;
                return (
                  <div className="mt-3 space-y-1">
                    <UpdateDeltaCallout story={hero} field="bias" />
                    {points.map((point, i) => (
                      <p key={i} className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">• {point}</p>
                    ))}
                  </div>
                );
              }
              const biasPoints = bias
                ?.split(/[.؛]/)
                .map((p: string) => p.trim())
                .filter((p: string) => p.length > 10)
                .slice(0, 2) || [];
              return (
                <div className="mt-3">
                  <UpdateDeltaCallout story={hero} field="bias" />
                  {biasPoints.length > 0 && (
                    <div className="mb-3 space-y-1">
                      {biasPoints.map((point, i) => (
                        <p key={i} className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">• {point}</p>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    {stateSummary && (
                      <div className="border-r-2 border-[#1e3a5f] pr-3">
                        <p className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300 mb-1">روایت درون‌مرزی</p>
                        <UpdateDeltaCallout story={hero} field="state" className="mb-1.5" />
                        <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">{stateSummary}</p>
                      </div>
                    )}
                    {diasporaSummary && (
                      <div className="border-r-2 border-[#ea580c] pr-3">
                        <p className="text-[13px] font-bold text-[#ea580c] dark:text-orange-400 mb-1">روایت برون‌مرزی</p>
                        <UpdateDeltaCallout story={hero} field="diaspora" className="mb-1.5" />
                        <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">{diasporaSummary}</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
            {/* Telegram discourse summary */}
            {heroTelegram?.discourse_summary && (
              <div className="mt-3 px-1">
                <p className="text-[14px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                  <span className="font-bold text-slate-600 dark:text-slate-300">تحلیل روایت‌های تلگرام.</span>
                  {" "}{heroTelegram.discourse_summary}
                </p>
                {heroTelegram.predictions && heroTelegram.predictions.length > 0 && (
                  <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-blue-500">پیش‌بینی:</span> {predictionText(heroTelegram.predictions[0])}
                  </p>
                )}
                {heroTelegram.key_claims && heroTelegram.key_claims.length > 0 && (
                  <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-amber-500">ادعا:</span> {claimText(heroTelegram.key_claims[0])}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* LEFT: Blind spot stories (one from each side) */}
        <div className="col-span-3 py-4 pr-6 border-r border-slate-200 dark:border-slate-800 space-y-4 flex flex-col justify-center">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <span className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</span>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          {conservativeBlind && (
            <Link href={`/${locale}/stories/${conservativeBlind.id}`} className="group block border-[3px] border-[#1e3a5f] shadow-[0_0_12px_rgba(30,58,95,0.4)] hover:shadow-[0_0_20px_rgba(30,58,95,0.6)] transition-shadow animate-pulse-glow-blue">
              <div className="relative aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={conservativeBlind.image_url} className="h-full w-full object-cover" />
                {conservativeBlind.update_signal?.has_update && (
                  <span className="absolute bottom-2 right-2 border border-orange-300 dark:border-orange-700 bg-orange-50/95 dark:bg-orange-900/80 px-1.5 py-0.5 text-[10px] font-bold text-orange-700 dark:text-orange-200 backdrop-blur-sm">
                    بروزرسانی{formatUpdateReason(conservativeBlind.update_signal) ? ` · ${formatUpdateReason(conservativeBlind.update_signal)}` : ""}
                  </span>
                )}
              </div>
              <div className="p-3">
                <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {conservativeBlind.title_fa}
                </h3>
                <p className="mt-1.5 text-[13px] text-slate-400">
                  فقط روایت درون‌مرزی · {conservativeBlind.article_count} مقاله
                </p>
              </div>
            </Link>
          )}
          {oppositionBlind && (
            <Link href={`/${locale}/stories/${oppositionBlind.id}`} className="group block border-[3px] border-[#ea580c] shadow-[0_0_12px_rgba(234,88,12,0.4)] hover:shadow-[0_0_20px_rgba(234,88,12,0.6)] transition-shadow animate-pulse-glow-orange">
              <div className="relative aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={oppositionBlind.image_url} className="h-full w-full object-cover" />
                {oppositionBlind.update_signal?.has_update && (
                  <span className="absolute bottom-2 right-2 border border-orange-300 dark:border-orange-700 bg-orange-50/95 dark:bg-orange-900/80 px-1.5 py-0.5 text-[10px] font-bold text-orange-700 dark:text-orange-200 backdrop-blur-sm">
                    بروزرسانی{formatUpdateReason(oppositionBlind.update_signal) ? ` · ${formatUpdateReason(oppositionBlind.update_signal)}` : ""}
                  </span>
                )}
              </div>
              <div className="p-3">
                <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {oppositionBlind.title_fa}
                </h3>
                <p className="mt-1.5 text-[13px] text-orange-500">
                  فقط روایت برون‌مرزی · {oppositionBlind.article_count} مقاله
                </p>
              </div>
            </Link>
          )}

        </div>
      </div>

      {/* ═══ WEEKLY BRIEFING + MOST DISPUTED ═══ */}
      {sorted.length > 1 && (
        <div className="grid grid-cols-12 gap-0 py-8 border-b border-slate-200 dark:border-slate-800">
          {/* Weekly briefing (8 cols) */}
          <div className="col-span-7 pl-6 border-l border-slate-200 dark:border-slate-800">
            <h2 className="text-[24px] font-black text-slate-900 dark:text-white mb-6">در روزهای گذشته ...</h2>
            <div className="mr-8">
              {leftTextStories.map((s, i) => {
                const analysis = allAnalyses[s.id];
                const stateSummary = analysis?.state_summary_fa;
                const diasporaSummary = analysis?.diaspora_summary_fa;
                const tg = leftTextTelegramById[s.id];
                return (
                  <div key={s.id} className={`py-5 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    <Link href={`/${locale}/stories/${s.id}`} className="group block">
                      <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {s.title_fa}
                      </h3>
                    </Link>
                    <UpdateBadge story={s} className="mt-2" />
                    <Meta story={s} />
                    {/* Two-side bias comparison — hero-style card without image */}
                    {stateSummary || diasporaSummary ? (
                      <div className="mt-3">
                        <UpdateDeltaCallout story={s} field="bias" />
                        <div className="grid grid-cols-2 gap-3">
                          {stateSummary && (
                            <div className="border-r-2 border-[#1e3a5f] pr-3">
                              <p className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300 mb-1">روایت درون‌مرزی</p>
                              <UpdateDeltaCallout story={s} field="state" className="mb-1.5" />
                              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">{stateSummary}</p>
                            </div>
                          )}
                          {diasporaSummary && (
                            <div className="border-r-2 border-[#ea580c] pr-3">
                              <p className="text-[13px] font-bold text-[#ea580c] dark:text-orange-400 mb-1">روایت برون‌مرزی</p>
                              <UpdateDeltaCallout story={s} field="diaspora" className="mb-1.5" />
                              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">{diasporaSummary}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (() => {
                      const bias = analysis?.bias_explanation_fa;
                      if (!bias) return null;
                      const firstPoint = bias.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
                      if (!firstPoint) return null;
                      return <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>;
                    })()}
                    {/* Telegram strip — discourse + first prediction + first claim */}
                    {tg?.discourse_summary && (
                      <div className="mt-3 px-1">
                        <p className="text-[14px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                          <span className="font-bold text-slate-600 dark:text-slate-300">تحلیل روایت‌های تلگرام.</span>
                          {" "}{tg.discourse_summary}
                        </p>
                        {tg.predictions && tg.predictions.length > 0 && (
                          <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                            <span className="font-bold text-blue-500">پیش‌بینی:</span> {predictionText(tg.predictions[0])}
                          </p>
                        )}
                        {tg.key_claims && tg.key_claims.length > 0 && (
                          <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                            <span className="font-bold text-amber-500">ادعا:</span> {claimText(tg.key_claims[0])}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Row 1 right column is now stacked: تقابل روایت‌ها on top,
              بیشترین اختلاف نگاه below (2 stories each). Each box
              claims flex-1 so they split the column height driven by
              leftTextStories. If there are no disputed candidates the
              bottom box is hidden entirely and تقابل takes the whole
              column — no empty shells. */}
          <div className="col-span-5 pr-6 flex flex-col gap-4">
            <div className="relative flex-1 min-h-0 border border-slate-300 dark:border-slate-600 flex flex-col">
              {/* Box title sits ON the outer top border, centered, with
                  bg cutting through the border behind it. Absolute
                  positioning anchored to the outer box — title's center
                  aligns exactly with the border line (top: 0 +
                  -translate-y-1/2). Content area below gets generous
                  pt to breathe after the overlay. */}
              <span className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 text-[15px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a] whitespace-nowrap">
                تقابل روایت‌ها
              </span>
              <div className="space-y-5 px-4 pb-6 pt-8 flex-1 flex flex-col justify-between overflow-hidden">
                {(() => {
                  // battleItems is pre-computed above the JSX so the
                  // lower box («بیشترین اختلاف نگاه») can exclude these
                  // story IDs and avoid duplicating cards.
                  return battleItems.slice(0, 2).map((item, idx) => {
                    const inner = (
                      <>
                        {/* Full title — was line-clamp-1 before; Parham
                            wants to see the whole story title. */}
                        <h4 className="text-[17px] font-bold leading-snug text-slate-900 dark:text-white mb-3 group-hover:text-blue-700 dark:group-hover:text-blue-400">
                          {item.title}
                        </h4>
                        {/* Uniform 15px for both quoted-word boxes —
                            the old conditional scaled long quotes UP to
                            24px which read inconsistent next to short
                            quotes. Same size, same weight, line-clamp-1
                            truncates anything that doesn't fit. */}
                        <div className="flex gap-0 text-center">
                          <div className="flex-1 py-3 bg-[#1e3a5f]/10 dark:bg-blue-900/20 border-t-[3px] border-[#1e3a5f]">
                            <p className="text-[15px] font-black text-[#1e3a5f] dark:text-blue-300 line-clamp-1 px-2">{item.conservative}</p>
                            <p className="text-[13px] text-[#1e3a5f] dark:text-blue-300 font-medium mt-1">درون‌مرزی</p>
                          </div>
                          <div className="flex-1 py-3 bg-[#ea580c]/10 dark:bg-orange-900/20 border-t-[3px] border-[#ea580c]">
                            <p className="text-[15px] font-black text-[#ea580c] dark:text-orange-400 line-clamp-1 px-2">{item.opposition}</p>
                            <p className="text-[13px] text-[#ea580c] dark:text-orange-400 font-medium mt-1">برون‌مرزی</p>
                          </div>
                        </div>
                        {/* Replace the generic context sentence with
                            the actual two-side summaries — each up to
                            2 lines, color-coded markers to match the
                            side above. Reads as: "here are the boxes,
                            here's what each side actually says." */}
                        {(item.stateSummary || item.diasporaSummary) && (
                          <div className="mt-3 space-y-1">
                            {item.stateSummary && (
                              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                                <span className="text-[#1e3a5f] dark:text-blue-300 font-bold">• </span>{item.stateSummary}
                              </p>
                            )}
                            {item.diasporaSummary && (
                              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                                <span className="text-[#ea580c] dark:text-orange-400 font-bold">در مقابل </span>{item.diasporaSummary}
                              </p>
                            )}
                          </div>
                        )}
                      </>
                    );
                    return item.storyId ? (
                      <Link key={idx} href={`/${locale}/stories/${item.storyId}`} className="group block">
                        {inner}
                      </Link>
                    ) : (
                      <div key={idx}>{inner}</div>
                    );
                  });
                })()}
              </div>
            </div>
            {/* بیشترین اختلاف نگاه — bottom half of the column. Show
                up to 2 stories; hide the whole box if nothing qualifies
                (no empty shells). Top 2 rotate as dispute_score shifts
                from day to day. */}
            {(mostDisputedBottom || secondDisputedBottom) && (
              <div className="relative flex-1 min-h-0 border border-slate-300 dark:border-slate-600 flex flex-col">
                <span className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 text-[15px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a] whitespace-nowrap">
                  بیشترین اختلاف نگاه
                </span>
                <div className="px-4 pb-4 pt-6 flex-1 overflow-hidden">
                  {/* Stories shown here are disputed candidates that are
                      NOT already in the تقابل روایت‌ها box above —
                      prevents the same story appearing twice on the
                      right column. */}
                  {[mostDisputedBottom, secondDisputedBottom].filter(Boolean).map((story, i) => {
                    const s = story!;
                    const analysis = allAnalyses[s.id];
                    const stateSummary = analysis?.state_summary_fa;
                    const diasporaSummary = analysis?.diaspora_summary_fa;
                    return (
                      <div key={s.id} className={`py-3 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                        <Link href={`/${locale}/stories/${s.id}`} className="group block">
                          <h4 className="text-[17px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                            {s.title_fa}
                          </h4>
                          <UpdateBadge story={s} className="mt-1" />
                          <div className="mt-1 flex items-center justify-end gap-3 text-[13px]">
                            <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">درون‌مرزی {toFa(s.state_pct)}٪</span>
                            <span className="text-[#ea580c] dark:text-orange-400 font-medium">برون‌مرزی {toFa(s.diaspora_pct)}٪</span>
                          </div>
                        </Link>
                        {(stateSummary || diasporaSummary) && (
                          <div className="mt-2 space-y-1">
                            {stateSummary && (
                              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">
                                <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">• </span>{stateSummary}
                              </p>
                            )}
                            {diasporaSummary && (
                              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">
                                <span className="text-[#ea580c] dark:text-orange-400 font-medium">در مقابل </span>{diasporaSummary}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ═══ پرمخاطب‌ترین — full-width row with image on the right ═══ */}
      <div className="py-10 px-8 md:px-14 border-b border-slate-200 dark:border-slate-800">
        {/* Line-title-line divider, same pattern as «نگاه یک‌جانبه»
            on the hero row. Keeps the section visually tied to the
            rest of the homepage's chrome language. */}
        <div className="flex items-center gap-3 mb-8">
          <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          <span className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">پرمخاطب‌ترین</span>
          <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
        </div>
        <div>
          {mostViewed.map((s, i) => {
            const analysis = allAnalyses[s.id];
            const stateS = analysis?.state_summary_fa;
            const diasporaS = analysis?.diaspora_summary_fa;
            const tg = mostViewedTelegramById[s.id];
            let fallbackBullets: string[] = [];
            if (!stateS && !diasporaS) {
              const bias = analysis?.bias_explanation_fa;
              fallbackBullets = bias
                ? bias.split(/[.؛]/).map((p: string) => p.trim()).filter((p: string) => p.length > 10).slice(0, 2)
                : [];
            }
            return (
              <div key={s.id}>
                {/* Between-story separator — half width, transparent,
                    centered. Rendered ABOVE every card except the
                    first so spacing stays symmetric. */}
                {i > 0 && (
                  <div className="my-4 mx-auto w-1/2 h-px bg-slate-200/60 dark:bg-slate-700/40" />
                )}
                <Link href={`/${locale}/stories/${s.id}`} className="group flex items-stretch gap-6 py-5">
                  {/* Image first in DOM → visually on the right in RTL.
                      items-stretch on the Link lets the image match the
                      row's full content height — Parham's "same height
                      as each row" spec. Fixed width keeps the layout
                      predictable; height follows the text block. */}
                  <div className="w-48 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800 self-stretch">
                    <SafeImage src={s.image_url} className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-3">
                      <span className="text-[32px] font-black text-slate-200 dark:text-slate-700 shrink-0 leading-none mt-1">{toFa(i + 1)}</span>
                      <div className="flex-1 min-w-0">
                        {/* Tightened inter-line spacing throughout —
                            mt-1.5 → mt-1, leading-6 → leading-5.
                            Parham's "smaller between two lines" ask. */}
                        <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                          {s.title_fa}
                        </h3>
                        <UpdateBadge story={s} className="mt-1" />
                        <p className="text-[14px] text-slate-400 mt-1">
                          {toFa(s.article_count)} مقاله · {toFa(s.source_count)} رسانه
                          {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · درون‌مرزی {toFa(s.state_pct)}٪</span>}
                          {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · برون‌مرزی {toFa(s.diaspora_pct)}٪</span>}
                        </p>
                        {stateS && (
                          <p className="text-[14px] leading-5 text-slate-500 dark:text-slate-400 mt-1.5 line-clamp-2">
                            <span className="text-[#1e3a5f] dark:text-blue-300 font-bold">• </span>{stateS}
                          </p>
                        )}
                        {diasporaS && (
                          <p className="text-[14px] leading-5 text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
                            <span className="text-[#ea580c] dark:text-orange-400 font-bold">• </span>{diasporaS}
                          </p>
                        )}
                        {!stateS && !diasporaS && fallbackBullets.map((b, j) => (
                          <p key={j} className="text-[14px] leading-5 text-slate-400 dark:text-slate-500 mt-0.5 line-clamp-2">• {b}</p>
                        ))}
                        {tg?.predictions && tg.predictions.length > 0 && (
                          <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-2">
                            <span className="font-bold text-blue-500">پیش‌بینی:</span> {predictionText(tg.predictions[0])}
                          </p>
                        )}
                        {tg?.key_claims && tg.key_claims.length > 0 && (
                          <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-0.5 line-clamp-2">
                            <span className="font-bold text-amber-500">ادعا:</span> {claimText(tg.key_claims[0])}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </Link>
              </div>
            );
          })}
        </div>
      </div>

      {/* ═══ WEEKLY DIGEST ═══ */}
      <div className="py-8">
        <WeeklyDigest prefetchedContent={weeklyDigestData?.content || null} />
      </div>

      </div>
    </div>
  );
}


// ─── Mobile-only home layout (phones) ─────────────────────────────
function MobileHome({
  hero,
  stories,
  summaries,
  locale,
  conservativeBlind,
  oppositionBlind,
  allAnalyses,
  heroTelegram,
  prefetchedTelegram,
}: {
  hero: StoryBrief | undefined;
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
  conservativeBlind: StoryBrief | undefined;
  oppositionBlind: StoryBrief | undefined;
  allAnalyses: Record<string, { bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string } | null>;
  heroTelegram: { discourse_summary?: string; predictions?: any[]; key_claims?: any[] } | null;
  prefetchedTelegram: { storyId: string; analysis: any }[];
}) {
  if (!hero) return null;

  // Hero narrative fields (same two-side bias comparison used on desktop)
  const heroAnalysis = allAnalyses[hero.id];
  const heroStateSummary = heroAnalysis?.state_summary_fa;
  const heroDiasporaSummary = heroAnalysis?.diaspora_summary_fa;
  const heroBias = heroAnalysis?.bias_explanation_fa;
  const heroBiasPoints = heroBias
    ?.split(/[.؛]/).map((p: string) => p.trim()).filter((p: string) => p.length > 10).slice(0, 2) || [];

  // Weekly briefing stories ("در روزهای گذشته"): stories 1–3
  const briefingStories = stories.slice(1, 4);

  // Most covered: blended popularity score, deduplicated
  const mobileUsedIds = new Set([hero.id, ...briefingStories.map(s => s.id)]);
  if (conservativeBlind) mobileUsedIds.add(conservativeBlind.id);
  if (oppositionBlind) mobileUsedIds.add(oppositionBlind.id);
  const mobileNow = Date.now();
  const mobileMostCovered = [...stories]
    .filter(s => !mobileUsedIds.has(s.id))
    .map(s => {
      const views = s.view_count || 0;
      const recencyHours = s.updated_at ? (mobileNow - new Date(s.updated_at).getTime()) / 3600000 : 100;
      const recencyBonus = Math.max(0, 1 - recencyHours / 72);
      return { ...s, _popScore: views * 2 + s.trending_score + recencyBonus * 10 + s.article_count * 0.5 };
    })
    .sort((a, b) => b._popScore - a._popScore)
    .slice(0, 5);

  // Extract first prediction and key_claim from telegram analysis (same logic as desktop hero)
  const firstPrediction = heroTelegram?.predictions?.[0];
  const firstClaim = heroTelegram?.key_claims?.[0];
  const firstPredictionText = predictionText(firstPrediction);
  const firstClaimText = claimText(firstClaim);

  return (
    <div className="md:hidden">

      {/* ── 1. Hero story — image, title, bias comparison, telegram strip ── */}
      <div className="border-b border-slate-200 dark:border-slate-800">
        <Link href={`/${locale}/stories/${hero.id}`} className="block">
          <div className="aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
            <SafeImage
              src={hero.image_url}
              className="h-full w-full object-cover"
              sizes="100vw"
              priority
            />
          </div>
          <div className="px-4 pt-4">
            <h1 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white line-clamp-3">
              {hero.title_fa}
            </h1>
            <p className="mt-2 text-[13px] text-slate-400 dark:text-slate-500">
              {toFa(hero.source_count)} رسانه · {toFa(hero.article_count)} مقاله
            </p>
            {(hero.state_pct > 0 || hero.diaspora_pct > 0) && (
              <p className="text-[13px] mt-0.5">
                {hero.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">درون‌مرزی {toFa(hero.state_pct)}٪</span>}
                {hero.state_pct > 0 && hero.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
                {hero.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">برون‌مرزی {toFa(hero.diaspora_pct)}٪</span>}
              </p>
            )}
          </div>
        </Link>

        {/* Two-side bias comparison — same structure as desktop hero */}
        <div className="px-4 pt-3">
          {(heroStateSummary || heroDiasporaSummary) ? (
            <>
              {heroBiasPoints.length > 0 && (
                <div className="mb-3 space-y-1">
                  {heroBiasPoints.map((point, i) => (
                    <p key={i} className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">• {point}</p>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                {heroStateSummary && (
                  <div className="border-r-2 border-[#1e3a5f] pr-3">
                    <p className="text-[12px] font-bold text-[#1e3a5f] dark:text-blue-300 mb-1">روایت درون‌مرزی</p>
                    <p className="text-[13px] leading-5 text-slate-600 dark:text-slate-400 line-clamp-5">{heroStateSummary}</p>
                  </div>
                )}
                {heroDiasporaSummary && (
                  <div className="border-r-2 border-[#ea580c] pr-3">
                    <p className="text-[12px] font-bold text-[#ea580c] dark:text-orange-400 mb-1">روایت برون‌مرزی</p>
                    <p className="text-[13px] leading-5 text-slate-600 dark:text-slate-400 line-clamp-5">{heroDiasporaSummary}</p>
                  </div>
                )}
              </div>
            </>
          ) : heroBiasPoints.length > 0 ? (
            <div className="space-y-1">
              {heroBiasPoints.map((point, i) => (
                <p key={i} className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">• {point}</p>
              ))}
            </div>
          ) : null}
        </div>

        {/* Telegram discourse summary + first prediction + first claim (same as desktop hero) */}
        {heroTelegram?.discourse_summary && (
          <div className="px-4 pt-3 pb-4">
            <p className="text-[13px] leading-5 text-slate-600 dark:text-slate-400 line-clamp-3">
              <span className="font-bold text-slate-700 dark:text-slate-200">تحلیل روایت‌های تلگرام.</span>
              {" "}{heroTelegram.discourse_summary}
            </p>
            {firstPredictionText && (
              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-500 mt-1.5 line-clamp-2">
                <span className="font-bold text-blue-500">پیش‌بینی:</span> {firstPredictionText}
              </p>
            )}
            {firstClaimText && (
              <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-500 mt-1 line-clamp-2">
                <span className="font-bold text-amber-500">ادعا:</span> {firstClaimText}
              </p>
            )}
          </div>
        )}
        {!heroTelegram?.discourse_summary && <div className="pb-4" />}
      </div>

      {/* ── 2. Telegram section (cross-story discussions) ── */}
      <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-[15px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
          تحلیل روایت‌های تلگرام
        </h3>
        <TelegramDiscussions prefetchedData={prefetchedTelegram} locale={locale} />
      </div>

      {/* ── 3. Blind spots ── */}
      {(conservativeBlind || oppositionBlind) && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <span className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</span>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          <div className="space-y-4">
            {conservativeBlind && (
              <Link href={`/${locale}/stories/${conservativeBlind.id}`}
                className="group block border-[3px] border-[#1e3a5f] shadow-[0_0_12px_rgba(30,58,95,0.4)] animate-pulse-glow-blue">
                <div className="flex gap-3 p-3">
                  <div className="relative w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={conservativeBlind.image_url} className="h-full w-full object-cover" />
                    {conservativeBlind.update_signal?.has_update && (
                      <span className="absolute bottom-0 inset-x-0 bg-orange-500/95 text-white text-center text-[9px] font-bold py-0.5">
                        بروزرسانی
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {conservativeBlind.title_fa}
                    </h3>
                    <p className="mt-1 text-[13px] text-slate-400">
                      فقط روایت درون‌مرزی · {conservativeBlind.article_count} مقاله
                    </p>
                  </div>
                </div>
              </Link>
            )}
            {oppositionBlind && (
              <Link href={`/${locale}/stories/${oppositionBlind.id}`}
                className="group block border-[3px] border-[#ea580c] shadow-[0_0_12px_rgba(234,88,12,0.4)] animate-pulse-glow-orange">
                <div className="flex gap-3 p-3">
                  <div className="relative w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={oppositionBlind.image_url} className="h-full w-full object-cover" />
                    {oppositionBlind.update_signal?.has_update && (
                      <span className="absolute bottom-0 inset-x-0 bg-orange-500/95 text-white text-center text-[9px] font-bold py-0.5">
                        بروزرسانی
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {oppositionBlind.title_fa}
                    </h3>
                    <p className="mt-1 text-[13px] text-orange-500">
                      فقط روایت برون‌مرزی · {oppositionBlind.article_count} مقاله
                    </p>
                  </div>
                </div>
              </Link>
            )}
          </div>
        </div>
      )}

      {/* ── 4. Most visited ── */}
      {mobileMostCovered.length > 0 && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <span className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">پرمخاطب‌ترین</span>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {mobileMostCovered.map((s, i) => (
              <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group flex items-start gap-3 py-3">
                <span className="text-[14px] font-black text-slate-200 dark:text-slate-700 shrink-0 w-7 text-center mt-0.5">{toFa(i + 1)}</span>
                <div className="flex-1 min-w-0">
                  <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                    {s.title_fa}
                  </h3>
                  <UpdateBadge story={s} className="mt-0.5" />
                  <p className="text-[13px] text-slate-400 mt-0.5">
                    {toFa(s.article_count)} مقاله · {toFa(s.source_count)} رسانه
                    {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · درون‌مرزی {toFa(s.state_pct)}٪</span>}
                    {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · برون‌مرزی {toFa(s.diaspora_pct)}٪</span>}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ── 5. Last days ("در روزهای گذشته") ── */}
      {briefingStories.length > 0 && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <h2 className="text-[20px] font-black text-slate-900 dark:text-white mb-3">در روزهای گذشته ...</h2>
          <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {briefingStories.map((s) => {
              const bias = allAnalyses[s.id]?.bias_explanation_fa;
              const firstPoint = bias?.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
              return (
                <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group block py-4">
                  <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                    {s.title_fa}
                  </h3>
                  <UpdateBadge story={s} className="mt-1" />
                  <p className="mt-1 text-[13px] text-slate-400 dark:text-slate-500">
                    {toFa(s.source_count)} رسانه · {toFa(s.article_count)} مقاله
                    {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · درون‌مرزی {toFa(s.state_pct)}٪</span>}
                    {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · برون‌مرزی {toFa(s.diaspora_pct)}٪</span>}
                  </p>
                  {firstPoint && (
                    <p className="mt-1.5 text-[14px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
}
