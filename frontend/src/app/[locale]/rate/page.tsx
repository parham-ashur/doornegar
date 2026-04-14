import { setRequestLocale } from "next-intl/server";
import type { StoryBrief } from "@/lib/types";
import RateHomeClient from "@/components/home/RateHomeClient";

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

export default async function RatePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const [stories, blindspots] = await Promise.all([
    fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=50").then(d => d || []),
    fetchAPI<StoryBrief[]>("/api/v1/stories/blindspots?limit=10").then(d => d || []),
  ]);

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
      </div>
    );
  }

  // Blind spots
  const conservativeBlind = blindspots.find(s => s.blindspot_type === "state_only") || null;
  const oppositionBlind = blindspots.find(s => s.blindspot_type === "diaspora_only") || null;

  // Deduplication
  const usedIds = new Set<string>();
  if (conservativeBlind) usedIds.add(conservativeBlind.id);
  if (oppositionBlind) usedIds.add(oppositionBlind.id);

  const sorted = [...stories];
  const hero = sorted[0];
  if (hero) usedIds.add(hero.id);

  const leftTextStories = sorted.filter(s => !usedIds.has(s.id)).slice(0, 4);
  leftTextStories.forEach(s => usedIds.add(s.id));

  const now = Date.now();
  const mostViewed = [...sorted]
    .filter(s => !usedIds.has(s.id))
    .map(s => {
      const views = s.view_count || 0;
      const recencyHours = s.updated_at ? (now - new Date(s.updated_at).getTime()) / 3600000 : 100;
      const recencyBonus = Math.max(0, 1 - recencyHours / 72);
      const score = views * 2 + s.trending_score + recencyBonus * 10 + s.article_count * 0.5;
      return { ...s, _popScore: score };
    })
    .sort((a, b) => b._popScore - a._popScore)
    .slice(0, 5);
  mostViewed.forEach(s => usedIds.add(s.id));

  const disputedCandidates = [...stories]
    .filter(s => s.state_pct > 0 && s.diaspora_pct > 0 && !s.is_blindspot && !usedIds.has(s.id))
    .sort((a, b) => Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct));

  // Fetch summaries + analyses
  const allStoriesForSummary = new Set<string>();
  if (hero) allStoriesForSummary.add(hero.id);
  for (const s of [...leftTextStories, ...mostViewed]) allStoriesForSummary.add(s.id);
  const summaryIds = Array.from(allStoriesForSummary);
  const summaryResults = await Promise.all(summaryIds.map(id => fetchSummary(id)));
  const allSummaries: Record<string, string | null> = {};
  summaryIds.forEach((id, i) => { allSummaries[id] = summaryResults[i]; });

  const analysisFetchIds = [hero.id, ...leftTextStories.map(s => s.id)];
  for (const s of disputedCandidates) {
    if (!analysisFetchIds.includes(s.id)) analysisFetchIds.push(s.id);
  }
  for (const s of mostViewed) {
    if (!analysisFetchIds.includes(s.id)) analysisFetchIds.push(s.id);
  }
  const analysisResults = await Promise.all(analysisFetchIds.map(id => fetchAnalysis(id)));
  const allAnalyses: Record<string, { bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null> = {};
  analysisFetchIds.forEach((id, i) => { allAnalyses[id] = analysisResults[i]; });

  const heroTelegram = hero ? await fetchTelegramAnalysis(hero.id) : null;

  // Re-sort disputed by dispute_score
  const disputedResorted = [...disputedCandidates].sort((a, b) => {
    const scoreA = allAnalyses[a.id]?.dispute_score ?? null;
    const scoreB = allAnalyses[b.id]?.dispute_score ?? null;
    if (scoreA !== null && scoreB !== null) return scoreB - scoreA;
    if (scoreA !== null) return -1;
    if (scoreB !== null) return 1;
    return Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct);
  });
  const mostDisputed = disputedResorted[0] || null;
  const secondDisputed = disputedResorted[1] || null;

  // Prefetch telegram
  const telegramAnalysisIds = sorted.slice(0, 5).map(s => s.id);
  const telegramResults = await Promise.all(telegramAnalysisIds.map(id => fetchTelegramAnalysis(id)));
  const prefetchedTelegram: { storyId: string; analysis: any }[] = [];
  telegramAnalysisIds.forEach((id, i) => {
    if (telegramResults[i]) prefetchedTelegram.push({ storyId: id, analysis: telegramResults[i] });
  });

  return (
    <RateHomeClient
      locale={locale}
      hero={hero}
      sorted={sorted}
      leftTextStories={leftTextStories}
      mostViewed={mostViewed}
      mostDisputed={mostDisputed}
      secondDisputed={secondDisputed}
      conservativeBlind={conservativeBlind}
      oppositionBlind={oppositionBlind}
      allSummaries={allSummaries}
      allAnalyses={allAnalyses}
      heroTelegram={heroTelegram}
      prefetchedTelegram={prefetchedTelegram}
    />
  );
}
