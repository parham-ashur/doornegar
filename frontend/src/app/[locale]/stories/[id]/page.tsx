import { getTranslations, setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { ArrowLeft, ArrowRight, AlertTriangle, Newspaper } from "lucide-react";
import CoverageBar from "@/components/common/CoverageBar";
import FactCheckBarometer from "@/components/common/FactCheckBarometer";
import TopicSpectrumView from "@/components/story/TopicSpectrumView";
import FramingTable from "@/components/story/FramingTable";
import SocialPanel from "@/components/story/SocialPanel";
import SourceSpectrum from "@/components/source/SourceSpectrum";
import { getStory, getStorySocial, getSources } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { StateAlignment } from "@/lib/types";

export default async function StoryDetailPage({
  params: { locale, id },
}: {
  params: { locale: string; id: string };
}) {
  setRequestLocale(locale);
  const t = await getTranslations();
  const isRtl = locale === "fa";
  const BackArrow = isRtl ? ArrowRight : ArrowLeft;

  let story;
  let social = null;
  let allSources: any[] = [];

  try {
    story = await getStory(id);
  } catch {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 text-center">
        <p className="text-slate-500">{t("common.error")}</p>
        <Link href={`/${locale}/stories`} className="mt-4 inline-block text-diaspora hover:underline">
          {t("common.back")}
        </Link>
      </div>
    );
  }

  try {
    social = await getStorySocial(id);
  } catch {}

  try {
    const data = await getSources();
    allSources = data.sources;
  } catch {}

  const title = locale === "fa" ? story.title_fa : story.title_en;

  // Build coverage segments
  const alignmentCounts: Record<string, number> = {};
  story.articles.forEach((a) => {
    const alignment = a.source_state_alignment || "unknown";
    alignmentCounts[alignment] = (alignmentCounts[alignment] || 0) + 1;
  });
  const segments = Object.entries(alignmentCounts)
    .filter(([key]) => ["state", "semi_state", "independent", "diaspora"].includes(key))
    .map(([alignment, count]) => ({
      alignment: alignment as StateAlignment,
      count,
    }));

  // Average factuality score across articles
  const factScores = story.articles
    .flatMap((a) => a.bias_scores || [])
    .map((bs) => bs.factuality_score)
    .filter((s): s is number => s != null);
  const avgFactuality = factScores.length > 0
    ? factScores.reduce((a, b) => a + b, 0) / factScores.length
    : null;

  // Sources that cover this story
  const coveringSlugs = new Set(story.articles.map((a) => a.source_slug).filter(Boolean));
  const coveringSources = allSources.filter((s) => coveringSlugs.has(s.slug));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Back */}
      <Link
        href={`/${locale}/stories`}
        className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-diaspora"
      >
        <BackArrow className="h-4 w-4" />
        {t("common.back")}
      </Link>

      {/* Story header */}
      <div className="mb-8">
        {story.is_blindspot && (
          <div className="mb-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            {t("story.blind_spot")}:{" "}
            {story.blindspot_type === "state_only"
              ? t("story.state_only")
              : t("story.diaspora_only")}
          </div>
        )}

        <h1 className="text-2xl font-bold leading-tight text-slate-900 md:text-3xl dark:text-white">
          {title}
        </h1>

        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1">
            <Newspaper className="h-4 w-4" />
            {t("story.sources_covered", { count: story.source_count })} &middot;{" "}
            {story.article_count} {locale === "fa" ? "مقاله" : "articles"}
          </span>
          {story.first_published_at && (
            <span>{formatRelativeTime(story.first_published_at, locale)}</span>
          )}
        </div>

        <div className="mt-4 max-w-lg">
          <CoverageBar segments={segments} showLabels height="md" />
        </div>
      </div>

      {/* Main layout */}
      <div className="grid gap-8 lg:grid-cols-3">
        {/* Left-Center-Right Spectrum View (2/3 width) */}
        <div className="lg:col-span-2 space-y-8">
          {/* Topic Spectrum — the core comparison view */}
          <section>
            <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-white">
              {locale === "fa" ? "مقایسه پوشش رسانه‌ها" : "Media Coverage Comparison"}
            </h2>
            <TopicSpectrumView articles={story.articles} />
          </section>

          {/* Media Spectrum for this story */}
          {coveringSources.length > 0 && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-white">
                {locale === "fa" ? "جایگاه رسانه‌ها در طیف" : "Sources on the Spectrum"}
              </h2>
              <div className="card">
                <SourceSpectrum sources={coveringSources} locale={locale} />
              </div>
            </section>
          )}

          {/* Framing table */}
          {story.articles.length > 1 && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-white">
                {t("story.framing")}
              </h2>
              <div className="card">
                <FramingTable articles={story.articles} />
              </div>
            </section>
          )}
        </div>

        {/* Sidebar (1/3) */}
        <div className="space-y-6">
          {/* Fact Check Barometer */}
          <div className="card">
            <FactCheckBarometer score={avgFactuality} />
          </div>

          {/* Social reaction */}
          <SocialPanel
            sentiment={social?.sentiment || null}
            totalPosts={social?.total_posts || 0}
          />

          {/* AI Analysis reasoning */}
          {story.articles.some((a) => a.bias_scores?.[0]?.reasoning_en) && (
            <div className="card">
              <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">
                {t("story.bias_analysis")}
              </h3>
              <div className="space-y-3">
                {story.articles
                  .filter((a) => a.bias_scores?.[0]?.reasoning_en)
                  .slice(0, 3)
                  .map((article) => {
                    const bs = article.bias_scores[0];
                    const reasoning =
                      locale === "fa" ? bs.reasoning_fa : bs.reasoning_en;
                    return (
                      <div
                        key={article.id}
                        className="border-b border-slate-100 pb-3 last:border-0 dark:border-slate-800"
                      >
                        <p className="text-xs font-medium text-slate-700 dark:text-slate-300">
                          {locale === "fa"
                            ? article.source_name_fa
                            : article.source_name_en}
                        </p>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          {reasoning}
                        </p>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
