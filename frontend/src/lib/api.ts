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

// Sources — rarely change, cache 10 min
export async function getSources() {
  return fetchAPI<{ sources: import("./types").Source[]; total: number }>(
    "/api/v1/sources",
    { revalidate: 600 },
  );
}

export async function getSource(slug: string) {
  return fetchAPI<import("./types").Source>(`/api/v1/sources/${slug}`, {
    revalidate: 600,
  });
}

// Stories — update on maintenance runs (~daily), cache 2 min
export async function getStories(page = 1, pageSize = 20) {
  return fetchAPI<{
    stories: import("./types").StoryBrief[];
    total: number;
    page: number;
    page_size: number;
  }>(`/api/v1/stories?page=${page}&page_size=${pageSize}`);
}

export async function getBlindspotStories(limit = 20) {
  return fetchAPI<import("./types").StoryBrief[]>(
    `/api/v1/stories/blindspots?limit=${limit}`,
  );
}

// Story detail — cache 5 min (rarely changes between maintenance runs)
export async function getStory(id: string) {
  return fetchAPI<import("./types").StoryDetail>(`/api/v1/stories/${id}`, {
    revalidate: 300,
  });
}

// Story analysis — fetched server-side in parallel with story detail
export async function getStoryAnalysis(id: string) {
  return fetchAPI<import("./types").StoryAnalysis>(
    `/api/v1/stories/${id}/analysis`,
    { revalidate: 300 },
  );
}

