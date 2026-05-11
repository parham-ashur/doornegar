const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// Server-side only — Next.js does NOT expose non-NEXT_PUBLIC_* envs to
// client bundles, so this stays out of the browser. Paired with the
// FastAPI origin_auth gate (Phase G follow-up 2026-05-11) that blocks
// direct Railway hits without either this token or a doornegar.org
// Origin/Referer header. Until BACKEND_API_TOKEN is set on both Vercel
// and Railway, the gate is a no-op so this is forward-compatible.
const BACKEND_API_TOKEN = process.env.BACKEND_API_TOKEN;

async function fetchAPI<T>(
  path: string,
  options?: RequestInit & { revalidate?: number },
): Promise<T> {
  const { revalidate = 120, ...fetchOpts } = options || {};
  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...((fetchOpts?.headers as Record<string, string>) || {}),
  };
  if (BACKEND_API_TOKEN) {
    baseHeaders["X-API-Token"] = BACKEND_API_TOKEN;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOpts,
    headers: baseHeaders,
    next: { revalidate },
  });

  if (!res.ok) {
    // Phase G follow-up (2026-05-11) — Option C 410 Gone responses
    // are how the backend signals "this story is archived/off-homepage".
    // We surface the status code on the thrown Error so pages can
    // call notFound() on 410 instead of crashing with a generic error.
    const err = new Error(`API error: ${res.status} ${res.statusText}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }

  return res.json();
}

// Sources — rarely change
export async function getSources() {
  return fetchAPI<{ sources: import("./types").Source[]; total: number }>(
    "/api/v1/sources",
    { revalidate: 3600 },
  );
}

export async function getSource(slug: string) {
  return fetchAPI<import("./types").Source>(`/api/v1/sources/${slug}`, {
    revalidate: 3600,
  });
}

// Stories — update on maintenance runs (~daily)
export async function getStories(page = 1, pageSize = 20) {
  return fetchAPI<{
    stories: import("./types").StoryBrief[];
    total: number;
    page: number;
    page_size: number;
  }>(`/api/v1/stories?page=${page}&page_size=${pageSize}`, {
    revalidate: 1800,
  });
}

export async function getBlindspotStories(limit = 20) {
  return fetchAPI<import("./types").StoryBrief[]>(
    `/api/v1/stories/blindspots?limit=${limit}`,
    { revalidate: 1800 },
  );
}

// Story detail. 5-minute cache to stay in sync with the homepage's
// trending endpoint (TRENDING_TTL = 300). A longer TTL here caused
// article_count mismatches between homepage cards and story pages
// right after a Niloofar merge — homepage refreshed but detail
// lagged for up to an hour.
export async function getStory(id: string) {
  return fetchAPI<import("./types").StoryDetail>(`/api/v1/stories/${id}`, {
    revalidate: 300,
  });
}

// Story analysis — same 5-min cadence so the bias/side-narrative
// panels stay in sync with the detail page's article list.
export async function getStoryAnalysis(id: string) {
  return fetchAPI<import("./types").StoryAnalysis>(
    `/api/v1/stories/${id}/analysis`,
    { revalidate: 300 },
  );
}

// Related stories slider — arc siblings first, then cosine neighbors.
// Longer revalidate (10 min) since related sets barely change.
export type RelatedStory = {
  id: string;
  slug: string;
  title_fa: string;
  title_en: string;
  article_count: number;
  source_count: number;
  first_published_at: string | null;
  arc_id: string | null;
  image_url: string | null;
};

export async function getRelatedStories(id: string, limit = 8) {
  return fetchAPI<{ stories: RelatedStory[]; count: number }>(
    `/api/v1/stories/${id}/related?limit=${limit}`,
    { revalidate: 600 },
  );
}

