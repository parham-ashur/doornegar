import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";
import type { StoryBrief } from "@/lib/types";
import WordsOfWeek from "@/components/home/WordsOfWeek";
import TelegramDiscussions from "@/components/home/TelegramDiscussions";
import WeeklyDigest from "@/components/home/WeeklyDigest";
import { formatRelativeTime, toFa } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string): Promise<T | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`${API}${path}`, { next: { revalidate: 30 }, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchSummary(storyId: string): Promise<string | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    const data = await res.json();
    return data.summary_fa || null;
  } catch {
    return null;
  }
}

async function fetchAnalysis(storyId: string): Promise<{ summary_fa?: string; bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchTelegramAnalysis(storyId: string): Promise<{ discourse_summary?: string; predictions?: string[]; key_claims?: string[]; worldviews?: { pro_regime?: string; opposition?: string } } | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`${API}/api/v1/social/stories/${storyId}/telegram-analysis`, { next: { revalidate: 300 }, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    const data = await res.json();
    return data.status === "ok" ? data.analysis : null;
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
  const hasSides = story.state_pct > 0 || story.diaspora_pct > 0;
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
            {story.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">محافظه‌کار {toFa(story.state_pct)}٪</span>}
            {story.state_pct > 0 && story.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
            {story.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">اپوزیسیون {toFa(story.diaspora_pct)}٪</span>}
          </p>
        )}
      </div>
    </div>
  );
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
  const [stories, blindspots] = await Promise.all([
    fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=50").then(d => d || []),
    fetchAPI<StoryBrief[]>("/api/v1/stories/blindspots?limit=10").then(d => d || []),
  ]);

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
        <p className="mt-2 text-sm text-slate-500">پس از اجرای خط‌لوله داده، موضوعات خبری اینجا نمایش داده می‌شوند</p>
      </div>
    );
  }

  // Blind spots: one from each side
  const conservativeBlind = blindspots.find(s => s.blindspot_type === "state_only");
  const oppositionBlind = blindspots.find(s => s.blindspot_type === "diaspora_only");

  // ── Deduplication: track which stories are placed ──
  const usedIds = new Set<string>();

  // Blind spots first (already picked above)
  if (conservativeBlind) usedIds.add(conservativeBlind.id);
  if (oppositionBlind) usedIds.add(oppositionBlind.id);

  const sorted = [...stories];

  // Hero
  const hero = sorted[0];
  if (hero) usedIds.add(hero.id);

  // Weekly briefing: next 4 not already used
  const leftTextStories = sorted.filter(s => !usedIds.has(s.id)).slice(0, 4);
  leftTextStories.forEach(s => usedIds.add(s.id));

  // Most viewed: blended score = views + trending + recency bonus
  // When views are sparse, trending score dominates; as views grow, real popularity takes over
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
    .slice(0, 5);
  mostViewed.forEach(s => usedIds.add(s.id));

  // Most disputed: not already used
  const disputedCandidates = [...stories]
    .filter(s => s.state_pct > 0 && s.diaspora_pct > 0 && !s.is_blindspot && !usedIds.has(s.id))
    .sort((a, b) => Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct));
  let mostDisputed = disputedCandidates[0] || null;
  let secondDisputed = disputedCandidates[1] || null;
  if (mostDisputed) usedIds.add(mostDisputed.id);
  if (secondDisputed) usedIds.add(secondDisputed.id);

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

  // ── Fetch summaries (all in parallel) ──
  const allStoriesForSummary = new Set<string>();
  if (hero) allStoriesForSummary.add(hero.id);
  for (const s of [...leftTextStories, ...mostViewed, ...overflow]) {
    allStoriesForSummary.add(s.id);
  }
  for (const sec of sections) {
    for (const s of sec.stories) allStoriesForSummary.add(s.id);
  }
  const summaryIds = Array.from(allStoriesForSummary);
  const summaryResults = await Promise.all(summaryIds.map((id) => fetchSummary(id)));
  const allSummaries: Record<string, string | null> = {};
  summaryIds.forEach((id, i) => { allSummaries[id] = summaryResults[i]; });

  // Fetch full analysis for weekly briefing + most disputed + most read
  const briefingStories = leftTextStories;
  const analysisFetchIds = [hero.id, ...briefingStories.map(s => s.id)];
  // Include all disputed candidates so we can re-sort by dispute_score
  for (const s of disputedCandidates) {
    if (!analysisFetchIds.includes(s.id)) analysisFetchIds.push(s.id);
  }
  for (const s of mostViewed) {
    if (!analysisFetchIds.includes(s.id)) analysisFetchIds.push(s.id);
  }
  const analysisResults = await Promise.all(analysisFetchIds.map((id) => fetchAnalysis(id)));
  const allAnalyses: Record<string, { bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null> = {};
  analysisFetchIds.forEach((id, i) => { allAnalyses[id] = analysisResults[i]; });

  // Fetch Telegram analysis for hero story
  const heroTelegram = hero ? await fetchTelegramAnalysis(hero.id) : null;

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

  // Prefetch telegram analyses server-side for homepage (no client API calls)
  const telegramAnalysisIds = sorted.slice(0, 5).map(s => s.id);
  const telegramResults = await Promise.all(
    telegramAnalysisIds.map(id => fetchTelegramAnalysis(id))
  );
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
        />
      )}

      {/* ════════════════════════════════════════════ */}
      {/* DESKTOP LAYOUT (tablet and up, or force-enabled) */}
      {/* ════════════════════════════════════════════ */}
      <div className={forceDesktop ? "block" : "hidden md:block"}>

      {/* ═══ TOP SECTION: Blind spots | Hero | Telegram ═══ */}
      <div className="grid grid-cols-12 gap-0 border-b-2 border-slate-300 dark:border-slate-700">

        {/* RIGHT: Telegram discussions — fixed height matching hero */}
        <div className="col-span-3 py-6 pl-6 border-l border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden" style={{ maxHeight: 700 }}>
          <h3 className="text-[13px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800 shrink-0">
            تحلیل روایت‌های تلگرام
          </h3>
          <div className="flex-1 min-h-0 overflow-hidden">
            <TelegramDiscussions prefetchedData={prefetchedTelegram} locale={locale} />
          </div>

          {/* Words of the day — pushed to bottom */}
          <div className="shrink-0 pt-4 border-t border-slate-200 dark:border-slate-800">
            <WordsOfWeek />
          </div>
        </div>

        {/* CENTER: Hero story — image + title below */}
        {hero && (
          <div className="col-span-6 py-6 px-5">
            <Link href={`/${locale}/stories/${hero.id}`} className="group block">
              <div className="aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
              </div>
              <h1 className="mt-4 text-[28px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-3">
                {hero.title_fa}
              </h1>
            </Link>
            <Meta story={hero} />
            {/* Two-side bias comparison */}
            {(() => {
              const analysis = allAnalyses[hero.id];
              const stateSummary = analysis?.state_summary_fa;
              const diasporaSummary = analysis?.diaspora_summary_fa;
              if (!stateSummary && !diasporaSummary) {
                // Fallback to bias_explanation_fa points
                const bias = analysis?.bias_explanation_fa;
                const points = bias?.split(/[.؛]/).map((p: string) => p.trim()).filter((p: string) => p.length > 10).slice(0, 2) || [];
                if (!points.length) return null;
                return (
                  <div className="mt-3 space-y-1">
                    {points.map((point, i) => (
                      <p key={i} className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">• {point}</p>
                    ))}
                  </div>
                );
              }
              return (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {stateSummary && (
                    <div className="border-r-2 border-[#1e3a5f] pr-3">
                      <p className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300 mb-1">روایت محافظه‌کار</p>
                      <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">{stateSummary}</p>
                    </div>
                  )}
                  {diasporaSummary && (
                    <div className="border-r-2 border-[#ea580c] pr-3">
                      <p className="text-[13px] font-bold text-[#ea580c] dark:text-orange-400 mb-1">روایت اپوزیسیون</p>
                      <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">{diasporaSummary}</p>
                    </div>
                  )}
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
                    <span className="font-bold text-blue-500">پیش‌بینی:</span> {typeof heroTelegram.predictions[0] === "string" ? heroTelegram.predictions[0] : (heroTelegram.predictions[0] as any).text || ""}
                  </p>
                )}
                {heroTelegram.key_claims && heroTelegram.key_claims.length > 0 && (
                  <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-amber-500">ادعا:</span> {typeof heroTelegram.key_claims[0] === "string" ? heroTelegram.key_claims[0] : (heroTelegram.key_claims[0] as any).text || ""}
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
            <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</span>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          {conservativeBlind && (
            <Link href={`/${locale}/stories/${conservativeBlind.id}`} className="group block border-[3px] border-[#1e3a5f] shadow-[0_0_12px_rgba(30,58,95,0.4)] hover:shadow-[0_0_20px_rgba(30,58,95,0.6)] transition-shadow animate-pulse-glow-blue">
              <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={conservativeBlind.image_url} className="h-full w-full object-cover" />
              </div>
              <div className="p-3">
                <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {conservativeBlind.title_fa}
                </h3>
                <p className="mt-1.5 text-[13px] text-slate-400">
                  فقط روایت محافظه‌کار · {conservativeBlind.article_count} مقاله
                </p>
              </div>
            </Link>
          )}
          {oppositionBlind && (
            <Link href={`/${locale}/stories/${oppositionBlind.id}`} className="group block border-[3px] border-[#ea580c] shadow-[0_0_12px_rgba(234,88,12,0.4)] hover:shadow-[0_0_20px_rgba(234,88,12,0.6)] transition-shadow animate-pulse-glow-orange">
              <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={oppositionBlind.image_url} className="h-full w-full object-cover" />
              </div>
              <div className="p-3">
                <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {oppositionBlind.title_fa}
                </h3>
                <p className="mt-1.5 text-[13px] text-orange-500">
                  فقط روایت اپوزیسیون · {oppositionBlind.article_count} مقاله
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
              {leftTextStories.map((s, i) => (
                <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                  className={`group block py-5 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                  <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                    {s.title_fa}
                  </h3>
                  <Meta story={s} />
                  {(() => {
                    const bias = allAnalyses[s.id]?.bias_explanation_fa;
                    if (!bias) return null;
                    const firstPoint = bias.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
                    if (!firstPoint) return null;
                    return <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>;
                  })()}
                </Link>
              ))}
            </div>
          </div>

          {/* Most read (5 cols) */}
          <div className="col-span-5 pr-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">پرمخاطب‌ترین</span>
              <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            </div>

            <div className="space-y-0">
              {mostViewed.map((s, i) => {
                const bias = allAnalyses[s.id]?.bias_explanation_fa;
                const firstPoint = bias?.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
                return (
                  <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                    className={`group flex items-start gap-3 py-4 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    <span className="text-[24px] font-black text-slate-200 dark:text-slate-700 shrink-0 w-8 text-center mt-0.5">{toFa(i + 1)}</span>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {s.title_fa}
                      </h3>
                      <p className="text-[14px] text-slate-400 mt-1">
                        {toFa(s.article_count)} مقاله · {toFa(s.source_count)} رسانه
                        {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                        {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
                      </p>
                      {firstPoint && (
                        <p className="text-[14px] text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">• {firstPoint}</p>
                      )}
                        </div>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ═══ COMMON GROUND + BATTLE OF NUMBERS ═══ */}
      <div className="grid grid-cols-2 gap-6 py-8 border-b border-slate-200 dark:border-slate-800 items-stretch">

        {/* Most disputed */}
        <div>
          <div className="border border-slate-300 dark:border-slate-600 h-full flex flex-col">
            <div className="flex items-center -mt-3 mx-4">
              <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
              <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">بیشترین اختلاف نگاه</span>
              <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
            </div>
            <div className="px-4 pb-4 pt-2 flex-1">
              {[mostDisputed, secondDisputed].filter(Boolean).map((story, i) => {
                const s = story!;
                const analysis = allAnalyses[s.id];
                const stateSummary = analysis?.state_summary_fa;
                const diasporaSummary = analysis?.diaspora_summary_fa;
                return (
                  <div key={s.id} className={`py-4 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    <Link href={`/${locale}/stories/${s.id}`} className="group block">
                      <h4 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {s.title_fa}
                      </h4>
                      <div className="mt-1 flex items-center justify-end gap-3 text-[13px]">
                        <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">محافظه‌کار {toFa(s.state_pct)}٪</span>
                        <span className="text-[#ea580c] dark:text-orange-400 font-medium">اپوزیسیون {toFa(s.diaspora_pct)}٪</span>
                      </div>
                    </Link>
                    {(stateSummary || diasporaSummary) && (
                      <div className="mt-2 space-y-1">
                        {stateSummary && (
                          <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">
                            <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">• </span>{stateSummary}
                          </p>
                        )}
                        {diasporaSummary && (
                          <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">
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
        </div>

        {/* Battle of numbers */}
        <div>
          <div className="border border-slate-300 dark:border-slate-600 h-full flex flex-col">
            <div className="flex items-center -mt-3 mx-4">
              <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
              <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">تقابل روایت‌ها</span>
              <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
            </div>

          <div className="space-y-5 px-4 pb-4 pt-2 flex-1 flex flex-col justify-between">
            {(() => {
              // Build battle items from the top 2 most disputed stories
              type BattleItem = { title: string; conservative: string; opposition: string; conservativeLabel: string; oppositionLabel: string };
              const battleItems: BattleItem[] = [];

              for (const story of [mostDisputed, secondDisputed]) {
                if (!story) continue;
                const analysis = allAnalyses[story.id];
                if (!analysis) continue;

                const words = analysis.loaded_words;
                const stateSummary = analysis.state_summary_fa;
                const diasporaSummary = analysis.diaspora_summary_fa;
                const biasText = analysis.bias_explanation_fa;

                // Strategy 1: Use loaded_words if both sides have terms
                if (words?.conservative?.length && words?.opposition?.length) {
                  battleItems.push({
                    title: story.title_fa || "",
                    conservative: `«${words.conservative[0].replace(/[«»]/g, "")}»`,
                    opposition: `«${words.opposition[0].replace(/[«»]/g, "")}»`,
                    conservativeLabel: words.conservative.length > 1 ? words.conservative.slice(1, 3).join("، ") : "روایت محافظه‌کار",
                    oppositionLabel: words.opposition.length > 1 ? words.opposition.slice(1, 3).join("، ") : "روایت اپوزیسیون",
                  });
                  continue;
                }

                // Strategy 2: Extract «quoted» pairs from bias_explanation_fa
                if (biasText) {
                  const quotes = biasText.match(/«[^»]+»/g);
                  if (quotes && quotes.length >= 2) {
                    battleItems.push({
                      title: story.title_fa || "",
                      conservative: quotes[0],
                      opposition: quotes[1],
                      conservativeLabel: stateSummary ? stateSummary.slice(0, 40) + (stateSummary.length > 40 ? "..." : "") : "روایت محافظه‌کار",
                      oppositionLabel: diasporaSummary ? diasporaSummary.slice(0, 40) + (diasporaSummary.length > 40 ? "..." : "") : "روایت اپوزیسیون",
                    });
                    continue;
                  }
                }

                // Strategy 3: Use state_summary_fa vs diaspora_summary_fa as contrasting framings
                if (stateSummary && diasporaSummary) {
                  const stateShort = stateSummary.length > 25 ? stateSummary.slice(0, 25) + "..." : stateSummary;
                  const diasporaShort = diasporaSummary.length > 25 ? diasporaSummary.slice(0, 25) + "..." : diasporaSummary;
                  battleItems.push({
                    title: story.title_fa || "",
                    conservative: `«${stateShort}»`,
                    opposition: `«${diasporaShort}»`,
                    conservativeLabel: "خلاصه رسانه‌های محافظه‌کار",
                    oppositionLabel: "خلاصه رسانه‌های اپوزیسیون",
                  });
                }
              }

              // Fallback: hardcoded content if no real data available
              if (battleItems.length === 0) {
                battleItems.push(
                  {
                    title: "تلفات حملات هوایی",
                    conservative: "«شهدای مدافع»",
                    opposition: "«صدها غیرنظامی»",
                    conservativeLabel: "تلفات محدود نظامی",
                    oppositionLabel: "کشتار گسترده مردم",
                  },
                  {
                    title: "قطع اینترنت",
                    conservative: "«اختلال موقت»",
                    opposition: "«۴۰ روز قطع کامل»",
                    conservativeLabel: "محدودیت امنیتی",
                    oppositionLabel: "قطع عمدی و سراسری",
                  },
                );
              }

              return battleItems.slice(0, 2).map((item, idx) => (
                <div key={idx}>
                  <p className="text-[13px] font-bold text-slate-900 dark:text-white mb-3 line-clamp-1">{item.title}</p>
                  <div className="flex gap-0 text-center">
                    <div className="flex-1 py-3 bg-[#1e3a5f]/10 dark:bg-blue-900/20 border-t-[3px] border-[#1e3a5f]">
                      <p className={`${item.conservative.length > 20 ? "text-[24px]" : "text-[14px]"} font-black text-[#1e3a5f] dark:text-blue-300 line-clamp-1 px-2`}>{item.conservative}</p>
                      <p className="text-[13px] text-slate-500 mt-1 line-clamp-1 px-2">{item.conservativeLabel}</p>
                      <p className="text-[13px] text-[#1e3a5f] dark:text-blue-300 font-medium mt-0.5">محافظه‌کار</p>
                    </div>
                    <div className="flex-1 py-3 bg-[#ea580c]/10 dark:bg-orange-900/20 border-t-[3px] border-[#ea580c]">
                      <p className={`${item.opposition.length > 20 ? "text-[24px]" : "text-[14px]"} font-black text-[#ea580c] dark:text-orange-400 line-clamp-1 px-2`}>{item.opposition}</p>
                      <p className="text-[13px] text-slate-500 mt-1 line-clamp-1 px-2">{item.oppositionLabel}</p>
                      <p className="text-[13px] text-[#ea580c] dark:text-orange-400 font-medium mt-0.5">اپوزیسیون</p>
                    </div>
                  </div>
                </div>
              ));
            })()}
          </div>
          </div>
        </div>

      </div>

      {/* ═══ WEEKLY DIGEST ═══ */}
      <div className="py-8">
        <WeeklyDigest />
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
}: {
  hero: StoryBrief | undefined;
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
  conservativeBlind: StoryBrief | undefined;
  oppositionBlind: StoryBrief | undefined;
  allAnalyses: Record<string, { bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string } | null>;
}) {
  if (!hero) return null;

  // Extract first bias point for hero
  const heroBias = allAnalyses[hero.id]?.bias_explanation_fa;
  const heroPoint = heroBias?.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);

  // Weekly briefing: stories 1-3
  const briefingStories = stories.slice(1, 4);

  // Most covered (by article count), deduplicated
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
  mobileMostCovered.forEach(s => mobileUsedIds.add(s.id));

  const remaining = stories.filter(s => !mobileUsedIds.has(s.id)).slice(0, 8);

  return (
    <div className="md:hidden">

      {/* ── 1. Hero story ── */}
      <Link
        href={`/${locale}/stories/${hero.id}`}
        className="block border-b border-slate-200 dark:border-slate-800"
      >
        <div className="aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
          <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
        </div>
        <div className="px-4 py-4">
          <h1 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white line-clamp-3">
            {hero.title_fa}
          </h1>
          <div className="mt-2">
            <p className="text-[13px] text-slate-400 dark:text-slate-500">
              {toFa(hero.source_count)} رسانه · {toFa(hero.article_count)} مقاله
            </p>
            {(hero.state_pct > 0 || hero.diaspora_pct > 0) && (
              <p className="text-[13px] mt-0.5">
                {hero.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">محافظه‌کار {toFa(hero.state_pct)}٪</span>}
                {hero.state_pct > 0 && hero.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
                {hero.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">اپوزیسیون {toFa(hero.diaspora_pct)}٪</span>}
              </p>
            )}
          </div>
          {heroPoint && (
            <p className="mt-2 text-[14px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">• {heroPoint}</p>
          )}
        </div>
      </Link>

      {/* ── 2. Blind spots ── */}
      {(conservativeBlind || oppositionBlind) && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</span>
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
          </div>
          <div className="space-y-4">
            {conservativeBlind && (
              <Link href={`/${locale}/stories/${conservativeBlind.id}`}
                className="group block border-[3px] border-[#1e3a5f] shadow-[0_0_12px_rgba(30,58,95,0.4)] animate-pulse-glow-blue">
                <div className="flex gap-3 p-3">
                  <div className="w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={conservativeBlind.image_url} className="h-full w-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {conservativeBlind.title_fa}
                    </h3>
                    <p className="mt-1 text-[13px] text-slate-400">
                      فقط روایت محافظه‌کار · {conservativeBlind.article_count} مقاله
                    </p>
                  </div>
                </div>
              </Link>
            )}
            {oppositionBlind && (
              <Link href={`/${locale}/stories/${oppositionBlind.id}`}
                className="group block border-[3px] border-[#ea580c] shadow-[0_0_12px_rgba(234,88,12,0.4)] animate-pulse-glow-orange">
                <div className="flex gap-3 p-3">
                  <div className="w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={oppositionBlind.image_url} className="h-full w-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {oppositionBlind.title_fa}
                    </h3>
                    <p className="mt-1 text-[13px] text-orange-500">
                      فقط روایت اپوزیسیون · {oppositionBlind.article_count} مقاله
                    </p>
                  </div>
                </div>
              </Link>
            )}
          </div>
        </div>
      )}

      {/* ── 3. Weekly briefing ── */}
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
                  <p className="mt-1 text-[13px] text-slate-400 dark:text-slate-500">
                    {toFa(s.source_count)} رسانه · {toFa(s.article_count)} مقاله
                    {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                    {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
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

      {/* ── 4. Most covered ── */}
      {mobileMostCovered.length > 0 && (
        <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">پرمخاطب‌ترین</span>
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
                  <p className="text-[13px] text-slate-400 mt-0.5">
                    {toFa(s.article_count)} مقاله · {toFa(s.source_count)} رسانه
                    {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                    {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ── 5. Telegram analysis ── */}
      <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-[13px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
          تحلیل روایت‌های تلگرام
        </h3>
        <TelegramDiscussions storyIds={stories.slice(0, 5).map(s => s.id)} locale={locale} />
      </div>

      {/* ── 5. Words of the day ── */}
      <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
        <WordsOfWeek />
      </div>

      {/* ── 6. Remaining stories ── */}
      {remaining.length > 0 && (
        <div className="divide-y divide-slate-200 dark:divide-slate-800">
          {remaining.map((s) => (
            <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group block px-4 py-4">
              <h3 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                {s.title_fa}
              </h3>
              <p className="mt-1 text-[13px] text-slate-400 dark:text-slate-500">
                {toFa(s.source_count)} رسانه · {toFa(s.article_count)} مقاله
                {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
              </p>
              {summaries[s.id] && (
                <p className="mt-1.5 text-[14px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                  {summaries[s.id]}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
