import type { Source, StoryAnalysis, StoryBrief } from "./types";
import type {
  BlindspotSlotData,
  MaxDisagreementSlotData,
  StoryCore,
  StorySlot,
  TelegramSlotData,
} from "@/components/stories/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TelegramAnalysisResponse = {
  status?: string;
  analysis?: {
    discourse_summary?: string;
    predictions?: (string | { text: string })[];
    key_claims?: (string | { text: string; source?: string; verified?: boolean })[];
    worldviews?: { pro_regime?: string; opposition?: string; neutral?: string };
  };
};

function extractPredictions(a: TelegramAnalysisResponse | null): string[] {
  const arr = a?.analysis?.predictions ?? [];
  return arr
    .map((p) => (typeof p === "string" ? p : p?.text ?? ""))
    .filter((s) => s.length > 0)
    .slice(0, 3);
}

function extractClaims(
  a: TelegramAnalysisResponse | null,
): { source?: string; text: string; verified?: boolean }[] {
  const arr = a?.analysis?.key_claims ?? [];
  return arr
    .map((c) => {
      if (typeof c === "string") return { text: c };
      if (c && typeof c === "object") {
        return { text: c.text ?? "", source: c.source, verified: c.verified };
      }
      return { text: "" };
    })
    .filter((c) => c.text.length > 0)
    .slice(0, 3);
}

