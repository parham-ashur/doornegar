import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { ArrowRight, Newspaper } from "lucide-react";
import SourceSpectrum from "@/components/source/SourceSpectrum";
import FramingTable from "@/components/story/FramingTable";
import StoryAnalysisPanel from "@/components/story/StoryAnalysisPanel";
import ArticleFilterList from "@/components/story/ArticleFilterList";
import TelegramPanel from "@/components/story/TelegramPanel";
import FeedbackProvider from "@/components/feedback/FeedbackProvider";
import SummaryRating from "@/components/feedback/SummaryRating";
import { getStory, getSources } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

export default async function StoryDetailPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  let story;
  let allSources: any[] = [];

  try {
    story = await getStory(id);
  } catch {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-16 text-center">
        <p className="text-slate-500">خطا در بارگذاری</p>
        <Link href={`/${locale}/stories`} className="mt-4 inline-block text-blue-600 dark:text-blue-400 hover:underline">
          بازگشت
        </Link>
      </div>
    );
  }

  try {
    const data = await getSources();
    allSources = data.sources;
  } catch {}

  const title = story.title_fa || story.title_en;

  // Coverage segments
  const alignmentCounts: Record<string, number> = {};
  story.articles.forEach((a) => {
    const alignment = a.source_state_alignment || "unknown";
    alignmentCounts[alignment] = (alignmentCounts[alignment] || 0) + 1;
  });
  const total = story.articles.length || 1;
  const statePct = Math.round(((alignmentCounts["state"] || 0) + (alignmentCounts["semi_state"] || 0)) * 100 / total);
  const diasporaPct = Math.round((alignmentCounts["diaspora"] || 0) * 100 / total);
  const independentPct = Math.round((alignmentCounts["independent"] || 0) * 100 / total);

  // Sources covering this story
  const coveringSlugs = new Set(story.articles.map((a) => a.source_slug).filter(Boolean));
  const coveringSources = allSources.filter((s) => coveringSlugs.has(s.slug));

  // Framing data
  const hasFraming = story.articles.some((a) =>
    a.bias_scores?.some((bs) => bs.framing_labels && bs.framing_labels.length > 0)
  );

  return (
    <FeedbackProvider>
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      {/* Back */}
      <Link
        href={`/${locale}/stories`}
        className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors"
      >
        <ArrowRight className="h-4 w-4" />
        بازگشت
      </Link>

      {/* Header */}
      <div className="mb-6 pb-6 border-b border-slate-200 dark:border-slate-800">
        <h1 className="text-2xl font-black leading-snug text-slate-900 dark:text-white md:text-3xl">
          {title}
        </h1>

        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-slate-500">
          <span className="flex items-center gap-1">
            <Newspaper className="h-4 w-4" />
            {story.source_count} رسانه · {story.article_count} مقاله
          </span>
          {story.first_published_at && (
            <span>{formatRelativeTime(story.first_published_at, "fa")}</span>
          )}
        </div>

        {/* Coverage bar */}
        <div className="mt-4 max-w-md space-y-1.5">
          <div className="flex h-1.5 w-full overflow-hidden bg-slate-200 dark:bg-slate-800">
            {statePct > 0 && <div className="bg-red-500" style={{ width: `${statePct}%` }} />}
            {independentPct > 0 && <div className="bg-emerald-500" style={{ width: `${independentPct}%` }} />}
            {diasporaPct > 0 && <div className="bg-blue-500" style={{ width: `${diasporaPct}%` }} />}
          </div>
          <div className="flex items-center gap-3 text-[10px]">
            {statePct > 0 && (
              <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                <span className="inline-block h-1.5 w-1.5 bg-red-500" /> حکومتی {statePct}٪
              </span>
            )}
            {independentPct > 0 && (
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <span className="inline-block h-1.5 w-1.5 bg-emerald-500" /> مستقل {independentPct}٪
              </span>
            )}
            {diasporaPct > 0 && (
              <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <span className="inline-block h-1.5 w-1.5 bg-blue-500" /> برون‌مرزی {diasporaPct}٪
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Analysis (OpenAI summary + bias) */}
      <div className="mb-8">
        <StoryAnalysisPanel storyId={id} />
        <SummaryRating storyId={id} />
      </div>

      {/* Main layout */}
      <div className="grid gap-8 lg:grid-cols-3">
        {/* Articles (2/3) */}
        <div className="lg:col-span-2">
          <h2 className="mb-4 text-base font-black text-slate-900 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3">
            مقالات مرتبط
          </h2>
          <ArticleFilterList articles={story.articles} storyId={id} />

          {/* Telegram reactions */}
          <TelegramPanel storyId={id} />
        </div>

        {/* Sidebar (1/3) */}
        <div className="space-y-6 lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6">
          {coveringSources.length > 0 && (
            <div>
              <h3 className="text-sm font-black text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-slate-800">
                جایگاه رسانه‌ها
              </h3>
              <SourceSpectrum sources={coveringSources} locale="fa" showFeedback />
            </div>
          )}

          {hasFraming && story.articles.length > 1 && (
            <div>
              <h3 className="text-sm font-black text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-slate-800">
                چارچوب‌بندی
              </h3>
              <FramingTable articles={story.articles} />
            </div>
          )}
        </div>
      </div>
    </div>
    </FeedbackProvider>
  );
}
