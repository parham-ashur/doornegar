import { getTranslations, setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { ArrowLeft, ArrowRight, AlertTriangle, Eye, TrendingUp, Newspaper } from "lucide-react";
import StoryCard from "@/components/story/StoryCard";
import { getTrendingStories, getBlindspotStories, getSources } from "@/lib/api";
import type { StoryBrief } from "@/lib/types";
import SourceSpectrum from "@/components/source/SourceSpectrum";

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  const t = await getTranslations();
  const isRtl = locale === "fa";
  const Arrow = isRtl ? ArrowLeft : ArrowRight;

  let trendingStories: StoryBrief[] = [];
  let blindspotStories: StoryBrief[] = [];
  let sources: any[] = [];

  try {
    trendingStories = await getTrendingStories(7);
  } catch {}
  try {
    blindspotStories = await getBlindspotStories(4);
  } catch {}
  try {
    const data = await getSources();
    sources = data.sources;
  } catch {}

  const heroStory = trendingStories[0];
  const secondaryStories = trendingStories.slice(1, 4);
  const moreStories = trendingStories.slice(4);

  return (
    <div>
      {/* NYTimes-style Hero Section */}
      <section className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto max-w-7xl px-4 py-6">
          {/* Masthead */}
          <div className="mb-6 border-b border-slate-300 pb-4 text-center dark:border-slate-700">
            <h1 className="text-4xl font-bold tracking-tight text-slate-900 md:text-5xl dark:text-white">
              {t("app.name")}
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {t("app.tagline")} — {t("app.description")}
            </p>
          </div>

          {heroStory ? (
            <div className="grid gap-6 lg:grid-cols-3">
              {/* Hero story — large, 2 columns */}
              <Link
                href={`/${locale}/stories/${heroStory.id}`}
                className="group lg:col-span-2"
              >
                <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-slate-800 to-slate-900 p-8 md:p-12">
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
                  <div className="relative z-10">
                    {heroStory.is_blindspot && (
                      <span className="mb-3 inline-flex items-center gap-1 rounded-full bg-amber-500/20 px-3 py-1 text-xs font-semibold text-amber-300">
                        <AlertTriangle className="h-3 w-3" />
                        {t("story.blind_spot")}
                      </span>
                    )}
                    <h2 className="text-2xl font-bold leading-tight text-white md:text-4xl group-hover:text-blue-300 transition-colors">
                      {locale === "fa" ? heroStory.title_fa : heroStory.title_en}
                    </h2>
                    <div className="mt-4 flex items-center gap-3 text-sm text-slate-300">
                      <span className="flex items-center gap-1">
                        <Newspaper className="h-4 w-4" />
                        {t("story.sources_covered", { count: heroStory.source_count })}
                      </span>
                      <span>{heroStory.article_count} {locale === "fa" ? "مقاله" : "articles"}</span>
                    </div>
                    {/* Coverage indicator */}
                    <div className="mt-4 flex gap-2">
                      {heroStory.covered_by_state && (
                        <span className="rounded-full bg-red-500/20 px-2.5 py-0.5 text-xs text-red-300">
                          {locale === "fa" ? "دولتی" : "State"}
                        </span>
                      )}
                      {heroStory.covered_by_diaspora && (
                        <span className="rounded-full bg-blue-500/20 px-2.5 py-0.5 text-xs text-blue-300">
                          {locale === "fa" ? "برون‌مرزی" : "Diaspora"}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </Link>

              {/* Secondary stories — sidebar */}
              <div className="flex flex-col gap-4">
                {secondaryStories.map((story) => (
                  <Link
                    key={story.id}
                    href={`/${locale}/stories/${story.id}`}
                    className="group border-b border-slate-200 pb-4 last:border-0 dark:border-slate-700"
                  >
                    {story.is_blindspot && (
                      <span className="mb-1 inline-flex items-center gap-1 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
                        <AlertTriangle className="h-3 w-3" />
                        {story.blindspot_type === "state_only"
                          ? t("story.state_only")
                          : t("story.diaspora_only")}
                      </span>
                    )}
                    <h3 className="text-sm font-semibold leading-snug text-slate-900 group-hover:text-diaspora dark:text-white">
                      {locale === "fa" ? story.title_fa : story.title_en}
                    </h3>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {t("story.sources_covered", { count: story.source_count })}
                    </p>
                  </Link>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-xl bg-slate-100 p-12 text-center dark:bg-slate-800">
              <Eye className="mx-auto mb-3 h-10 w-10 text-slate-400" />
              <p className="text-slate-500 dark:text-slate-400">{t("story.no_stories")}</p>
              <p className="mt-2 text-sm text-slate-400">
                {locale === "fa"
                  ? "خبرها پس از اجرای خط‌لوله نمایش داده می‌شوند"
                  : "Stories will appear after running the pipeline"}
              </p>
            </div>
          )}
        </div>
      </section>

      {/* More Stories Grid */}
      {moreStories.length > 0 && (
        <section className="mx-auto max-w-7xl px-4 py-8">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-white">
              <TrendingUp className="h-5 w-5 text-diaspora" />
              {t("home.trending")}
            </h2>
            <Link
              href={`/${locale}/stories`}
              className="flex items-center gap-1 text-sm text-diaspora hover:underline"
            >
              {t("home.view_all")} <Arrow className="h-4 w-4" />
            </Link>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {moreStories.map((story) => (
              <StoryCard key={story.id} story={story} />
            ))}
          </div>
        </section>
      )}

      {/* Media Spectrum */}
      {sources.length > 0 && (
        <section className="border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50">
          <div className="mx-auto max-w-7xl px-4 py-8">
            <h2 className="mb-6 text-center text-lg font-bold text-slate-900 dark:text-white">
              {locale === "fa" ? "طیف رسانه‌ها" : "Media Spectrum"}
            </h2>
            <SourceSpectrum sources={sources} locale={locale} />
          </div>
        </section>
      )}

      {/* Blind Spot Alert */}
      {blindspotStories.length > 0 && (
        <section className="border-t border-slate-200 dark:border-slate-800">
          <div className="mx-auto max-w-7xl px-4 py-8">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                  {t("home.blindspot_alert")}
                </h2>
              </div>
              <Link
                href={`/${locale}/blindspots`}
                className="flex items-center gap-1 text-sm text-amber-600 hover:underline"
              >
                {t("home.view_all")} <Arrow className="h-4 w-4" />
              </Link>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {blindspotStories.map((story) => (
                <StoryCard key={story.id} story={story} />
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
