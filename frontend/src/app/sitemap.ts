import type { MetadataRoute } from "next";

// Canonical domain for all absolute URLs emitted by the sitemap. Matches
// robots.txt and layout.metadataBase so Google sees a single identity
// even when the site is reachable via the Vercel preview hostname.
const BASE = "https://doornegar.org";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Sitemap refreshes hourly — stories are ingested every hour, and news
// freshness is what Google News actually ranks on. A sitemap that lags
// half a day is functionally invisible for breaking-news terms.
export const revalidate = 3600;

type Brief = {
  id: string;
  slug?: string | null;
  updated_at?: string | null;
  last_updated_at?: string | null;
  first_published_at?: string | null;
  trending_score?: number;
  article_count?: number;
};

async function safeFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { next: { revalidate } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const locales = ["fa", "en"] as const;
  const now = new Date();
  const entries: MetadataRoute.Sitemap = [];

  // Static routes — one per locale. Homepage gets priority 1.0,
  // secondary routes taper off so the sitemap encodes our own view
  // of site structure, which crawlers use as a hint.
  const staticRoutes = [
    { path: "", priority: 1.0, changeFrequency: "hourly" as const },
    { path: "/stories", priority: 0.9, changeFrequency: "hourly" as const },
    { path: "/blindspots", priority: 0.8, changeFrequency: "daily" as const },
    { path: "/sources", priority: 0.7, changeFrequency: "weekly" as const },
  ];
  for (const locale of locales) {
    for (const route of staticRoutes) {
      entries.push({
        url: `${BASE}/${locale}${route.path}`,
        lastModified: now,
        changeFrequency: route.changeFrequency,
        priority: route.priority,
        alternates: {
          languages: Object.fromEntries(
            locales.map(l => [l, `${BASE}/${l}${route.path}`]),
          ),
        },
      });
    }
  }

  // Stories — bulk fetch, use last_updated_at for freshness. Skip
  // stories without an id or that look archived (article_count < 2).
  // We emit up to 5000 — Google's sitemap entry cap is 50k, but we
  // keep it leaner so the file stays small and fetchable.
  const storiesPayload = await safeFetch<{ stories?: Brief[] }>(
    `/api/v1/stories?page=1&page_size=5000`,
  );
  const stories = storiesPayload?.stories ?? [];
  for (const s of stories) {
    if (!s.id || (s.article_count ?? 0) < 2) continue;
    const lastMod = s.last_updated_at || s.updated_at || s.first_published_at;
    for (const locale of locales) {
      entries.push({
        url: `${BASE}/${locale}/stories/${s.id}`,
        lastModified: lastMod ? new Date(lastMod) : now,
        changeFrequency: "hourly",
        // Trending stories are ranked more highly in the sitemap so
        // crawlers prioritize them. Normalized into 0.3..0.9 band.
        priority: Math.min(
          0.9,
          Math.max(0.3, 0.3 + Math.min((s.trending_score || 0) / 20, 0.6)),
        ),
        alternates: {
          languages: Object.fromEntries(
            locales.map(l => [l, `${BASE}/${l}/stories/${s.id}`]),
          ),
        },
      });
    }
  }

  // Sources — stable URLs, one entry per slug per locale.
  const sourcesPayload = await safeFetch<{
    sources?: Array<{ slug: string; updated_at?: string | null }>;
  }>(`/api/v1/sources`);
  const sources = sourcesPayload?.sources ?? [];
  for (const src of sources) {
    if (!src.slug) continue;
    for (const locale of locales) {
      entries.push({
        url: `${BASE}/${locale}/sources/${src.slug}`,
        lastModified: src.updated_at ? new Date(src.updated_at) : now,
        changeFrequency: "weekly",
        priority: 0.5,
        alternates: {
          languages: Object.fromEntries(
            locales.map(l => [l, `${BASE}/${l}/sources/${src.slug}`]),
          ),
        },
      });
    }
  }

  return entries;
}
