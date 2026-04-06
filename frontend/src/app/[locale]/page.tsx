import { useTranslations } from "next-intl";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { ArrowLeft, ArrowRight, AlertTriangle, Eye, TrendingUp } from "lucide-react";
import StoryCard from "@/components/story/StoryCard";
import { getTrendingStories, getBlindspotStories } from "@/lib/api";

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  const t = await getTranslations();
  const isRtl = locale === "fa";
  const Arrow = isRtl ? ArrowLeft : ArrowRight;

  let trendingStories = [];
  let blindspotStories = [];

  try {
    trendingStories = await getTrendingStories(6);
  } catch {
    // API may not be running yet
  }

  try {
    blindspotStories = await getBlindspotStories(4);
  } catch {
    // API may not be running yet
  }

  return (
    <div>
      {/* Hero */}
      <section className="border-b border-slate-200 bg-gradient-to-b from-slate-100 to-white dark:border-slate-800 dark:from-slate-900 dark:to-slate-950">
        <div className="mx-auto max-w-7xl px-4 py-16 text-center md:py-24">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-diaspora/10">
            <Eye className="h-8 w-8 text-diaspora" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 md:text-5xl dark:text-white">
            {t("home.hero_title")}
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-slate-600 dark:text-slate-400">
            {t("home.hero_subtitle")}
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <Link
              href={`/${locale}/stories`}
              className="rounded-xl bg-diaspora px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-diaspora-dark"
            >
              {t("nav.stories")}
            </Link>
            <Link
              href={`/${locale}/sources`}
              className="rounded-xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {t("nav.sources")}
            </Link>
          </div>
        </div>
      </section>

      {/* Trending Stories */}
      <section className="mx-auto max-w-7xl px-4 py-12">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-diaspora" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              {t("home.trending")}
            </h2>
          </div>
          <Link
            href={`/${locale}/stories`}
            className="flex items-center gap-1 text-sm font-medium text-diaspora hover:underline"
          >
            {t("home.view_all")}
            <Arrow className="h-4 w-4" />
          </Link>
        </div>

        {trendingStories.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {trendingStories.map((story) => (
              <StoryCard key={story.id} story={story} />
            ))}
          </div>
        ) : (
          <div className="card text-center text-slate-500 dark:text-slate-400">
            {t("story.no_stories")}
          </div>
        )}
      </section>

      {/* Blind Spot Alert */}
      {blindspotStories.length > 0 && (
        <section className="border-t border-slate-200 bg-amber-50/50 dark:border-slate-800 dark:bg-amber-950/10">
          <div className="mx-auto max-w-7xl px-4 py-12">
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                <div>
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                    {t("home.blindspot_alert")}
                  </h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    {t("home.blindspot_desc")}
                  </p>
                </div>
              </div>
              <Link
                href={`/${locale}/blindspots`}
                className="flex items-center gap-1 text-sm font-medium text-amber-600 hover:underline"
              >
                {t("home.view_all")}
                <Arrow className="h-4 w-4" />
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
