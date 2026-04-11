import { setRequestLocale } from "next-intl/server";
import HomepageLayout from "@/components/home/HomepageLayout";
import RaterOnboarding from "@/components/improvement/RaterOnboarding";
import type { StoryBrief } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: 30 } });
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

export default async function RatePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const stories = (await fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=50")) || [];

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
      </div>
    );
  }

  // Fetch summaries in parallel for the top 20 stories
  const topForSummary = stories.slice(0, 25);
  const summaryResults = await Promise.all(topForSummary.map((s) => fetchSummary(s.id)));
  const summaries: Record<string, string | null> = {};
  topForSummary.forEach((s, i) => { summaries[s.id] = summaryResults[i]; });

  return (
    <>
      {/* Onboarding modal (shown once) + history panel (shown if any submissions exist) */}
      <RaterOnboarding />

      {/* Feedback mode banner */}
      <div dir="rtl" className="bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-900/50 px-4 py-3">
        <div className="mx-auto max-w-7xl flex items-center justify-between gap-4">
          <p className="text-[12px] leading-6 text-slate-700 dark:text-slate-300">
            <span className="font-bold">حالت بازخورد</span> —
            روی دکمه‌های کوچک کنار هر عنصر کلیک کنید تا پیشنهاد دهید. کلیک روی هر خبر شما را به صفحه آن می‌برد (در همان حالت بازخورد).
          </p>
        </div>
      </div>

      <HomepageLayout
        stories={stories}
        summaries={summaries}
        locale={locale}
        feedbackMode={true}
      />
    </>
  );
}
