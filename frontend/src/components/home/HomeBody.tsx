import Link from "next/link";
import { unstable_noStore as noStore } from "next/cache";
import { Fragment, type ReactNode } from "react";
import SafeImage from "@/components/common/SafeImage";
import SafeImageStatic from "@/components/common/SafeImageStatic";
import WelcomeModal from "@/components/common/WelcomeModal";
import type { StoryBrief, TelegramAnalysis } from "@/lib/types";
import TelegramDiscussions from "@/components/home/TelegramDiscussions";
import WeeklyDigest from "@/components/home/WeeklyDigest";
import RotatingWord from "@/components/home/RotatingWord";
import { StoryFeedback } from "@/components/home/FeedbackOverlay";
import { formatRelativeTime, splitBiasPoints, tabularNum } from "@/lib/utils";
import {
  claimText,
  displayClaims,
  displayPredictions,
  predictionText,
} from "@/lib/telegram-text";
import { normalizedSidePercentages, independentShare } from "@/lib/narrativeGroups";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// Server-side only — see app/api/v1/origin_auth.py for the contract.
const BACKEND_API_TOKEN = process.env.BACKEND_API_TOKEN;
const AUTH_HEADERS: HeadersInit = BACKEND_API_TOKEN
  ? { "X-API-Token": BACKEND_API_TOKEN }
  : {};

// Cache TTLs tuned for a homepage where stories update on the hour, not the
// minute. Every miss is a round trip from Vercel (US or EU) to Railway in the
// US, so bumping these from 30/60/120 to 300/600/600 cuts origin pressure
// dramatically without noticeably aging the content.
// TTLs intentionally short: our SSR fetches swallow errors and return
// `{}` / `null` as fallback (so the page still renders partial data when
// the API is slow). Next.js ISR caches those fallback values as if they
// were real, which can leave the homepage stuck on empty-state for up
// to the TTL window. Short TTLs heal that within a few minutes.
const TRENDING_TTL = 600;        // 10 min — data changes 2×/day; longer TTL halves regen egress (Lever 1, 2026-05-31)
const ANALYSIS_TTL = 600;        // 10 min
const TELEGRAM_TTL = 600;        // 10 min

async function fetchAPI<T>(path: string): Promise<T | null> {
  try {
    const controller = new AbortController();
    // 20s: Railway cold-starts during ISR regen can easily hit 10s+ while
    // also serving 15+ parallel telegram calls. The old 8s cap was
    // aborting trending on those bursts and baking an empty homepage
    // into the ISR cache for the full 300s revalidate window.
    const timeout = setTimeout(() => controller.abort(), 20000);
    const res = await fetch(`${API}${path}`, { next: { revalidate: TRENDING_TTL }, signal: controller.signal, headers: AUTH_HEADERS });
    clearTimeout(timeout);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchSummary(storyId: string): Promise<string | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: ANALYSIS_TTL }, headers: AUTH_HEADERS });
    if (!res.ok) return null;
    const data = await res.json();
    return data.summary_fa || null;
  } catch {
    return null;
  }
}

async function fetchAnalysis(storyId: string): Promise<{ summary_fa?: string; briefing_fa?: string | null; bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: ANALYSIS_TTL }, headers: AUTH_HEADERS });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchAnalysesBatch(storyIds: string[]): Promise<Record<string, { summary_fa?: string; briefing_fa?: string | null; bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null>> {
  if (storyIds.length === 0) return {};
  // Dedupe + stable-sort so identical sets share a cache key.
  const ids = Array.from(new Set(storyIds)).sort();
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    const res = await fetch(
      `${API}/api/v1/stories/analyses?ids=${ids.join(",")}`,
      { next: { revalidate: ANALYSIS_TTL }, signal: controller.signal, headers: AUTH_HEADERS },
    );
    clearTimeout(timeout);
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};
  }
}

async function fetchTelegramAnalysesBatch(storyIds: string[]): Promise<Record<string, TelegramAnalysis>> {
  if (storyIds.length === 0) return {};
  const ids = Array.from(new Set(storyIds)).sort();
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const res = await fetch(
      `${API}/api/v1/social/stories/telegram-analyses?ids=${ids.join(",")}`,
      { next: { revalidate: TELEGRAM_TTL }, signal: controller.signal, headers: AUTH_HEADERS },
    );
    clearTimeout(timeout);
    if (!res.ok) return {};
    const raw = (await res.json()) as Record<string, TelegramAnalysis | null>;
    const out: Record<string, TelegramAnalysis> = {};
    for (const [id, a] of Object.entries(raw)) {
      if (!a) continue;
      out[id] = {
        ...a,
        predictions: displayPredictions(a),
        key_claims: displayClaims(a),
      };
    }
    return out;
  } catch {
    return {};
  }
}

/**
 * Pick the display title for a story based on the active locale.
 *
 * Cycle-4 (2026-05-08): pre-this-fix, HomeBody rendered `s.title_fa`
 * unconditionally — so /en showed Persian even though the API
 * populated `title_en` (gpt-4.1-nano article-level) and
 * `translations.{en,fr}.title` (gpt-5-mini story-level NYT/Le Monde
 * voice). Preference order:
 *   1. translations[locale].title — the higher-quality voice-tuned
 *      story-level translation when it exists.
 *   2. title_{en|fa} — flat per-language fields (article-level).
 *   3. The other locale as a last resort so the page never goes empty.
 *
 * The trending API now exposes `translations` on the brief (cycle-4
 * backend fix); pre-this-fix the blob was detail-only, so /fr rendered
 * the EN article-level translation as a fallback.
 */
