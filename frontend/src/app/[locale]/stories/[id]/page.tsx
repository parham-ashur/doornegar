import { setRequestLocale } from "next-intl/server";
import type { Metadata } from "next";
import Link from "next/link";
import { Newspaper } from "lucide-react";
import PoliticalSpectrum from "@/components/source/PoliticalSpectrum";
import StatsPanel from "@/components/story/StatsPanel";
import StoryAnalysisPanel from "@/components/story/StoryAnalysisPanel";
import StoryTimeline from "@/components/story/StoryTimeline";
import ArticleFilterList from "@/components/story/ArticleFilterList";

import FeedbackProvider from "@/components/feedback/FeedbackProvider";
import SummaryRating from "@/components/feedback/SummaryRating";
import EditableTitle from "@/components/feedback/EditableTitle";
import PriorityControl from "@/components/feedback/PriorityControl";
import StoryFeedbackOverlay from "@/components/improvement/StoryFeedbackOverlay";
import { getStory, getSources, getStoryAnalysis } from "@/lib/api";
import { formatRelativeTime, toFa } from "@/lib/utils";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const story = await getStory(id);
    const title = story.title_fa || story.title_en;
    const description = story.summary_fa || `${story.source_count} رسانه · ${story.article_count} مقاله`;
    return {
      title: `${title} — دورنگر`,
      description,
    };
  } catch {
    return { title: "دورنگر" };
  }
}

export default async function StoryDetailPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  // Fetch story, analysis, and sources in parallel (no waterfall)
  let story;
  let analysis = null;
  let allSources: any[] = [];

  try {
    const [storyResult, analysisResult, sourcesResult] = await Promise.all([
      getStory(id),
      getStoryAnalysis(id).catch(() => null),
      getSources().then(d => d.sources).catch(() => []),
    ]);
    story = storyResult;
    analysis = analysisResult;
    allSources = sourcesResult;
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

  // Sources covering this story
  const coveringSlugs = new Set(story.articles.map((a) => a.source_slug).filter(Boolean));
  const coveringSources = allSources.filter((s) => coveringSlugs.has(s.slug));

  return (
    <FeedbackProvider>
    <StoryFeedbackOverlay storyId={id} storyTitle={title} />
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 pb-6 border-b border-slate-200 dark:border-slate-800">
        <h1 className="text-2xl font-black leading-snug text-slate-900 dark:text-white md:text-3xl">
          <EditableTitle storyId={id} initialTitle={title} />
        </h1>

        <PriorityControl storyId={id} initialPriority={story.trending_score > 0 ? 0 : 0} />

        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-slate-500">
          <span className="flex items-center gap-1">
            <Newspaper className="h-4 w-4" />
            {toFa(story.source_count)} رسانه · {toFa(story.article_count)} مقاله
          </span>
          {story.first_published_at && (
            <span>
              نشر {formatRelativeTime(story.first_published_at, "fa")}
            </span>
          )}
          {story.updated_at && (
            <span className="text-sm text-slate-500">
              به‌روز {formatRelativeTime(story.updated_at, "fa")}
            </span>
          )}
        </div>

        {/* Coverage bar */}
        <div className="mt-4 max-w-md space-y-1.5">
          <div className="flex h-1.5 w-full overflow-hidden bg-slate-200 dark:bg-slate-800">
            {statePct > 0 && <div className="bg-[#1e3a5f]" style={{ width: `${statePct}%` }} />}
            {diasporaPct > 0 && <div className="bg-[#ea580c]" style={{ width: `${diasporaPct}%` }} />}
          </div>
          <div className="flex items-center gap-4 text-[13px]">
            <span className="flex items-center gap-1.5 text-[#1e3a5f] dark:text-blue-300">
              <span className="inline-block h-2 w-2 bg-[#1e3a5f] dark:bg-blue-400" />
              <span className="font-bold">محافظه‌کار</span> — رسانه‌های دولتی و نزدیک به حکومت
              {statePct > 0 && <span className="font-medium"> ({toFa(statePct)}٪)</span>}
            </span>
          </div>
          <div className="flex items-center gap-4 text-[13px] mt-0.5">
            <span className="flex items-center gap-1.5 text-[#ea580c] dark:text-orange-400">
              <span className="inline-block h-2 w-2 bg-[#ea580c] dark:bg-orange-400" />
              <span className="font-bold">اپوزیسیون</span> — رسانه‌های برون‌مرزی و منتقد حکومت
              {diasporaPct > 0 && <span className="font-medium"> ({toFa(diasporaPct)}٪)</span>}
            </span>
          </div>
        </div>
      </div>

      {/* Two-column layout for everything below header */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 lg:items-start">
        {/* RIGHT column (RTL): bias tabs → articles */}
        <div className="lg:pl-6 lg:border-l border-slate-200 dark:border-slate-800">
          {/* Editorial context */}
          {story.editorial_context_fa?.context && (
            <div className="mb-4 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 px-4 py-3">
              <p className="text-[13px] font-bold text-slate-500 dark:text-slate-400 mb-1">زمینه خبر</p>
              <p className="text-[13px] leading-6 text-slate-700 dark:text-slate-300">{story.editorial_context_fa.context}</p>
            </div>
          )}
          {/* Bias comparison */}
          <StoryAnalysisPanel analysis={analysis} />
          <SummaryRating storyId={id} />

          {/* Timeline — desktop only */}
          <div className="hidden lg:block">
            <StoryTimeline articles={story.articles} />
          </div>

          {/* Articles */}
          <h2 className="mt-6 mb-4 text-base font-black text-slate-900 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3">
            مقالات مرتبط
          </h2>
          <ArticleFilterList articles={story.articles} storyId={id} />
        </div>

        {/* LEFT column (RTL): stats → analyst → spectrum */}
        <div className="lg:pr-6 lg:sticky lg:top-4 space-y-6 pt-4 lg:pt-0" id="story-sidebar">
          <StatsPanel analysis={analysis} storyId={id} articleCount={story.article_count} sourceCount={story.source_count} />

          {/* Political spectrum — desktop only */}
          {coveringSources.length > 0 && (
            <div className="hidden lg:block border-t border-slate-200 dark:border-slate-800 pt-4">
              <h3 className="text-sm font-black text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-slate-800">
                جایگاه رسانه‌ها
              </h3>
              <PoliticalSpectrum sources={coveringSources} sourceNeutrality={analysis?.source_neutrality || null} />
            </div>
          )}
        </div>
      </div>
    </div>
    </FeedbackProvider>
  );
}
