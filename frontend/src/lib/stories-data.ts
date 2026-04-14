import type { StoryAnalysis, StoryBrief } from "./types";
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

function asStoryCore(
  story: StoryBrief,
  analysis: StoryAnalysis | null,
  telegramDiscourse: string | null,
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
    telegramSummary: telegramDiscourse ?? undefined,
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

  const topStoryCores = topStories.map((s, i) =>
    asStoryCore(
      s,
      topAnalyses[i] ?? null,
      topTelegrams[i]?.analysis?.discourse_summary ?? null,
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
  ];

  return slots;
}

function buildTelegramData(
  topStories: StoryBrief[],
  responses: (TelegramAnalysisResponse | null)[],
): TelegramSlotData | null {
  const predictions: TelegramSlotData["predictions"] = [];
  const claims: TelegramSlotData["claims"] = [];

  topStories.forEach((story, i) => {
    const r = responses[i];
    const analysis = r?.analysis;
    if (!analysis) return;

    for (const p of analysis.predictions ?? []) {
      const text = normalizeText(p);
      if (text) predictions.push({ text });
    }

    for (const c of analysis.key_claims ?? []) {
      if (typeof c === "string") {
        claims.push({ source: story.title_fa.slice(0, 40), text: c, verified: false });
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
    predictions: predictions.slice(0, 3),
    claims: claims.slice(0, 3),
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
    .slice(0, 8);

  if (candidates.length === 0) return null;

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

  const pick = scored[0];
  if (!pick || !pick.analysis) return null;

  const conservativeText =
    pick.analysis.state_summary_fa ?? "روایت محافظه‌کار برای این خبر در دسترس نیست.";
  const oppositionText =
    pick.analysis.diaspora_summary_fa ?? "روایت اپوزیسیون برای این خبر در دسترس نیست.";

  return {
    story: asStoryCore(pick.story, pick.analysis, null),
    top: {
      sideLabel: "محافظه‌کار",
      percent: pick.story.state_pct || 0,
      framing: conservativeText,
    },
    bottom: {
      sideLabel: "اپوزیسیون",
      percent: pick.story.diaspora_pct || 0,
      framing: oppositionText,
    },
  };
}