function localizedStoryTitle(
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

function Meta({ story }: { story: StoryBrief }) {
  // Fall back through the date chain so a story always shows at least
  // one timestamp. Some stories arrive with a null first_published_at
  // (RSS feeds without pubDate); without the fallback the meta line
  // hides the date entirely.
  const publishedSrc = story.first_published_at || story.last_updated_at || story.updated_at;
  const published = publishedSrc ? formatRelativeTime(publishedSrc, "fa") : null;
  const updatedSrc = story.last_updated_at || story.updated_at;
  const updated = updatedSrc ? formatRelativeTime(updatedSrc, "fa") : null;
  const showUpdated = updated && updatedSrc && publishedSrc
    && Math.abs(new Date(updatedSrc).getTime() - new Date(publishedSrc).getTime()) > 3600000;
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
      <div className="flex items-center justify-between text-[15px] leading-6">
        <p className="text-slate-400 dark:text-slate-500">
          {tabularNum(story.source_count)} رسانه · {tabularNum(story.article_count)} مقاله
          {/* Lead with freshness: an ongoing story that got new articles today
              must not read as «۶ روز پیش» just because its first article is old
              (Parham 2026-06-03: today's Kuwait news showed «نشر ۶ روز پیش»).
              When there's recent activity, show «به‌روزرسانی» first and keep the
              start date faint; otherwise just the publish date. */}
          {showUpdated ? (
            <>
              <span>{" · "}به‌روزرسانی {updated}</span>
              {published && (
                <span className="text-slate-300 dark:text-slate-600">{" · "}نشر {published}</span>
              )}
            </>
          ) : (
            published && <span>{" · "}نشر {published}</span>
          )}
        </p>
        {hasSides && (
          <p className="shrink-0">
            {insidePct > 0 && <span className="text-inside-border dark:text-inside-border-dark">درون‌مرزی {tabularNum(insidePct)}٪</span>}
            {insidePct > 0 && outsidePct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
            {outsidePct > 0 && <span className="text-outside-border dark:text-outside-border-dark">برون‌مرزی {tabularNum(outsidePct)}٪</span>}
            {indepPct >= 5 && (
              <span className="text-slate-400 dark:text-slate-500">
                {" · "}مستقل {tabularNum(indepPct)}٪
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
          className="text-[15px] leading-6 text-emerald-900 dark:text-emerald-100"
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
// F5 — orange "بروزرسانی" badge auto-expires after 24 hours.
// Without this, a story flagged at 09:00 Monday still wears the orange
// pill on Friday, which is misleading. The trigger doesn't get
// re-evaluated until the next maintenance tick, so we TTL the
// rendered badge on the read side based on `detected_at`.
const UPDATE_BADGE_TTL_MS = 24 * 3600 * 1000;
function isUpdateBadgeFresh(sig: NonNullable<StoryBrief["update_signal"]> | null | undefined): boolean {
  if (!sig?.has_update) return false;
  if (!sig.detected_at) return true; // legacy rows without detected_at — render once, falls off naturally on next refresh
  const t = Date.parse(sig.detected_at);
  if (!Number.isFinite(t)) return true;
  return Date.now() - t < UPDATE_BADGE_TTL_MS;
}

function UpdateBadge({ story, className = "mt-1.5" }: { story: StoryBrief; className?: string }) {
  // «بروزرسانی» must mean NEW REPORTING arrived. A closed/frozen story
  // (no new article in >7d) can still carry a fresh update_signal from a
  // pure metric recompute — e.g. the 2026-05-31 dispute_score methodology
  // rollout restamped detected_at on 70 stories, lighting up «اختلاف
  // روایت‌ها افزایش یافت» on month-old frozen clusters that received no
  // articles. New coverage ticks last_updated_at; a recompute doesn't. So
  // suppress the orange badge when last_updated_at is definitively stale.
  const luStale = story.last_updated_at
    ? Date.now() - new Date(story.last_updated_at).getTime() >= 7 * 86400 * 1000
    : false; // missing timestamp → don't suppress (legacy rows)
  // Orange — significant update
  if (!luStale && isUpdateBadgeFresh(story.update_signal)) {
    const reason = formatUpdateReason(story.update_signal!);
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

// ─── Shared homepage body ──────────────────────────────────────
// Rendered by both `/` (read mode) and `/rate` (feedback mode). The
// only difference between the two: feedback mode wraps every story
// link in <StoryFeedback> (overlay buttons for title/image/priority/
// merge) and rewrites story hrefs to include `?feedback=1` so the
// story page also enters feedback mode.

export default async function HomeBody({
  locale,
  feedbackMode = false,
}: {
  locale: string;
  feedbackMode?: boolean;
}) {
  // Helpers for the feedback-vs-read fork. Defined inline so every
  // story-card site can call `wrapStory(...)` + `storyHref(...)` and
  // not branch on feedbackMode at every callsite. In read mode these
  // are pass-throughs; in feedback mode they wrap with <StoryFeedback>
  // and append `?feedback=1` to the link.
  const storyHref = (id: string) =>
    `/${locale}/stories/${id}${feedbackMode ? "?feedback=1" : ""}`;
  function wrapStory(
    args: { storyId: string | undefined | null; title: string | undefined | null; imageUrl?: string | null },
    children: ReactNode,
    key?: React.Key,
  ): ReactNode {
    if (!feedbackMode || !args.storyId) {
      return key !== undefined ? <Fragment key={key}>{children}</Fragment> : children;
    }
    return (
      <StoryFeedback
        key={key}
        storyId={args.storyId}
        title={args.title || ""}
        imageUrl={args.imageUrl ?? null}
      >
        {children}
      </StoryFeedback>
    );
  }
  // Stage 1: all independent fetches in parallel — trending,
  // blindspots, weekly digest. None depend on story IDs.
  //
  // Trending is load-bearing (`_stories` gates the whole render). If
  // fetchAPI returns null (20s timeout or 5xx) we retry once with a
  // fresh controller before giving up. A single transient Railway
  // hiccup was baking the "هنوز موضوعی ایجاد نشده" empty state into
  // the ISR cache for 300s. Throwing would be cleaner but kills the
  // initial `next build` prerender (no prior cached version exists
  // then), so we retry instead and accept occasional empty caches.
  const [trendingFirst, blindspotsFirst, weeklyDigestData] = await Promise.all([
    fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=30"),
    fetchAPI<StoryBrief[]>("/api/v1/stories/blindspots?limit=10"),
    fetchAPI<{ status: string; content?: string }>("/api/v1/stories/weekly-digest"),
  ]);
  let _stories: StoryBrief[] | null = trendingFirst;
  for (let attempt = 1; _stories === null && attempt <= 3; attempt++) {
    await new Promise((r) => setTimeout(r, 1500 * attempt));
    _stories = await fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=30");
  }
  // Blindspots get the SAME retry treatment as trending (2026-05-31).
  // Previously this fetch coalesced null→[] with no retry, so a single
  // transient backend blip — e.g. a homepage ISR regen that happened to
  // run mid-Railway-redeploy — returned [] and baked an empty «نگاه
  // یک‌جانبه» section into the 30-min cache (Parham saw it empty while
  // the API actually had 9 blindspots). A genuine quiet day returns an
  // empty ARRAY (truthy) and is respected; only a null FETCH FAILURE
  // triggers retry, and a persistent failure opts the page out of cache
  // below rather than baking the empty section.
  let _blindspots: StoryBrief[] | null = blindspotsFirst;
  for (let attempt = 1; _blindspots === null && attempt <= 3; attempt++) {
    await new Promise((r) => setTimeout(r, 1500 * attempt));
    _blindspots = await fetchAPI<StoryBrief[]>("/api/v1/stories/blindspots?limit=10");
  }
  // If trending OR blindspots is genuinely null after retries, the API
  // is down. Opt OUT of the ISR cache so the empty state isn't served
  // for the next 30 min — the next request triggers a fresh SSR attempt.
  const apiIsDown = _stories === null;
  if (apiIsDown || _blindspots === null) {
    noStore();
  }
  if (_stories === null) _stories = [];
  if (_blindspots === null) _blindspots = [];

  // Skip stories that only have a source-logo fallback as their cover.
  // Per Parham's rule, a story without a real image should never surface
  // on the homepage — it looks broken and dilutes the editorial feed.
  // Those stories are still accessible via direct link and are queued for
  // HITL image assignment at /admin/hitl/stories-without-image.
  // `has_real_image` is undefined on older cached responses; treat
  // undefined as "assume true" so a rollout of the backend flag doesn't
  // blank the homepage on stale caches.
  const hasImage = (s: StoryBrief) => s.has_real_image !== false;
  let stories = (_stories || []).filter(hasImage);
  let blindspots = _blindspots.filter(hasImage);

  if (stories.length === 0) {
    // Belt-and-suspenders: if we got here with stories=[] after the
    // API succeeded with an actually-empty result (not the down-API
    // path above), still opt out of caching. An empty homepage cached
    // for 5 min is worse than re-fetching every request — the page is
    // unusable either way and we want the moment data appears to
    // surface as soon as possible.
    noStore();
    return (
      <div dir={locale === "fa" ? "rtl" : "ltr"} className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">پوشش خبری در حال بروزرسانی است</h2>
        <p className="mt-2 text-sm text-slate-500">
          خط‌لولهٔ گردآوری در حال اجراست. این صفحه به‌طور خودکار هر چند دقیقه تازه می‌شود؛
          {" "}
          <Link href={`/${locale}/sources`} className="underline decoration-slate-300 dark:decoration-slate-600 underline-offset-2 hover:text-slate-700 dark:hover:text-slate-300">
            فهرست رسانه‌ها و روش‌شناسی
          </Link>
          {" "}
          را در همین حال ببینید.
        </p>
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
  // F1 — tiered freshness windows. The site's editorial intent is
  // "anything older than ~7 days is dated; ~30 days is dead." Each
  // homepage section gets its own cutoff so older content silently
  // falls off the prime slots even when picks would otherwise be
  // empty. Anything beyond MAX_AGE is dropped from every pick.
  const HERO_MAX_AGE_MS = 72 * 3600 * 1000;        // 3d — hero must be hot
  const HERO_DROUGHT_AGE_MS = 26 * 86400 * 1000;   // 26d — last-resort hero only when nothing fresher exists
  const BLINDSPOT_MAX_AGE_MS = 7 * 86400 * 1000;   // 7d — F7 mirror
  const DISPUTE_MAX_AGE_MS = 14 * 86400 * 1000;    // 14d — disputed slot
  const BRIEFING_MAX_AGE_MS = 14 * 86400 * 1000;   // 14d — weekly briefing
  const POPULAR_MAX_AGE_MS = 14 * 86400 * 1000;    // 14d — pop-score
  // HARD_MAX_AGE_MS removed 2026-05-03: was the silent filter that
  // dropped frozen homepage stories. Per-slot windows below are the
  // editorial intent; backend archived_at is the death.
  const FRESH_WINDOW_MS = 24 * 60 * 60 * 1000;     // legacy "fresh" signal kept for has_update gating
  const nowMs = Date.now();
  const ageMs = (s: StoryBrief): number => {
    const src = s.last_updated_at || s.first_published_at;
    if (!src) return Number.POSITIVE_INFINITY;
    const t = Date.parse(src);
    return Number.isFinite(t) ? nowMs - t : Number.POSITIVE_INFINITY;
  };
  const isFresh = (s: StoryBrief): boolean => ageMs(s) < FRESH_WINDOW_MS;
  const withinAge = (limit: number) => (s: StoryBrief): boolean => ageMs(s) < limit;
  const hasUpdate = (s: StoryBrief): boolean => !!s.update_signal?.has_update;

  // Frontend age policy (Parham 2026-05-03): the prior unconditional
  // HARD_MAX_AGE_MS=30d filter silently dropped frozen stories that
  // the backend now intentionally serves on the homepage (frozen-stays-
  // visible rule). Trust the backend ordering — archived_at and the
  // demote-on-freeze sort already keep stale content from dominating.
  // Hero/blindspot/disputed/popular/briefing slots STILL apply their
  // tighter per-slot windows below; this just removes the global gate
  // that was hiding the rotation tail.

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
  // blindspot. 80/20 is the threshold for "one-sided enough to be
  // worth calling out as a نگاه یک‌جانبه" — anything balanced beyond
  // that erodes the meaning of the slot. The label below switches to
  // «بیشتر» when the minority side has any coverage and «فقط» only
  // when the minority side is at exactly 0%.
  const ONE_SIDED_MAJOR = 80;  // % covered by the dominant side (heuristic mint)
  const ONE_SIDED_MINOR = 20;  // % covered by the minority side (heuristic mint)
  // Backend-flagged blindspots get a looser live re-validation: the
  // backend already classified them as one-sided, we just confirm the
  // split hasn't flipped. Without this, formal blindspots whose minority
  // climbed from 0% → 25% (still one-sided) would fail the 80/20 gate
  // and leave a slot empty when the backend already named a candidate.
  const ONE_SIDED_MAJOR_LOOSE = 70;
  const ONE_SIDED_MINOR_LOOSE = 30;
  const stateHeavy = (s: StoryBrief) =>
    (s.state_pct || 0) >= ONE_SIDED_MAJOR && (s.diaspora_pct || 0) <= ONE_SIDED_MINOR;
  const diasporaHeavy = (s: StoryBrief) =>
    (s.diaspora_pct || 0) >= ONE_SIDED_MAJOR && (s.state_pct || 0) <= ONE_SIDED_MINOR;
  const stateHeavyLoose = (s: StoryBrief) =>
    (s.state_pct || 0) >= ONE_SIDED_MAJOR_LOOSE && (s.diaspora_pct || 0) <= ONE_SIDED_MINOR_LOOSE;
  const diasporaHeavyLoose = (s: StoryBrief) =>
    (s.diaspora_pct || 0) >= ONE_SIDED_MAJOR_LOOSE && (s.state_pct || 0) <= ONE_SIDED_MINOR_LOOSE;

  // F1 — blindspots restricted to BLINDSPOT_MAX_AGE_MS (7d). The
  // feature loses meaning if it shows month-old gaps. Fall through
  // to the formal blindspot list before the heuristic state/diaspora
  // heavy fallback, but never beyond 7d. Earlier code's "any state_only
  // ever" fallback removed — those slots simply stay empty when
  // there's nothing fresh, which is honest signal.
  //
  // Re-validate one-sidedness against current state_pct/diaspora_pct.
  // Backend's is_blindspot is computed from per-article side counts at
  // recount time, while the homepage displays distinct-source pcts —
  // when new articles tip a previously one-sided story toward balance
  // the flag can lag the visible split. Gate the formal pick by the
  // same 60/40 source threshold the heuristic uses so we never show a
  // «نگاه یک‌جانبه» card whose own percentages contradict the label.
  const blindFresh = withinAge(BLINDSPOT_MAX_AGE_MS);
  // Prefer a real-image candidate (`blindspots` is image-filtered), but fall
  // back to a PHOTO-LESS one-sided blindspot from the unfiltered `_blindspots`
  // before leaving the slot empty. Diaspora outlets reaching us only via t.me
  // mirrors usually have no OG image, so _pick_image returns their source LOGO
  // with has_real_image=false — which the `hasImage` filter strips, silently
  // emptying the برون‌مرزی column even when a perfect 100%-diaspora blindspot
  // exists (Parham, 2026-06-02: «نگاه یک‌جانبه has only one story»). The card
  // renders the newspaper placeholder for these via the has_real_image gate.
  const conservativeBlind =
    blindspots.find(s => s.blindspot_type === "state_only" && blindFresh(s) && hasUpdate(s) && stateHeavyLoose(s)) ||
    blindspots.find(s => s.blindspot_type === "state_only" && blindFresh(s) && stateHeavyLoose(s)) ||
    _blindspots.find(s => s.blindspot_type === "state_only" && blindFresh(s) && stateHeavyLoose(s)) ||
    [...stories].filter(stateHeavy).filter(blindFresh).sort((a, b) =>
      (b.state_pct - b.diaspora_pct) - (a.state_pct - a.diaspora_pct)
    )[0] ||
    undefined;
  const oppositionBlind =
    blindspots.find(s => s.blindspot_type === "diaspora_only" && blindFresh(s) && hasUpdate(s) && diasporaHeavyLoose(s)) ||
    blindspots.find(s => s.blindspot_type === "diaspora_only" && blindFresh(s) && diasporaHeavyLoose(s)) ||
    _blindspots.find(s => s.blindspot_type === "diaspora_only" && blindFresh(s) && diasporaHeavyLoose(s)) ||
    [...stories].filter(diasporaHeavy).filter(blindFresh).sort((a, b) =>
      (b.diaspora_pct - b.state_pct) - (a.diaspora_pct - a.state_pct)
    )[0] ||
    undefined;

  // ── Deduplication: track which stories are placed ──
  const usedIds = new Set<string>();

  // Blind spots first (already picked above)
  if (conservativeBlind) usedIds.add(conservativeBlind.id);
  if (oppositionBlind) usedIds.add(oppositionBlind.id);

  const sorted = [...stories];

  // ── Stage 2 (collapsed): one round trip for ALL analyses + top-15
  //    telegram strips, fired in parallel. Previously this was split
  //    across two awaits — a 15-id "prefetch" to gate the hero picker,
  //    then another batch with extraAnalyses + 4 telegram batches.
  //    Merging into a single Promise.all saves ~300-600ms on every ISR
  //    regen on Railway. Hero/leftText/mostViewed strips are looked up
  //    from the top-15 telegram map further down (no separate fetches).
  const sortedIds = sorted.map(s => s.id);
  const telegramAnalysisIds = sorted.slice(0, 15).map(s => s.id);
  const [allAnalyses, telegramByStoryId] = await Promise.all([
    fetchAnalysesBatch(sortedIds),
    fetchTelegramAnalysesBatch(telegramAnalysisIds),
  ]);
  const hasBiasNarrative = (s: StoryBrief): boolean => {
    const a = allAnalyses[s.id];
    return !!(a && (a.state_summary_fa || a.diaspora_summary_fa) && a.bias_explanation_fa);
  };

  // Hero picker fallback chain — most specific first so we surface the
  // richest story that qualifies. The bias-narrative gate sits at the
  // top because the hero card is useless without it; once the gate is
  // exhausted we fall through to the older signals so the slot never
  // goes empty on a thin news day.
  // F1 — hero must be hot (≤72h). Fall through to the regular
  // 24h-fresh window only if no 72h-eligible story has the right
  // narrative shape. Anything older than 14d is excluded entirely
  // (no `sorted[0]` fallback), so on a thin news day the hero may
  // be missing — better than promoting a 3-week-old story.
  const heroFresh = withinAge(HERO_MAX_AGE_MS);
  const heroSafe = withinAge(BRIEFING_MAX_AGE_MS);
  // Manual-pin override (Parham 2026-05-04): a story with priority > 0
  // is the operator's explicit declaration that this IS the hero,
  // regardless of whether step_detect_hourly_updates flagged it as
  // having an update_signal. Without this clause the regular
  // hasUpdate-gated find skipped a freshly-pinned story whose update
  // signal hadn't yet been recomputed. Still requires bias narrative
  // + 72h freshness so the card isn't visually broken.
  const isPinned = (s: StoryBrief): boolean => (s.priority ?? 0) > 0;
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
    // Drought fallback (2026-05-31): the 14d cap above leaves the marquee
    // EMPTY when every trending story is older — which is exactly what
    // happened after the May cron lockdown left the freshest stories at
    // 16-25d AND the two genuinely-fresh ones were archived (a grab-bag +
    // a false geo-merge). An empty hero reads as broken, so fall back to
    // the best older story: prefer a two-sided bias narrative, else the
    // freshest available within the wider window. Auto-tightens back to
    // 14d the moment the now-live cron brings fresh news.
    sorted.find(s => withinAge(HERO_DROUGHT_AGE_MS)(s) && hasBiasNarrative(s) && s.state_pct >= 5 && s.diaspora_pct >= 5) ||
    sorted.find(s => withinAge(HERO_DROUGHT_AGE_MS)(s) && hasBiasNarrative(s)) ||
    sorted.find(withinAge(HERO_DROUGHT_AGE_MS));
  if (hero) usedIds.add(hero.id);

  // Weekly briefing: left-text "در روزهای گذشته" block. 3 hero-style
  // cards — two-side narratives + telegram strip, no image. F1: drop
  // anything older than 14d so this section reflects the past week,
  // not the past month.
  // ── تقابل روایت‌ها reservation (Parham 2026-06-03) ──────────────
  // The «clash of narratives» box needs two genuinely-opposed sides. On a
  // war-news day EVERY story is two-sided, and the most-viewed / left-text
  // strips below were consuming the fresh disputed stories before this box
  // was computed — so تقابل rendered just 1 card despite plenty of qualifying
  // stories. Reserve its picks HERE, before those strips, so it gets the
  // strongest disputed stories; the strips then fill from the remainder.
  // (The old separate «بیشترین اختلاف» box was merged into this one — its
  // mostDisputed/secondDisputed/thirdDisputed vars are no longer rendered.)
  const META_PATTERNS = [
    /^پوشش\s+(برون‌مرزی|درون‌مرزی)/,
    /روایت[^.]{0,40}(متمایز|شکل\s+نگرفت|غایب)/,
    /هیچ\s+رسانه/,
    /در\s+این\s+(خبر|مجموعه)[^.]{0,20}حضور\s+ندارن/,
    /رسانه[^.]{0,50}حضور\s+ندار/,
  ];
  const hasTwoRealNarratives = (
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
  const _battleGate = (s: StoryBrief, maxAgeMs: number): boolean => {
    if (!(s.state_pct > 0 && s.diaspora_pct > 0) || s.is_blindspot) return false;
    if (usedIds.has(s.id)) return false;
    if (ageMs(s) >= maxAgeMs) return false;
    const a = allAnalyses[s.id];
    if (!hasTwoRealNarratives(a)) return false;
    const lw = a?.loaded_words;
    if (lw?.conservative?.length && lw?.opposition?.length) return true;
    // Bias-text quote fallback (matches the battle loop below).
    const quotes = a?.bias_explanation_fa?.match(/«[^»]+»/g);
    return !!(quotes && quotes.length >= 2);
  };
  const _battleSpread = (a: StoryBrief, b: StoryBrief) =>
    Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct);
  let battleReserved = [...sorted].filter(s => _battleGate(s, DISPUTE_MAX_AGE_MS)).sort(_battleSpread);
  if (battleReserved.length < 3) {
    // Drought widen — same recovery logic as the other boxes.
    battleReserved = [...sorted].filter(s => _battleGate(s, 26 * 86400 * 1000)).sort(_battleSpread);
  }
  battleReserved = battleReserved.slice(0, 4);
  battleReserved.forEach(s => usedIds.add(s.id));

  const briefingFresh = withinAge(BRIEFING_MAX_AGE_MS);
  let leftTextStories = sorted.filter(s => !usedIds.has(s.id) && briefingFresh(s)).slice(0, 3);
  if (leftTextStories.length < 3) {
    // Drought fallback (2026-05-31): after a content gap (e.g. the May
    // cron lockdown left most stories 16-25d old) the 14d cap leaves
    // this block empty once hero + disputed consume the few fresh ones.
    // Widen to 26d so «در روزهای گذشته» isn't bare — same recovery logic
    // as the disputed box; auto-tightens once fresh content returns.
    const briefingDrought = withinAge(26 * 86400 * 1000);
    leftTextStories = sorted.filter(s => !usedIds.has(s.id) && briefingDrought(s)).slice(0, 3);
  }
  leftTextStories.forEach(s => usedIds.add(s.id));

  // Most viewed: top 3. Narrower half-column now (grid-cols-2 cell in
  // row 2), so fewer cards at richer density reads better. F1: cap at
  // 14d so a 3-week-old viral story doesn't dominate the section
  // forever after its real moment passed.
  const popularFresh = withinAge(POPULAR_MAX_AGE_MS);
  const now = Date.now();
  let popularPool = [...sorted].filter(s => !usedIds.has(s.id) && popularFresh(s));
  if (popularPool.length < 3) {
    // Drought fallback (2026-05-31): when the 14d window can't fill the 3
    // «پرمخاطب‌ترین» slots (post-lockdown content gap), widen to 26d so the
    // section isn't blank. Auto-tightens once fresh news returns.
    popularPool = [...sorted].filter(s => !usedIds.has(s.id) && withinAge(26 * 86400 * 1000)(s));
  }
  if (popularPool.length < 3) {
    // Second tier (Parham 2026-06-04): «پرمخاطب‌ترین» is about POPULARITY,
    // which accumulates over weeks — the genuinely most-viewed stories are
    // often the 27-30d war umbrellas, and on a thin war-homepage the fresh
    // pool is also claimed by the hero + تقابل + recent-days strips. Since
    // popularity isn't freshness-sensitive, widen to any homepage-eligible
    // story (retention already caps the DB at 30d) so this box never blanks.
    popularPool = [...sorted].filter(s => !usedIds.has(s.id));
  }
  const mostViewed = popularPool
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

  // Most disputed: F1: 14d cap. A 3-week-old disputed story isn't
  // disputed news anymore, it's history.
  //
  // Adaptive window (2026-05-31): the strict 14d cap goes bare during a
  // content drought (e.g. after the May cron lockdown most two-sided war
  // stories were 17-25d old). So we try 14d first; only if that yields
  // fewer than 3 disputed slots do we widen to DISPUTE_DROUGHT_AGE_MS so
  // the section fills from slightly-older two-sided stories. As soon as
  // the now-live cron brings ≥3 fresh disputed stories this auto-tightens
  // back to 14d — no permanent weakening of the freshness rule.
  const DISPUTE_DROUGHT_AGE_MS = 26 * 86400 * 1000; // recovery fallback only
  const disputeTwoSided = (s: StoryBrief, maxAgeMs: number) =>
    s.state_pct > 0 && s.diaspora_pct > 0 && !s.is_blindspot && !usedIds.has(s.id) && withinAge(maxAgeMs)(s);
  const byDisputeSpread = (a: StoryBrief, b: StoryBrief) =>
    Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct);
  const freshDisputed = [...stories]
    .filter(s => disputeTwoSided(s, DISPUTE_MAX_AGE_MS))
    .sort(byDisputeSpread);
  const disputedCandidates = freshDisputed.length >= 3
    ? freshDisputed
    : [...stories].filter(s => disputeTwoSided(s, DISPUTE_DROUGHT_AGE_MS)).sort(byDisputeSpread);
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

  // ── Telegram lookup maps ──
  // Top-15 telegram strips were fetched up top alongside analyses, in a
  // single batched request. Look up hero/leftText/mostViewed telegrams
  // from that map instead of refetching them. Stories that fall outside
  // top-15 (rare for hero/leftText, occasionally for mostViewed) get
  // null and the strip simply hides — acceptable below-fold UX.
  const heroTelegram: TelegramAnalysis | null = hero ? telegramByStoryId[hero.id] || null : null;
  const leftTextTelegramById: Record<string, TelegramAnalysis> = {};
  for (const s of leftTextStories) {
    if (telegramByStoryId[s.id]) leftTextTelegramById[s.id] = telegramByStoryId[s.id];
  }
  const mostViewedTelegramById: Record<string, TelegramAnalysis> = {};
  for (const s of mostViewed) {
    if (telegramByStoryId[s.id]) mostViewedTelegramById[s.id] = telegramByStoryId[s.id];
  }

  // Cycle-4 Phase 2-a (2026-05-08): prefer the translated story-level
  // summary (gpt-5-mini Niloofar NYT/Le Monde voice) over the FA
  // analysis summary when locale != fa. The translation lives on the
  // story brief now (cycle-4 backend exposed translations on
  // StoryBrief). Fall back to FA only if the locale's translation is
  // missing — better Persian than empty.
  const briefById: Record<string, StoryBrief> = {};
  for (const s of sorted) {
    briefById[s.id] = s;
  }
  // Cycle-4 Phase 2-c (2026-05-08): override the FA narrative fields
  // in `allAnalyses` with the locale-translated values when present.
  // Single-point patch keeps all ~15 downstream render sites unchanged.
  // Phase 2-b cron now writes translations.{locale}.{state_summary,
  // diaspora_summary, independent_summary, bias_explanation,
  // editorial_context}; this loop hoists those onto the analysis
  // shape so every render site reading {field}_fa gets the translated
  // string transparently. FA pages are no-op (locale === "fa").
  if (locale !== "fa") {
    for (const id of sortedIds) {
      const tl = briefById[id]?.translations?.[locale];
      const a = allAnalyses[id];
      if (!tl || !a) continue;
      if (tl.state_summary) a.state_summary_fa = tl.state_summary;
      if (tl.diaspora_summary) a.diaspora_summary_fa = tl.diaspora_summary;
      if (tl.bias_explanation) a.bias_explanation_fa = tl.bias_explanation;
      // independent_summary_fa isn't on the analysis shape today;
      // omit until/unless the analysis API exposes it. The bias-panel
      // 4-subgroup taxonomy uses inside/outside_border_pct, not the
      // independent narrative paragraph.
    }
  }
  const allSummaries: Record<string, string | null> = {};
  for (const id of sortedIds) {
    const tl = locale !== "fa" ? briefById[id]?.translations?.[locale]?.summary : null;
    allSummaries[id] = tl || allAnalyses[id]?.summary_fa || null;
  }

  // Pick disputed stories by the real dispute_score (state-vs-diaspora
  // framing divergence, backfilled deterministically — the LLM had clustered
  // every story on ~0.5, so this box used to just show the top-trending
  // two-sided stories rather than the genuinely-contested ones). Sort by
  // dispute desc (tiebreak: coverage-% gap), then PREFER the genuinely-
  // disputed subset (>= floor); fall back to the full sorted list if too few
  // qualify so the box isn't empty on calm news days.
  const DISPUTE_FLOOR = 0.45;
  const byDispute = [...disputedCandidates].sort((a, b) =>
    ((allAnalyses[b.id]?.dispute_score ?? 0) - (allAnalyses[a.id]?.dispute_score ?? 0))
    || (Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct)),
  );
  const genuinelyDisputed = byDispute.filter(
    s => (allAnalyses[s.id]?.dispute_score ?? 0) >= DISPUTE_FLOOR,
  );
  const disputedResorted = genuinelyDisputed.length >= 2 ? genuinelyDisputed : byDispute;
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
    // Lists of distinct loaded words, sorted shortest-first. RotatingWord
    // cycles through them with a fade animation; if a story only yielded
    // one word the component renders it static (no flicker).
    conservativeWords: string[];
    oppositionWords: string[];
    stateSummary: string;
    diasporaSummary: string;
  };
  const battleItems: BattleItem[] = [];
  const buildWordList = (ws: string[]): string[] => {
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
  // government stories, and buildWordList's shortest-first sort surfaces
  // the short stock word («سرکوب») first, so every card showed the same
  // outside-border word. preferUnused reorders each story's list to lead
  // with a word no prior card has shown yet, falling back to the
  // shortest-first order only when every word is already taken. Keeps
  // the rotation list intact (RotatingWord still cycles all of them) —
  // only the FIRST, most-visible word is diversified across cards.
  const _usedOppWords = new Set<string>();
  const _usedConsWords = new Set<string>();
  const preferUnused = (ws: string[], used: Set<string>): string[] => {
    const fresh = ws.filter(w => !used.has(w));
    const stale = ws.filter(w => used.has(w));
    const ordered = fresh.length ? [...fresh, ...stale] : ws;
    if (ordered[0]) used.add(ordered[0]);
    return ordered;
  };
  // Scan the top 12 disputed candidates so we can reliably fill the
  // 4-story تقابل روایت‌ها box — previously 2 slots here + 2 in the
  // separate بیشترین اختلاف نگاه box. The two boxes shared ~80% of
  // selection logic and only differed in visuals (word pair vs
  // percentage); merging into one 4-story box reduces duplication
  // and keeps the stronger word-pair affordance. On quiet news days
  // the box may render 2-3 items instead of 4 — acceptable.
  // battleReserved was gated + sorted + reserved up top (before the
  // most-viewed/left-text strips could eat these stories).
  for (const story of battleReserved) {
    if (battleItems.length >= 4) break;
    const analysis = allAnalyses[story.id];
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
          conservativeWords: preferUnused(cw, _usedConsWords),
          oppositionWords: preferUnused(ow, _usedOppWords),
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
            conservativeWords: preferUnused(cw, _usedConsWords),
            oppositionWords: preferUnused(ow, _usedOppWords),
            stateSummary,
            diasporaSummary,
          });
          continue;
        }
      }
    }
  }
  const battleIds = new Set(battleItems.map(b => b.storyId));

  const prefetchedTelegram: { storyId: string; analysis: TelegramAnalysis }[] = [];
  for (const id of telegramAnalysisIds) {
    const a = telegramByStoryId[id];
    if (a) prefetchedTelegram.push({ storyId: id, analysis: a });
  }

  return (
    <div dir={locale === "fa" ? "rtl" : "ltr"} className="mx-auto max-w-7xl px-0 md:px-6 lg:px-8">
      {!feedbackMode && <WelcomeModal />}

      {/* ════════════════════════════════════════════ */}
      {/* MOBILE LAYOUT — original scrolling list (phones only) */}
      {/* Gated purely by CSS (md:hidden) so this Server Component can */}
      {/* stay cache-eligible. The previous JS-based forceDesktop flag  */}
      {/* forced the whole page into dynamic (uncached) mode because    */}
      {/* it read searchParams. Desktop-on-mobile testing now uses      */}
      {/* Chrome DevTools' viewport toggle — no code path needed.       */}
      {/* ════════════════════════════════════════════ */}
      <div className="md:hidden">
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
          telegramAnalysisIds={telegramAnalysisIds}
          battleItems={battleItems}
          weeklyDigestContent={weeklyDigestData?.content || null}
          wrapStory={wrapStory}
          storyHref={storyHref}
        />
      </div>

      {/* ════════════════════════════════════════════ */}
      {/* DESKTOP LAYOUT (tablet and up) */}
      {/* ════════════════════════════════════════════ */}
      <div className="hidden md:block">

      {/* ═══ TOP SECTION: Blind spots | Hero | Telegram ═══ */}
      <div className="grid grid-cols-12 gap-0 border-b-2 border-slate-300 dark:border-slate-700">

        {/* RIGHT: Telegram discussions. Cap at ~780px so the hero card
            (image 16:9 + title + bias + tg strip) drives the row height
            instead of the sidebar. Lifting the cap made the sidebar
            content grow taller than the hero and pushed the whole row
            down; restoring a slightly-larger-than-700 ceiling keeps
            everything aligned. */}
        <div className="col-span-3 py-6 pe-6 border-e border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden" style={{ maxHeight: 780 }}>
          <h3 className="text-[18px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800 shrink-0">
            پیش‌بینی تحلیل‌های تلگرام
          </h3>
          <div className="flex-1 min-h-0 overflow-hidden">
            <TelegramDiscussions prefetchedData={prefetchedTelegram} storyIds={telegramAnalysisIds} locale={locale} />
          </div>
        </div>

        {/* CENTER: Hero story — image + title below */}
        {hero && (
          <div className="col-span-6 py-6 px-5">
            {wrapStory({ storyId: hero.id, title: localizedStoryTitle(hero, locale), imageUrl: hero.image_url }, (
              <Link href={storyHref(hero.id)} className="group block">
                <div className="relative aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage
                    src={hero.image_url}
                    className="h-full w-full object-cover"
                    sizes="(max-width: 1024px) 100vw, 50vw"
                    priority
                  />
                  {/* Update badge overlaid on the image, bottom-right.
                      Same staleness gate as UpdateBadge: a closed/frozen
                      story (no new article in >7d) must not show «بروزرسانی»
                      from a pure metric recompute. */}
                  {(() => {
                    const heroLuStale = hero.last_updated_at
                      ? Date.now() - new Date(hero.last_updated_at).getTime() >= 7 * 86400 * 1000
                      : false;
                    if (!heroLuStale && isUpdateBadgeFresh(hero.update_signal)) {
                      const heroReason = formatUpdateReason(hero.update_signal!);
                      return (
                        <div className="absolute bottom-2 right-2 inline-flex items-center gap-1.5 bg-orange-500/95 px-2 py-1 shadow-sm">
                          <span className="inline-block h-1.5 w-1.5 bg-white" />
                          <span className="text-[12px] font-bold text-white">بروزرسانی</span>
                          {heroReason && (
                            <span className="text-[12px] text-white/90">{heroReason}</span>
                          )}
                        </div>
                      );
                    }
                    if (
                      hero.last_updated_at &&
                      Date.now() - new Date(hero.last_updated_at).getTime() < 2 * 3600 * 1000
                    ) {
                      return (
                        <div className="absolute bottom-2 right-2 inline-flex items-center gap-1.5 bg-emerald-500/95 px-2 py-1 shadow-sm">
                          <span className="inline-block h-1.5 w-1.5 bg-white" />
                          <span className="text-[12px] font-bold text-white">مقالهٔ جدید</span>
                          <span className="text-[12px] text-white/90">{formatRelativeTime(hero.last_updated_at, "fa")}</span>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>
                <h1 className="mt-4 text-[28px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-3">
                  {localizedStoryTitle(hero, locale)}
                </h1>
              </Link>
            ))}
            <Meta story={hero} />
            {/* Hero leads with the دورنما prose synthesis (briefing_fa) when
                it exists, replacing the loaded-words bias bullets (Parham
                2026-06-03); bullets stay the fallback until doornama runs. */}
            {(() => {
              const analysis = allAnalyses[hero.id];
              const stateSummary = analysis?.state_summary_fa;
              const diasporaSummary = analysis?.diaspora_summary_fa;
              const doornama = analysis?.briefing_fa;
              const bias = analysis?.bias_explanation_fa;
              const points = doornama ? [] : splitBiasPoints(bias).slice(0, 2);
              if (!stateSummary && !diasporaSummary) {
                if (!doornama && !points.length) return null;
                return (
                  <div className="mt-3 space-y-1">
                    <UpdateDeltaCallout story={hero} field="bias" />
                    {doornama ? (
                      <p className="text-[15px] leading-7 text-slate-600 dark:text-slate-300 line-clamp-5">{doornama}</p>
                    ) : points.map((point, i) => (
                      <p key={i} className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-1">• {point}</p>
                    ))}
                  </div>
                );
              }
              return (
                <div className="mt-3">
                  <UpdateDeltaCallout story={hero} field="bias" />
                  {doornama ? (
                    <p className="mb-3 text-[15px] leading-7 text-slate-600 dark:text-slate-300 line-clamp-4">{doornama}</p>
                  ) : points.length > 0 && (
                    <div className="mb-3 space-y-1">
                      {points.map((point, i) => (
                        <p key={i} className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-1">• {point}</p>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    {stateSummary && (
                      <div className="border-r-2 border-inside-border pr-3">
                        <p className="text-[15px] font-bold text-inside-border dark:text-inside-border-dark mb-1">روایت درون‌مرزی</p>
                        <UpdateDeltaCallout story={hero} field="state" className="mb-1.5" />
                        <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-3">{stateSummary}</p>
                      </div>
                    )}
                    {diasporaSummary && (
                      <div className="border-r-2 border-outside-border pr-3">
                        <p className="text-[15px] font-bold text-outside-border dark:text-outside-border-dark mb-1">روایت برون‌مرزی</p>
                        <UpdateDeltaCallout story={hero} field="diaspora" className="mb-1.5" />
                        <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-3">{diasporaSummary}</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
            {/* Telegram discourse summary */}
            {heroTelegram?.discourse_summary && (
              <div className="mt-3 px-1">
                <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">
                  <span className="font-bold text-slate-600 dark:text-slate-300">تحلیل روایت‌های تلگرام.</span>
                  {" "}{heroTelegram.discourse_summary}
                </p>
                {heroTelegram.predictions && heroTelegram.predictions.length > 0 && (
                  <p className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-blue-500">پیش‌بینی:</span> {predictionText(heroTelegram.predictions[0])}
                  </p>
                )}
                {heroTelegram.key_claims && heroTelegram.key_claims.length > 0 && (
                  <p className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-amber-500">ادعا:</span> {claimText(heroTelegram.key_claims[0])}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* LEFT: Blind spot stories (one from each side) */}
        <div className="col-span-3 py-4 ps-6 border-s border-slate-200 dark:border-slate-800 space-y-4 flex flex-col justify-center">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <h2 className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</h2>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          {conservativeBlind && wrapStory({ storyId: conservativeBlind.id, title: localizedStoryTitle(conservativeBlind, locale), imageUrl: conservativeBlind.image_url }, (
            <Link
              href={storyHref(conservativeBlind.id)}
              aria-label={`نگاه یک‌جانبهٔ درون‌مرزی: ${localizedStoryTitle(conservativeBlind, locale)}`}
              className="group block border border-inside-border transition-shadow hover:shadow-md"
            >
              <div className="relative aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImageStatic src={conservativeBlind.has_real_image === false ? null : conservativeBlind.image_url} alt={localizedStoryTitle(conservativeBlind, locale)} className="h-full w-full object-cover" />
                {isUpdateBadgeFresh(conservativeBlind.update_signal) && (
                  <span className="absolute bottom-2 right-2 border border-orange-300 dark:border-orange-700 bg-orange-50/95 dark:bg-orange-900/80 px-1.5 py-0.5 text-[10px] font-bold text-orange-700 dark:text-orange-200 backdrop-blur-sm">
                    بروزرسانی{formatUpdateReason(conservativeBlind.update_signal!) ? ` · ${formatUpdateReason(conservativeBlind.update_signal!)}` : ""}
                  </span>
                )}
              </div>
              <div className="p-3">
                <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {localizedStoryTitle(conservativeBlind, locale)}
                </h3>
                <p className="mt-1.5 text-[15px] text-slate-400">
                  {conservativeBlind.diaspora_pct > 0 ? "بیشتر" : "فقط"} روایت درون‌مرزی · {conservativeBlind.article_count} مقاله
                </p>
              </div>
            </Link>
          ))}
          {oppositionBlind && wrapStory({ storyId: oppositionBlind.id, title: localizedStoryTitle(oppositionBlind, locale), imageUrl: oppositionBlind.image_url }, (
            <Link
              href={storyHref(oppositionBlind.id)}
              aria-label={`نگاه یک‌جانبهٔ برون‌مرزی: ${localizedStoryTitle(oppositionBlind, locale)}`}
              className="group block border border-outside-border transition-shadow hover:shadow-md"
            >
              <div className="relative aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImageStatic src={oppositionBlind.has_real_image === false ? null : oppositionBlind.image_url} alt={localizedStoryTitle(oppositionBlind, locale)} className="h-full w-full object-cover" />
                {isUpdateBadgeFresh(oppositionBlind.update_signal) && (
                  <span className="absolute bottom-2 right-2 border border-orange-300 dark:border-orange-700 bg-orange-50/95 dark:bg-orange-900/80 px-1.5 py-0.5 text-[10px] font-bold text-orange-700 dark:text-orange-200 backdrop-blur-sm">
                    بروزرسانی{formatUpdateReason(oppositionBlind.update_signal!) ? ` · ${formatUpdateReason(oppositionBlind.update_signal!)}` : ""}
                  </span>
                )}
              </div>
              <div className="p-3">
                <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {localizedStoryTitle(oppositionBlind, locale)}
                </h3>
                <p className="mt-1.5 text-[15px] text-orange-500">
                  {oppositionBlind.state_pct > 0 ? "بیشتر" : "فقط"} روایت برون‌مرزی · {oppositionBlind.article_count} مقاله
                </p>
              </div>
            </Link>
          ))}

        </div>
      </div>

      {/* ═══ WEEKLY BRIEFING + MOST DISPUTED ═══ */}
      {sorted.length > 1 && (
        <div className="grid grid-cols-12 gap-0 py-8 border-b border-slate-200 dark:border-slate-800">
          {/* Weekly briefing (8 cols) */}
          <div className="col-span-7 pe-6 border-e border-slate-200 dark:border-slate-800">
            <h2 className="text-[24px] font-black text-slate-900 dark:text-white mb-6">در روزهای گذشته ...</h2>
            <div className="ms-8">
              {leftTextStories.map((s, i) => {
                const analysis = allAnalyses[s.id];
                const stateSummary = analysis?.state_summary_fa;
                const diasporaSummary = analysis?.diaspora_summary_fa;
                const tg = leftTextTelegramById[s.id];
                return (
                  <div key={s.id} className={`py-5 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    {wrapStory({ storyId: s.id, title: localizedStoryTitle(s, locale), imageUrl: s.image_url }, (
                      <Link href={storyHref(s.id)} className="group block">
                        <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                          {localizedStoryTitle(s, locale)}
                        </h3>
                      </Link>
                    ))}
                    <UpdateBadge story={s} className="mt-2" />
                    <Meta story={s} />
                    {/* Two-side bias comparison — hero-style card without image */}
                    {stateSummary || diasporaSummary ? (
                      <div className="mt-3">
                        <UpdateDeltaCallout story={s} field="bias" />
                        <div className="grid grid-cols-2 gap-3">
                          {stateSummary && (
                            <div className="border-r-2 border-inside-border pr-3">
                              <p className="text-[15px] font-bold text-inside-border dark:text-inside-border-dark mb-1">روایت درون‌مرزی</p>
                              <UpdateDeltaCallout story={s} field="state" className="mb-1.5" />
                              <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{stateSummary}</p>
                            </div>
                          )}
                          {diasporaSummary && (
                            <div className="border-r-2 border-outside-border pr-3">
                              <p className="text-[15px] font-bold text-outside-border dark:text-outside-border-dark mb-1">روایت برون‌مرزی</p>
                              <UpdateDeltaCallout story={s} field="diaspora" className="mb-1.5" />
                              <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{diasporaSummary}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (() => {
                      const bias = analysis?.bias_explanation_fa;
                      if (!bias) return null;
                      const firstPoint = splitBiasPoints(bias)[0];
                      if (!firstPoint) return null;
                      return <p className="mt-1.5 text-[15px] leading-6 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>;
                    })()}
                    {/* Telegram strip — discourse + first prediction + first claim */}
                    {tg?.discourse_summary && (
                      <div className="mt-3 px-1">
                        <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">
                          <span className="font-bold text-slate-600 dark:text-slate-300">تحلیل روایت‌های تلگرام.</span>
                          {" "}{tg.discourse_summary}
                        </p>
                        {tg.predictions && tg.predictions.length > 0 && (
                          <p className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                            <span className="font-bold text-blue-500">پیش‌بینی:</span> {predictionText(tg.predictions[0])}
                          </p>
                        )}
                        {tg.key_claims && tg.key_claims.length > 0 && (
                          <p className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
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

          {/* Row 1 right column: a single تقابل روایت‌ها box showing up
              to 4 disputed stories with word-pair visuals. Previously
              split across two boxes (تقابل + بیشترین اختلاف نگاه) that
              shared ~80% of selection logic and only differed in
              visuals; consolidated 2026-04-21. */}
          <div className="col-span-5 ps-6 flex flex-col gap-4">
            <div className="relative flex-1 min-h-0 border border-slate-300 dark:border-slate-600 flex flex-col">
              {/* Box title sits ON the outer top border, centered, with
                  bg cutting through the border behind it. Absolute
                  positioning anchored to the outer box — title's center
                  aligns exactly with the border line (top: 0 +
                  -translate-y-1/2). Content area below gets generous
                  pt to breathe after the overlay. */}
              <span className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 text-[15px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-anthracite whitespace-nowrap">
                تقابل روایت‌ها
              </span>
              <div className="px-4 pb-6 pt-8 flex-1 flex flex-col gap-4 overflow-hidden">
                {(() => {
                  // battleItems is pre-computed above the JSX so the
                  // lower box («بیشترین اختلاف نگاه») can exclude these
                  // story IDs and avoid duplicating cards.
                  //
                  // Items size naturally (content-height). Previous
                  // attempt used `flex-1 min-h-0 overflow-hidden` so
                  // both items split 50/50 — that clipped the second
                  // bullet on whichever item had more content. Now
                  // both items grow to their content and the parent's
                  // overflow-hidden catches the rare overflow at the
                  // bottom rather than mid-item.
                  return battleItems.slice(0, 4).map((item, idx) => {
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
                          <div className="flex-1 py-3 bg-inside-border/10 dark:bg-inside-border/20 border-t-[3px] border-inside-border">
                            <p className="text-[15px] font-black text-inside-border dark:text-inside-border-dark line-clamp-1 px-2">
                              <RotatingWord words={item.conservativeWords} />
                            </p>
                            <p className="text-[15px] text-inside-border dark:text-inside-border-dark font-medium mt-1">درون‌مرزی</p>
                          </div>
                          <div className="flex-1 py-3 bg-outside-border/10 dark:bg-outside-border/20 border-t-[3px] border-outside-border">
                            <p className="text-[15px] font-black text-outside-border dark:text-outside-border-dark line-clamp-1 px-2">
                              <RotatingWord words={item.oppositionWords} />
                            </p>
                            <p className="text-[15px] text-outside-border dark:text-outside-border-dark font-medium mt-1">برون‌مرزی</p>
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
                              <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">
                                <span className="text-inside-border dark:text-inside-border-dark font-bold">(درون‌مرزی) </span>{item.stateSummary}
                              </p>
                            )}
                            {item.diasporaSummary && (
                              <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">
                                <span className="text-outside-border dark:text-outside-border-dark font-bold">(برون‌مرزی) </span>{item.diasporaSummary}
                              </p>
                            )}
                          </div>
                        )}
                      </>
                    );
                    return item.storyId ? wrapStory(
                      { storyId: item.storyId, title: item.title, imageUrl: null },
                      (
                        <Link href={storyHref(item.storyId)} className="group block">
                          {inner}
                        </Link>
                      ),
                      idx,
                    ) : (
                      <div key={idx}>{inner}</div>
                    );
                  });
                })()}
              </div>
            </div>
            {/* بیشترین اختلاف نگاه removed 2026-04-21: it duplicated
                ~80% of the تقابل روایت‌ها selection logic and only
                differed in visuals (percentage vs word pair). The
                word-pair affordance is stronger, so we consolidated
                into a single 4-story تقابل box above. The dispute
                percentage is still visible on every individual story
                card elsewhere on the homepage — no information lost.
            */}
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
              fallbackBullets = splitBiasPoints(bias).slice(0, 2);
            }
            return (
              <div key={s.id}>
                {/* Between-story separator — half width, transparent,
                    centered. Rendered ABOVE every card except the
                    first so spacing stays symmetric. */}
                {i > 0 && (
                  <div className="my-4 mx-auto w-1/2 h-px bg-slate-200/60 dark:bg-slate-700/40" />
                )}
                {wrapStory({ storyId: s.id, title: localizedStoryTitle(s, locale), imageUrl: s.image_url }, (
                <Link href={storyHref(s.id)} className="group flex items-stretch gap-6 py-5">
                  {/* DOM order: number → image → text. In RTL that
                      renders visually as [number][image][text] from
                      right to left, so the rank number sits to the
                      right of the image (Parham's ask). */}
                  <span className="text-[64px] font-black text-slate-200 dark:text-slate-700 shrink-0 leading-none -mt-1 w-[72px] text-start self-start">{tabularNum(i + 1)}</span>
                  <div className="w-48 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800 self-stretch">
                    <SafeImageStatic src={s.image_url} alt={localizedStoryTitle(s, locale)} className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {localizedStoryTitle(s, locale)}
                    </h3>
                    <UpdateBadge story={s} className="mt-1" />
                    <p className="text-[15px] text-slate-400 mt-1">
                      {tabularNum(s.article_count)} مقاله · {tabularNum(s.source_count)} رسانه
                      {s.state_pct > 0 && <span className="text-inside-border dark:text-inside-border-dark"> · درون‌مرزی {tabularNum(s.state_pct)}٪</span>}
                      {s.diaspora_pct > 0 && <span className="text-outside-border dark:text-outside-border-dark"> · برون‌مرزی {tabularNum(s.diaspora_pct)}٪</span>}
                    </p>
                    {(s.first_published_at || s.last_updated_at) && (
                      <p className="text-[12px] text-slate-400 dark:text-slate-500 mt-1">
                        {s.first_published_at && (
                          <>منتشر {formatRelativeTime(s.first_published_at, "fa")}</>
                        )}
                        {s.last_updated_at && s.first_published_at &&
                          new Date(s.last_updated_at).getTime() - new Date(s.first_published_at).getTime() > 6 * 3600 * 1000 && (
                          <> · بروزرسانی {formatRelativeTime(s.last_updated_at, "fa")}</>
                        )}
                      </p>
                    )}
                    {stateS && (
                      <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 mt-1.5 line-clamp-2">
                        <span className="text-inside-border dark:text-inside-border-dark font-bold">• </span>{stateS}
                      </p>
                    )}
                    {diasporaS && (
                      <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
                        <span className="text-outside-border dark:text-outside-border-dark font-bold">• </span>{diasporaS}
                      </p>
                    )}
                    {!stateS && !diasporaS && fallbackBullets.map((b, j) => (
                      <p key={j} className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-0.5 line-clamp-2">• {b}</p>
                    ))}
                    {tg?.predictions && tg.predictions.length > 0 && (
                      <p className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-1 line-clamp-2">
                        <span className="font-bold text-blue-500">پیش‌بینی:</span> {predictionText(tg.predictions[0])}
                      </p>
                    )}
                    {tg?.key_claims && tg.key_claims.length > 0 && (
                      <p className="text-[15px] leading-6 text-slate-400 dark:text-slate-500 mt-0.5 line-clamp-2">
                        <span className="font-bold text-amber-500">ادعا:</span> {claimText(tg.key_claims[0])}
                      </p>
                    )}
                  </div>
                </Link>
                ))}
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
  telegramAnalysisIds,
  battleItems,
  weeklyDigestContent,
  wrapStory,
  storyHref,
}: {
  hero: StoryBrief | undefined;
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
  conservativeBlind: StoryBrief | undefined;
  oppositionBlind: StoryBrief | undefined;
  allAnalyses: Record<string, { briefing_fa?: string | null; bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string } | null>;
  heroTelegram: { discourse_summary?: string; predictions?: any[]; key_claims?: any[] } | null;
  prefetchedTelegram: { storyId: string; analysis: TelegramAnalysis }[];
  telegramAnalysisIds: string[];
  battleItems: Array<{
    storyId: string;
    title: string;
    conservativeWords: string[];
    oppositionWords: string[];
    stateSummary: string;
    diasporaSummary: string;
  }>;
  weeklyDigestContent: string | null;
  wrapStory: (
    args: { storyId: string | undefined | null; title: string | undefined | null; imageUrl?: string | null },
    children: ReactNode,
    key?: React.Key,
  ) => ReactNode;
  storyHref: (id: string) => string;
}) {
  if (!hero) return null;

  // Hero narrative fields (same two-side bias comparison used on desktop)
  const heroAnalysis = allAnalyses[hero.id];
  const heroStateSummary = heroAnalysis?.state_summary_fa;
  const heroDiasporaSummary = heroAnalysis?.diaspora_summary_fa;
  const heroBias = heroAnalysis?.bias_explanation_fa;
  const heroDoornama = heroAnalysis?.briefing_fa;
  // دورنما prose replaces the bias bullets in the hero (Parham 2026-06-03).
  const heroBiasPoints = heroDoornama ? [] : splitBiasPoints(heroBias).slice(0, 2);

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
        {wrapStory({ storyId: hero.id, title: localizedStoryTitle(hero, locale), imageUrl: hero.image_url }, (
          <Link href={storyHref(hero.id)} className="block">
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
                {localizedStoryTitle(hero, locale)}
              </h1>
              <p className="mt-2 text-[15px] text-slate-400 dark:text-slate-500">
                {tabularNum(hero.source_count)} رسانه · {tabularNum(hero.article_count)} مقاله
              </p>
              {(hero.state_pct > 0 || hero.diaspora_pct > 0) && (
                <p className="text-[15px] mt-0.5">
                  {hero.state_pct > 0 && <span className="text-inside-border dark:text-inside-border-dark">درون‌مرزی {tabularNum(hero.state_pct)}٪</span>}
                  {hero.state_pct > 0 && hero.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
                  {hero.diaspora_pct > 0 && <span className="text-outside-border dark:text-outside-border-dark">برون‌مرزی {tabularNum(hero.diaspora_pct)}٪</span>}
                </p>
              )}
            </div>
          </Link>
        ))}

        {/* Two-side bias comparison — same structure as desktop hero */}
        <div className="px-4 pt-3">
          {(heroStateSummary || heroDiasporaSummary) ? (
            <>
              {heroDoornama ? (
                <p className="mb-3 text-[15px] leading-7 text-slate-600 dark:text-slate-300 line-clamp-5">{heroDoornama}</p>
              ) : heroBiasPoints.length > 0 && (
                <div className="mb-3 space-y-1">
                  {heroBiasPoints.map((point, i) => (
                    <p key={i} className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">• {point}</p>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                {heroStateSummary && (
                  <div className="border-r-2 border-inside-border pr-3">
                    <p className="text-[12px] font-bold text-inside-border dark:text-inside-border-dark mb-1">روایت درون‌مرزی</p>
                    <p className="text-[15px] leading-6 text-slate-600 dark:text-slate-400 line-clamp-5">{heroStateSummary}</p>
                  </div>
                )}
                {heroDiasporaSummary && (
                  <div className="border-r-2 border-outside-border pr-3">
                    <p className="text-[12px] font-bold text-outside-border dark:text-outside-border-dark mb-1">روایت برون‌مرزی</p>
                    <p className="text-[15px] leading-6 text-slate-600 dark:text-slate-400 line-clamp-5">{heroDiasporaSummary}</p>
                  </div>
                )}
              </div>
            </>
          ) : heroDoornama ? (
            <p className="text-[15px] leading-7 text-slate-600 dark:text-slate-300 line-clamp-5">{heroDoornama}</p>
          ) : heroBiasPoints.length > 0 ? (
            <div className="space-y-1">
              {heroBiasPoints.map((point, i) => (
                <p key={i} className="text-[15px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">• {point}</p>
              ))}
            </div>
          ) : null}
        </div>

        {/* Telegram discourse summary + first prediction + first claim (same as desktop hero) */}
        {heroTelegram?.discourse_summary && (
          <div className="px-4 pt-3 pb-4">
            <p className="text-[15px] leading-6 text-slate-600 dark:text-slate-400 line-clamp-3">
              <span className="font-bold text-slate-700 dark:text-slate-200">تحلیل روایت‌های تلگرام.</span>
              {" "}{heroTelegram.discourse_summary}
            </p>
            {firstPredictionText && (
              <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-500 mt-1.5 line-clamp-2">
                <span className="font-bold text-blue-500">پیش‌بینی:</span> {firstPredictionText}
              </p>
            )}
            {firstClaimText && (
              <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-500 mt-1 line-clamp-2">
                <span className="font-bold text-amber-500">ادعا:</span> {firstClaimText}
              </p>
            )}
          </div>
        )}
        {!heroTelegram?.discourse_summary && <div className="pb-4" />}
      </div>

      {/* ── 2. Telegram section (cross-story discussions) ── */}
      <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-[18px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
          تحلیل روایت‌های تلگرام
        </h3>
        <TelegramDiscussions prefetchedData={prefetchedTelegram} storyIds={telegramAnalysisIds} locale={locale} />
      </div>

      {/* ── 3. Blind spots ── */}
      {(conservativeBlind || oppositionBlind) && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <h2 className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</h2>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          <div className="space-y-4">
            {conservativeBlind && wrapStory({ storyId: conservativeBlind.id, title: localizedStoryTitle(conservativeBlind, locale), imageUrl: conservativeBlind.image_url }, (
              <Link
                href={storyHref(conservativeBlind.id)}
                aria-label={`نگاه یک‌جانبهٔ درون‌مرزی: ${localizedStoryTitle(conservativeBlind, locale)}`}
                className="group block border border-inside-border transition-shadow hover:shadow-md"
              >
                <div className="flex gap-3 p-3">
                  <div className="relative w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImageStatic src={conservativeBlind.has_real_image === false ? null : conservativeBlind.image_url} alt={localizedStoryTitle(conservativeBlind, locale)} className="h-full w-full object-cover" />
                    {isUpdateBadgeFresh(conservativeBlind.update_signal) && (
                      <span className="absolute bottom-0 inset-x-0 bg-orange-500/95 text-white text-center text-[9px] font-bold py-0.5">
                        بروزرسانی
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {localizedStoryTitle(conservativeBlind, locale)}
                    </h3>
                    <p className="mt-1 text-[15px] text-slate-400">
                      {conservativeBlind.diaspora_pct > 0 ? "بیشتر" : "فقط"} روایت درون‌مرزی · {conservativeBlind.article_count} مقاله
                    </p>
                  </div>
                </div>
              </Link>
            ))}
            {oppositionBlind && wrapStory({ storyId: oppositionBlind.id, title: localizedStoryTitle(oppositionBlind, locale), imageUrl: oppositionBlind.image_url }, (
              <Link
                href={storyHref(oppositionBlind.id)}
                aria-label={`نگاه یک‌جانبهٔ برون‌مرزی: ${localizedStoryTitle(oppositionBlind, locale)}`}
                className="group block border border-outside-border transition-shadow hover:shadow-md"
              >
                <div className="flex gap-3 p-3">
                  <div className="relative w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImageStatic src={oppositionBlind.has_real_image === false ? null : oppositionBlind.image_url} alt={localizedStoryTitle(oppositionBlind, locale)} className="h-full w-full object-cover" />
                    {isUpdateBadgeFresh(oppositionBlind.update_signal) && (
                      <span className="absolute bottom-0 inset-x-0 bg-orange-500/95 text-white text-center text-[9px] font-bold py-0.5">
                        بروزرسانی
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {localizedStoryTitle(oppositionBlind, locale)}
                    </h3>
                    <p className="mt-1 text-[15px] text-orange-500">
                      {oppositionBlind.state_pct > 0 ? "بیشتر" : "فقط"} روایت برون‌مرزی · {oppositionBlind.article_count} مقاله
                    </p>
                  </div>
                </div>
              </Link>
            ))}
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
            {mobileMostCovered.map((s, i) => wrapStory(
              { storyId: s.id, title: localizedStoryTitle(s, locale), imageUrl: s.image_url },
              (
                <Link href={storyHref(s.id)} className="group flex items-start gap-3 py-3">
                  <span className="text-[44px] font-black text-slate-200 dark:text-slate-700 shrink-0 w-12 text-center leading-none -mt-1">{tabularNum(i + 1)}</span>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {localizedStoryTitle(s, locale)}
                    </h3>
                    <UpdateBadge story={s} className="mt-0.5" />
                    <p className="text-[15px] text-slate-400 mt-0.5">
                      {tabularNum(s.article_count)} مقاله · {tabularNum(s.source_count)} رسانه
                      {s.state_pct > 0 && <span className="text-inside-border dark:text-inside-border-dark"> · درون‌مرزی {tabularNum(s.state_pct)}٪</span>}
                      {s.diaspora_pct > 0 && <span className="text-outside-border dark:text-outside-border-dark"> · برون‌مرزی {tabularNum(s.diaspora_pct)}٪</span>}
                    </p>
                  </div>
                </Link>
              ),
              s.id,
            ))}
          </div>
        </div>
      )}

      {/* ── 4b. تقابل روایت‌ها (narrative clash) ── */}
      {battleItems.length > 0 && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <span className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">تقابل روایت‌ها</span>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          <div className="space-y-5">
            {battleItems.slice(0, 3).map((item, idx) => {
              const inner = (
                <>
                  <h4 className="text-[16px] font-bold leading-snug text-slate-900 dark:text-white mb-3 group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                    {item.title}
                  </h4>
                  <div className="flex gap-0 text-center">
                    <div className="flex-1 py-2 bg-inside-border/10 dark:bg-inside-border/20 border-t-[3px] border-inside-border">
                      <p className="text-[15px] font-black text-inside-border dark:text-inside-border-dark line-clamp-1 px-2">
                        <RotatingWord words={item.conservativeWords} />
                      </p>
                      <p className="text-[12px] text-inside-border dark:text-inside-border-dark font-medium mt-1">درون‌مرزی</p>
                    </div>
                    <div className="flex-1 py-2 bg-outside-border/10 dark:bg-outside-border/20 border-t-[3px] border-outside-border">
                      <p className="text-[15px] font-black text-outside-border dark:text-outside-border-dark line-clamp-1 px-2">
                        <RotatingWord words={item.oppositionWords} />
                      </p>
                      <p className="text-[12px] text-outside-border dark:text-outside-border-dark font-medium mt-1">برون‌مرزی</p>
                    </div>
                  </div>
                  {(item.stateSummary || item.diasporaSummary) && (
                    <div className="mt-2.5 space-y-1">
                      {item.stateSummary && (
                        <p className="text-[12px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">
                          <span className="text-inside-border dark:text-inside-border-dark font-bold">(درون‌مرزی) </span>{item.stateSummary}
                        </p>
                      )}
                      {item.diasporaSummary && (
                        <p className="text-[12px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-2">
                          <span className="text-outside-border dark:text-outside-border-dark font-bold">(برون‌مرزی) </span>{item.diasporaSummary}
                        </p>
                      )}
                    </div>
                  )}
                </>
              );
              return item.storyId ? wrapStory(
                { storyId: item.storyId, title: item.title, imageUrl: null },
                (
                  <Link href={storyHref(item.storyId)} className="group block">
                    {inner}
                  </Link>
                ),
                idx,
              ) : (
                <div key={idx}>{inner}</div>
              );
            })}
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
              const firstPoint = splitBiasPoints(bias)[0];
              return wrapStory(
                { storyId: s.id, title: localizedStoryTitle(s, locale), imageUrl: s.image_url },
                (
                  <Link href={storyHref(s.id)} className="group block py-4">
                    <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {localizedStoryTitle(s, locale)}
                    </h3>
                    <UpdateBadge story={s} className="mt-1" />
                    <p className="mt-1 text-[15px] text-slate-400 dark:text-slate-500">
                      {tabularNum(s.source_count)} رسانه · {tabularNum(s.article_count)} مقاله
                      {s.state_pct > 0 && <span className="text-inside-border dark:text-inside-border-dark"> · درون‌مرزی {tabularNum(s.state_pct)}٪</span>}
                      {s.diaspora_pct > 0 && <span className="text-outside-border dark:text-outside-border-dark"> · برون‌مرزی {tabularNum(s.diaspora_pct)}٪</span>}
                    </p>
                    {firstPoint && (
                      <p className="mt-1.5 text-[15px] leading-6 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>
                    )}
                  </Link>
                ),
                s.id,
              );
            })}
          </div>
        </div>
      )}

      {/* ── 6. Weekly digest ── */}
      {weeklyDigestContent && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <WeeklyDigest prefetchedContent={weeklyDigestContent} />
        </div>
      )}

    </div>
  );
}
