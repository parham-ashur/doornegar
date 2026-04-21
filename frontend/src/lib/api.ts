const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(
  path: string,
  options?: RequestInit & { revalidate?: number },
): Promise<T> {
  const { revalidate = 120, ...fetchOpts } = options || {};
  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOpts,
    headers: {
      "Content-Type": "application/json",
      ...fetchOpts?.headers,
    },
    next: { revalidate },
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
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

