import { getTranslations, setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { AlertTriangle, Eye, Newspaper, ChevronLeft, BarChart3, Shield } from "lucide-react";
import type { StoryBrief, Source } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  const t = await getTranslations();

  const stories = await fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=12") || [];
  const blindspots = await fetchAPI<StoryBrief[]>("/api/v1/stories/blindspots?limit=6") || [];
  const sourcesData = await fetchAPI<{ sources: Source[] }>("/api/v1/sources") || { sources: [] };
  const sources = sourcesData.sources;

  const heroStory = stories[0];
  const topStories = stories.slice(1, 4);
  const moreStories = stories.slice(4);

  const stateMedia = sources.filter(s => s.state_alignment === "state" || s.state_alignment === "semi_state");
  const diasporaMedia = sources.filter(s => s.state_alignment === "diaspora" || s.state_alignment === "independent");

  return (
    <div className="bg-white dark:bg-slate-950">
      {/* Masthead */}
      <div className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto max-w-7xl px-4 py-4 text-center">
          <h1 className="text-4xl font-black tracking-tight text-slate-900 dark:text-white md:text-5xl">
            دورنگر
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            شفافیت رسانه‌ای ایران — ببینید رسانه‌ها چگونه خبر را شکل می‌دهند
          </p>
          <div className="mx-auto mt-2 h-0.5 w-32 bg-gradient-to-r from-red-500 via-amber-500 via-emerald-500 to-blue-500" />
        </div>
      </div>

      {stories.length === 0 ? (
        <div className="mx-auto max-w-2xl px-4 py-20 text-center">
          <Eye className="mx-auto mb-4 h-16 w-16 text-slate-300" />
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">
            هنوز موضوعی ایجاد نشده
          </h2>
          <p className="mt-3 text-slate-500">
            پس از اجرای خط‌لوله داده، موضوعات خبری اینجا نمایش داده می‌شوند
          </p>
          <Link
            href={`/${locale}/dashboard`}
            className="mt-6 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-700"
          >
            <BarChart3 className="h-4 w-4" />
            داشبورد
          </Link>
        </div>
      ) : (
        <>
          {/* Hero + Top Stories */}
          <div className="mx-auto max-w-7xl px-4 py-6">
            <div className="grid gap-6 lg:grid-cols-5">
              {heroStory && (
                <Link
                  href={`/${locale}/stories/${heroStory.id}`}
                  className="group lg:col-span-3"
                >
                  <div className="relative overflow-hidden rounded-2xl bg-slate-900 aspect-[16/9] flex items-end">
                    <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/50 to-slate-800/30" />
                    <div className="relative z-10 p-6 md:p-8">
                      <div className="mb-3 flex gap-2">
                        {heroStory.covered_by_state && (
                          <span className="rounded-full bg-red-500 px-2.5 py-0.5 text-[10px] font-bold text-white">حکومتی</span>
                        )}
                        {heroStory.covered_by_diaspora && (
                          <span className="rounded-full bg-blue-500 px-2.5 py-0.5 text-[10px] font-bold text-white">برون‌مرزی</span>
                        )}
                        {heroStory.is_blindspot && (
                          <span className="rounded-full bg-amber-500 px-2.5 py-0.5 text-[10px] font-bold text-white flex items-center gap-1">
                            <AlertTriangle className="h-3 w-3" />
                            نقطه کور
                          </span>
                        )}
                      </div>
                      <h2 className="text-xl font-black leading-tight text-white md:text-3xl group-hover:text-blue-300 transition-colors">
                        {heroStory.title_fa}
                      </h2>
                      <div className="mt-3 flex items-center gap-4 text-sm text-slate-300">
                        <span className="flex items-center gap-1">
                          <Newspaper className="h-4 w-4" />
                          {heroStory.source_count} رسانه
                        </span>
                        <span>{heroStory.article_count} مقاله</span>
                      </div>
                      <div className="mt-3 flex h-1.5 w-48 overflow-hidden rounded-full">
                        {heroStory.covered_by_state && <div className="flex-1 bg-red-500" />}
                        {heroStory.covered_by_diaspora && <div className="flex-1 bg-blue-500" />}
                      </div>
                    </div>
                  </div>
                </Link>
              )}

              <div className="flex flex-col gap-4 lg:col-span-2">
                {topStories.map((story) => (
                  <Link
                    key={story.id}
                    href={`/${locale}/stories/${story.id}`}
                    className="group flex gap-4 border-b border-slate-100 pb-4 last:border-0 dark:border-slate-800"
                  >
                    <div className="flex w-1.5 flex-shrink-0 flex-col gap-0.5 rounded-full overflow-hidden">
                      {story.covered_by_state && <div className="flex-1 bg-red-500" />}
                      {story.covered_by_diaspora && <div className="flex-1 bg-blue-500" />}
                      {!story.covered_by_state && !story.covered_by_diaspora && <div className="flex-1 bg-slate-300" />}
                    </div>
                    <div className="flex-1">
                      {story.is_blindspot && (
                        <span className="mb-1 inline-flex items-center gap-1 text-[10px] font-bold text-amber-600">
                          <AlertTriangle className="h-3 w-3" />
                          نقطه کور
                        </span>
                      )}
                      <h3 className="text-sm font-bold leading-snug text-slate-900 group-hover:text-blue-600 dark:text-white">
                        {story.title_fa}
                      </h3>
                      <p className="mt-1 text-xs text-slate-500">
                        {story.source_count} رسانه · {story.article_count} مقاله
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          {/* Media Spectrum */}
          <div className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50">
            <div className="mx-auto max-w-7xl px-4 py-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">طیف رسانه‌ها</h3>
                <Link href={`/${locale}/sources`} className="text-xs text-blue-600 hover:underline">مشاهده همه</Link>
              </div>
              <div className="mt-3">
                <div className="relative">
                  <div className="h-10 rounded-lg bg-gradient-to-l from-red-500 via-amber-400 via-50% via-emerald-400 to-blue-500 opacity-15" />
                  <div className="absolute inset-0 flex items-center justify-between px-2">
                    <div className="flex gap-1.5 flex-row-reverse">
                      {diasporaMedia.slice(0, 6).map(s => (
                        <Link key={s.slug} href={`/${locale}/sources/${s.slug}`}
                          className="rounded-md bg-blue-100 border border-blue-200 px-2 py-0.5 text-[9px] font-bold text-blue-700 hover:bg-blue-200 dark:bg-blue-900/40 dark:border-blue-800 dark:text-blue-300">
                          {s.name_fa.length > 10 ? s.name_fa.slice(0, 8) + "…" : s.name_fa}
                        </Link>
                      ))}
                    </div>
                    <div className="flex gap-1.5">
                      {stateMedia.slice(0, 5).map(s => (
                        <Link key={s.slug} href={`/${locale}/sources/${s.slug}`}
                          className="rounded-md bg-red-100 border border-red-200 px-2 py-0.5 text-[9px] font-bold text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:border-red-800 dark:text-red-300 flex items-center gap-0.5">
                          {s.irgc_affiliated && <Shield className="h-2.5 w-2.5" />}
                          {s.name_fa.length > 10 ? s.name_fa.slice(0, 8) + "…" : s.name_fa}
                        </Link>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="mt-1 flex justify-between text-[9px] text-slate-400">
                  <span>اپوزیسیون / برون‌مرزی</span>
                  <span>حکومتی / دولتی</span>
                </div>
              </div>
            </div>
          </div>

          {/* More Stories Grid */}
          {moreStories.length > 0 && (
            <div className="mx-auto max-w-7xl px-4 py-8">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-black text-slate-900 dark:text-white">موضوعات بیشتر</h2>
                <Link href={`/${locale}/stories`} className="flex items-center gap-1 text-sm text-blue-600 hover:underline">
                  همه موضوعات <ChevronLeft className="h-4 w-4" />
                </Link>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {moreStories.map((story) => (
                  <Link key={story.id} href={`/${locale}/stories/${story.id}`} className="card group">
                    <div className="mb-3 flex h-1.5 overflow-hidden rounded-full">
                      {story.covered_by_state && <div className="flex-1 bg-red-500" />}
                      {story.covered_by_diaspora && <div className="flex-1 bg-blue-500" />}
                    </div>
                    {story.is_blindspot && (
                      <div className="mb-2 flex items-center gap-1 text-[10px] font-bold text-amber-600">
                        <AlertTriangle className="h-3 w-3" />
                        {story.blindspot_type === "state_only" ? "فقط رسانه دولتی" : "فقط رسانه برون‌مرزی"}
                      </div>
                    )}
                    <h3 className="text-sm font-bold leading-snug text-slate-900 group-hover:text-blue-600 dark:text-white">
                      {story.title_fa}
                    </h3>
                    <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
                      <span>{story.source_count} رسانه</span>
                      <span>{story.article_count} مقاله</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Blind Spots */}
          {blindspots.length > 0 && (
            <div className="border-t border-slate-200 bg-amber-50/50 dark:border-slate-800 dark:bg-amber-950/10">
              <div className="mx-auto max-w-7xl px-4 py-8">
                <div className="mb-4 flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h2 className="text-lg font-black text-slate-900 dark:text-white">نقاط کور</h2>
                  <span className="rounded-full bg-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-800">{blindspots.length}</span>
                </div>
                <p className="mb-4 text-xs text-slate-500">
                  خبرهایی که فقط یک طرف پوشش داده — چه چیزی از دید شما پنهان مانده؟
                </p>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {blindspots.map((story) => (
                    <Link key={story.id} href={`/${locale}/stories/${story.id}`}
                      className="group rounded-xl border border-amber-200 bg-white p-4 transition-shadow hover:shadow-md dark:border-amber-800/30 dark:bg-slate-900">
                      <span className="text-[10px] font-bold text-amber-600">
                        {story.blindspot_type === "state_only" ? "فقط رسانه دولتی" : "فقط رسانه برون‌مرزی"}
                      </span>
                      <h3 className="mt-1 text-sm font-bold text-slate-900 group-hover:text-blue-600 dark:text-white">
                        {story.title_fa}
                      </h3>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
