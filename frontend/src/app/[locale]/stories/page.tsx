import { setRequestLocale } from "next-intl/server";
import { Newspaper } from "lucide-react";
import StoryCard from "@/components/story/StoryCard";
import { getStories } from "@/lib/api";
import type { StoryBrief } from "@/lib/types";

export default async function StoriesPage({
  params: { locale },
  searchParams,
}: {
  params: { locale: string };
  searchParams: { page?: string };
}) {
  setRequestLocale(locale);
  const page = parseInt(searchParams.page || "1", 10);

  let stories: StoryBrief[] = [];
  let total = 0;

  try {
    const data = await getStories(page, 20);
    stories = data.stories;
    total = data.total;
  } catch {
    // API may not be running
  }

  const totalPages = Math.ceil(total / 20);

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <Newspaper className="h-6 w-6 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">
            خبرها
          </h1>
        </div>
        <p className="mt-1 text-sm text-slate-400">
          {total > 0 ? `${total} خبر` : ""}
        </p>
      </div>

      {/* Stories grid */}
      {stories.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {stories.map((story) => (
            <StoryCard key={story.id} story={story} />
          ))}
        </div>
      ) : (
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 text-center text-slate-400">
          هنوز خبری ثبت نشده است
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex justify-center gap-2">
          {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => i + 1).map(
            (p) => (
              <a
                key={p}
                href={`/${locale}/stories?page=${p}`}
                className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${
                  p === page
                    ? "bg-blue-500 text-white"
                    : "bg-slate-900/80 text-slate-400 ring-1 ring-white/[0.06] hover:bg-slate-800"
                }`}
              >
                {p}
              </a>
            )
          )}
        </div>
      )}
    </div>
  );
}