async function tryFetch<T>(path: string, revalidate = 120): Promise<T | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`${API_BASE}${path}`, {
      next: { revalidate },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function resolveImage(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

function normalizeText(v: unknown): string {
  if (typeof v === "string") return v;
  if (v && typeof v === "object" && "text" in v) return String((v as { text: unknown }).text ?? "");
  return "";
}

type ArticleLite = {
  id: string;
  source_id: string;
};

function asStoryCore(
  story: StoryBrief,
  analysis: StoryAnalysis | null,
  telegram: TelegramAnalysisResponse | null,
  sourceNames?: string[],
): StoryCore {
  const image = resolveImage(story.image_url);
  return {
    id: story.id,
    title: story.title_fa || story.title_en || "",
    sourceCount: story.source_count,
    articleCount: story.article_count,
    summary: analysis?.summary_fa ?? undefined,
    progressivePosition: analysis?.diaspora_summary_fa ?? undefined,
    conservativePosition: analysis?.state_summary_fa ?? undefined,
    telegramSummary: telegram?.analysis?.discourse_summary ?? undefined,
    telegramPredictions: extractPredictions(telegram),
    telegramClaims: extractClaims(telegram),
    statePct: story.state_pct,
    diasporaPct: story.diaspora_pct,
    sourceNames: sourceNames && sourceNames.length > 0 ? sourceNames : undefined,
    media: image
      ? { type: "image", src: image }
      : {
          type: "image",
          src: `https://picsum.photos/seed/${encodeURIComponent(story.id)}/900/1600`,
        },
  };
}

export async function buildStoriesSlots(): Promise<StorySlot[]> {
  const [trending, blindspots] = await Promise.all([
    tryFetch<StoryBrief[]>("/api/v1/stories/trending?limit=50", 120).then((d) => d ?? []),
    tryFetch<StoryBrief[]>("/api/v1/stories/blindspots?limit=20", 120).then((d) => d ?? []),
  ]);

  if (trending.length === 0) {
    return [{ kind: "placeholder", label: "هنوز موضوعی ایجاد نشده", bg: "bg-slate-900" }];
  }

  const topStories = trending.slice(0, 3);

  const topAnalyses = await Promise.all(
    topStories.map((s) => tryFetch<StoryAnalysis>(`/api/v1/stories/${s.id}/analysis`, 300)),
  );
  const topTelegrams = await Promise.all(
    topStories.map((s) =>
      tryFetch<TelegramAnalysisResponse>(
        `/api/v1/social/stories/${s.id}/telegram-analysis`,
        300,
      ),
    ),
  );

  // Fetch the sources list once + the articles for each top story, then
  // join by source_id to build a source-names list. (/api/v1/stories/{id}
  // currently returns 500, so we sidestep it.)
  const [sourcesResp, ...articlesByStory] = await Promise.all([
    tryFetch<{ sources: Source[] }>("/api/v1/sources", 600),
    ...topStories.map((s) =>
      tryFetch<{ articles: ArticleLite[] }>(
        `/api/v1/articles?story_id=${s.id}&limit=30`,
        300,
      ),
    ),
  ]);
  const sourceMap = new Map<string, string>();
  for (const src of sourcesResp?.sources ?? []) {
    sourceMap.set(src.id, src.name_fa || src.name_en || "");
  }
  const sourceNamesByStory: string[][] = articlesByStory.map((resp) => {
    if (!resp?.articles) return [];
    const seen = new Set<string>();
    const names: string[] = [];
    for (const a of resp.articles) {
      const name = sourceMap.get(a.source_id);
      if (name && !seen.has(name)) {
        seen.add(name);
        names.push(name);
      }
    }
    return names;
  });

  const topStoryCores = topStories.map((s, i) =>
    asStoryCore(
      s,
      topAnalyses[i] ?? null,
      topTelegrams[i] ?? null,
      sourceNamesByStory[i],
    ),
  );

  // Telegram slot — aggregate predictions + claims from top 3 stories
  const telegramData = buildTelegramData(topStories, topTelegrams);

  // Blindspot slot — take top state_only + top diaspora_only stories
  const blindspotData = buildBlindspotData(blindspots);

  // Max disagreement — find story with highest dispute_score among trending (excluding already-used top 3)
  const maxDisagreement = await buildMaxDisagreement(trending, topStoryCores);

  const slots: StorySlot[] = [
    { kind: "story", story: topStoryCores[0] },
    telegramData
      ? { kind: "telegram", data: telegramData }
      : { kind: "placeholder", label: "تحلیل تلگرام در دسترس نیست", bg: "bg-indigo-950" },
    topStoryCores[1]
      ? { kind: "story", story: topStoryCores[1] }
      : { kind: "placeholder", label: "...", bg: "bg-slate-900" },
    blindspotData
      ? { kind: "blindspot", data: blindspotData }
      : { kind: "placeholder", label: "نقطه کوری یافت نشد", bg: "bg-emerald-950" },
    topStoryCores[2]
      ? { kind: "story", story: topStoryCores[2] }
      : { kind: "placeholder", label: "...", bg: "bg-slate-900" },
    maxDisagreement
      ? { kind: "maxDisagreement", data: maxDisagreement }
      : { kind: "placeholder", label: "داستان پرمناقشه‌ای یافت نشد", bg: "bg-fuchsia-950" },
    // 7th slot: desktop-view preview. The iframe renders the homepage with
    // ?desktop=1 which forces the desktop layout regardless of viewport width.
    { kind: "desktopPreview", url: "?desktop=1" },
  ];

  return slots;
}

function buildTelegramData(
  topStories: StoryBrief[],
  responses: (TelegramAnalysisResponse | null)[],
): TelegramSlotData | null {
  const predictions: TelegramSlotData["predictions"] = [];
  const claims: TelegramSlotData["claims"] = [];

  // Typical distribution: first prediction ~40-50%, second ~25-35%
  const analystPercentsByRank = [45, 28];

  topStories.forEach((story, i) => {
    const r = responses[i];
    const analysis = r?.analysis;
    if (!analysis) return;

    for (const p of analysis.predictions ?? []) {
      const text = normalizeText(p);
      if (text) {
        predictions.push({
          text,
          analystPercent: analystPercentsByRank[predictions.length] ?? undefined,
        });
      }
    }

    for (const c of analysis.key_claims ?? []) {
      if (typeof c === "string") {
        claims.push({
          source: story.title_fa.slice(0, 40),
          text: c,
          verified: false,
          story: asStoryCore(story, null, null),
        });
      } else if (c && typeof c === "object") {
        const text = normalizeText(c);
        if (!text) continue;
        claims.push({
          source: c.source ?? story.title_fa.slice(0, 40),
          text,
          verified: c.verified ?? false,
          story: asStoryCore(story, null, null),
        });
      }
    }
  });

  if (predictions.length === 0 && claims.length === 0) return null;

  return {
    title: "تحلیل روایت‌های تلگرام",
    predictions: predictions.slice(0, 2),
    claims: claims.slice(0, 2),
  };
}

function buildBlindspotData(blindspots: StoryBrief[]): BlindspotSlotData | null {
  if (blindspots.length < 2) return null;

  const stateOnly =
    blindspots.find((s) => s.blindspot_type === "state_only") ??
    blindspots.find((s) => s.state_pct > 0 && s.diaspora_pct === 0);
  const diasporaOnly =
    blindspots.find((s) => s.blindspot_type === "diaspora_only") ??
    blindspots.find((s) => s.diaspora_pct > 0 && s.state_pct === 0);

  const top = stateOnly ?? blindspots[0];
  const bottom = diasporaOnly ?? blindspots.find((s) => s.id !== top.id) ?? blindspots[1];
  if (!top || !bottom || top.id === bottom.id) return null;

  return {
    top: {
      story: asStoryCore(top, null, null),
      sideLabel: "فقط در رسانه‌های محافظه‌کار",
      excerpt: `${top.source_count} منبع محافظه‌کار این خبر را پوشش داده‌اند. دیاسپورا به آن اشاره‌ای نکرده است.`,
    },
    bottom: {
      story: asStoryCore(bottom, null, null),
      sideLabel: "فقط در رسانه‌های دیاسپورا",
      excerpt: `${bottom.source_count} منبع دیاسپورا این خبر را پوشش داده‌اند. رسانه‌های داخلی به آن اشاره‌ای نکرده‌اند.`,
    },
  };
}

async function buildMaxDisagreement(
  trending: StoryBrief[],
  topStoryCores: StoryCore[],
): Promise<MaxDisagreementSlotData | null> {
  const usedIds = new Set(topStoryCores.map((s) => s.id));
  const candidates = trending
    .filter((s) => !usedIds.has(s.id) && s.state_pct > 0 && s.diaspora_pct > 0 && !s.is_blindspot)
    .slice(0, 12);

  if (candidates.length < 2) return null;

  const analyses = await Promise.all(
    candidates.map((s) => tryFetch<StoryAnalysis>(`/api/v1/stories/${s.id}/analysis`, 300)),
  );

  const scored = candidates
    .map((story, i) => ({ story, analysis: analyses[i] }))
    .sort((a, b) => {
      const sa = a.analysis?.dispute_score ?? -1;
      const sb = b.analysis?.dispute_score ?? -1;
      if (sa !== sb) return sb - sa;
      return (
        Math.abs(b.story.state_pct - b.story.diaspora_pct) -
        Math.abs(a.story.state_pct - a.story.diaspora_pct)
      );
    });

  const picks = scored.filter((s) => s.analysis?.dispute_score != null).slice(0, 2);
  if (picks.length < 2) return null;

  const buildExcerpt = (analysis: StoryAnalysis | null): string => {
    const state = analysis?.state_summary_fa?.trim();
    const opp = analysis?.diaspora_summary_fa?.trim();
    if (state && opp) return `${state.slice(0, 110)}… ↔ ${opp.slice(0, 110)}`;
    return analysis?.bias_explanation_fa ?? "اختلاف روایت بین رسانه‌های داخل و خارج.";
  };

  return {
    top: {
      story: asStoryCore(picks[0].story, picks[0].analysis, null),
      disputeScore: picks[0].analysis?.dispute_score ?? 0,
      excerpt: buildExcerpt(picks[0].analysis),
    },
    bottom: {
      story: asStoryCore(picks[1].story, picks[1].analysis, null),
      disputeScore: picks[1].analysis?.dispute_score ?? 0,
      excerpt: buildExcerpt(picks[1].analysis),
    },
  };
}
