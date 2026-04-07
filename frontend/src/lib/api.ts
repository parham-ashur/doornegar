const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    next: { revalidate: 60 }, // Cache for 60 seconds
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

// Sources
export async function getSources() {
  return fetchAPI<{ sources: import("./types").Source[]; total: number }>(
    "/api/v1/sources"
  );
}

export async function getSource(slug: string) {
  return fetchAPI<import("./types").Source>(`/api/v1/sources/${slug}`);
}

// Stories
export async function getStories(page = 1, pageSize = 20) {
  return fetchAPI<{
    stories: import("./types").StoryBrief[];
    total: number;
    page: number;
    page_size: number;
  }>(`/api/v1/stories?page=${page}&page_size=${pageSize}`);
}

export async function getTrendingStories(limit = 10) {
  return fetchAPI<import("./types").StoryBrief[]>(
    `/api/v1/stories/trending?limit=${limit}`
  );
}

export async function getBlindspotStories(limit = 20) {
  return fetchAPI<import("./types").StoryBrief[]>(
    `/api/v1/stories/blindspots?limit=${limit}`
  );
}

export async function getStory(id: string) {
  return fetchAPI<import("./types").StoryDetail>(`/api/v1/stories/${id}`);
}

// Story Analysis
export async function getStoryAnalysis(storyId: string) {
  return fetchAPI<import("./types").StoryAnalysis>(
    `/api/v1/stories/${storyId}/analysis`
  );
}

// Social
export async function getStorySocial(storyId: string) {
  return fetchAPI<{
    story_id: string;
    posts: any[];
    sentiment: import("./types").SocialSentiment | null;
    total_posts: number;
  }>(`/api/v1/social/stories/${storyId}/social`);
}
