import { setRequestLocale } from "next-intl/server";
import type { Metadata } from "next";
import Link from "next/link";
import { Newspaper } from "lucide-react";
import CoverageBar from "@/components/common/CoverageBar";
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
import PublicFeedbackButton from "@/components/common/PublicFeedbackButton";
import NarrativeDriftPanel from "@/components/story/NarrativeDriftPanel";
import { getStory, getSources, getStoryAnalysis } from "@/lib/api";
import { formatRelativeTime, toFa } from "@/lib/utils";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}): Promise<Metadata> {
  const { locale, id } = await params;
  try {
    const story = await getStory(id);
    const titleFa = story.title_fa || story.title_en || "";
    const titleEn = story.title_en || story.title_fa || "";
    const title = locale === "en" ? titleEn : titleFa;
    // Prefer summary_fa (1–2 sentence editorial blurb) for the meta
    // description; fall back to a deterministic stats line so there's
    // always SOMETHING — empty descriptions get penalized in search.
    const description =
      story.summary_fa ||
      story.summary_en ||
      `مقایسهٔ پوشش این خبر در ${story.source_count} رسانه (${story.article_count} مقاله) — ایران درون‌مرزی vs برون‌مرزی.`;

    const canonical = `https://doornegar.org/${locale}/stories/${id}`;
    const ogImage = story.image_url || undefined;

    return {
      title, // root layout's template adds " — دورنگر"
      description,
      alternates: {
        canonical,
        languages: {
          fa: `https://doornegar.org/fa/stories/${id}`,
          en: `https://doornegar.org/en/stories/${id}`,
          "x-default": `https://doornegar.org/fa/stories/${id}`,
        },
      },
      openGraph: {
        title,
        description,
        type: "article",
        url: canonical,
        siteName: "Doornegar - دورنگر",
        locale: locale === "en" ? "en_US" : "fa_IR",
        alternateLocale: locale === "en" ? ["fa_IR"] : ["en_US"],
        publishedTime: story.first_published_at || undefined,
        modifiedTime: story.last_updated_at || story.updated_at || undefined,
        images: ogImage ? [{ url: ogImage, alt: title }] : undefined,
      },
      twitter: {
        card: "summary_large_image",
        title,
        description,
        images: ogImage ? [ogImage] : undefined,
      },
    };
  } catch {
    return { title: "دورنگر" };
  }
}

export default async function StoryDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { locale, id } = await params;
  const sp = await searchParams;
  const tgParam = typeof sp.tg === "string" ? sp.tg : null;
  const hlParam = typeof sp.hl === "string" ? sp.hl : null;
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

  // Sources covering this story
  const coveringSlugs = new Set(story.articles.map((a) => a.source_slug).filter(Boolean));
  const coveringSources = allSources.filter((s) => coveringSlugs.has(s.slug));

  // JSON-LD NewsArticle schema — feeds Google News, knowledge panels,
  // rich-result carousels. Must match the visible content: same
  // headline, same publish date, same image. Embedded via <script
  // type="application/ld+json"> inline because Next doesn't have a
  // first-class Metadata API for structured data yet.
  const canonicalUrl = `https://doornegar.org/${locale}/stories/${id}`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: title,
    description:
      story.summary_fa ||
      story.summary_en ||
      `${story.source_count} رسانه · ${story.article_count} مقاله`,
    datePublished: story.first_published_at || undefined,
    dateModified: story.last_updated_at || story.updated_at || story.first_published_at || undefined,
    inLanguage: locale === "en" ? "en" : "fa",
    image: story.image_url ? [story.image_url] : undefined,
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": canonicalUrl,
    },
    publisher: {
      "@type": "Organization",
      name: "Doornegar - دورنگر",
      url: "https://doornegar.org",
      logo: {
        "@type": "ImageObject",
        url: "https://doornegar.org/favicon.ico",
      },
    },
    // Outlets covering the story surface as citations — signals to
    // crawlers that this is an aggregation page, not original reporting.
    citation: coveringSources.map(s => ({
      "@type": "CreativeWork",
      name: s.name_fa || s.name_en || s.slug,
      url: s.website_url,
    })),
  };

  return (
    <FeedbackProvider>
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
    />
    <StoryFeedbackOverlay storyId={id} storyTitle={title} />
    <PublicFeedbackButton storyId={id} />
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      {/* Arc chapter strip — visible only when this story is part of a
          curated arc. Shows all chapters in chronological order with
          the current chapter highlighted, each linking to its story. */}
      {story.arc && story.arc.chapters.length > 1 && (
        <div className="mb-4 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
              قوس
            </span>
            <h2 className="text-[13px] font-black text-slate-700 dark:text-slate-300">
              {story.arc.title_fa}
            </h2>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {story.arc.chapters.map((ch, i) => {
              const isCurrent = ch.story_id === id;
              const isLast = i === story.arc!.chapters.length - 1;
              return (
                <span key={ch.story_id} className="flex items-center gap-1.5">
                  {isCurrent ? (
                    <span className="border-2 border-slate-900 dark:border-white bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-2 py-0.5 text-[12px] font-bold">
                      {ch.title_fa || "(بدون عنوان)"}
                    </span>
                  ) : (
                    <Link
                      href={`/${locale}/stories/${ch.story_id}`}
                      className="border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-900 dark:hover:border-white hover:text-slate-900 dark:hover:text-white px-2 py-0.5 text-[12px] transition-colors"
                    >
                      {ch.title_fa || "(بدون عنوان)"}
                    </Link>
                  )}
                  {!isLast && <span className="text-slate-300 dark:text-slate-600 text-[12px]">←</span>}
                </span>
              );
            })}
          </div>
          <NarrativeDriftPanel arcId={story.arc.id} currentStoryId={id} locale={locale} />
        </div>
      )}

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

        {/* Coverage bar — 4 narrative subgroups grouped into 2 sides */}
        <div className="mt-4 max-w-md">
          <CoverageBar story={story} height="md" showSideTotals showSubgroupLabels />
        </div>
      </div>

      {/* Two-column layout for everything below header */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 lg:items-start">
        {/* RIGHT column (RTL): bias tabs → articles */}
        <div className="lg:pl-6 lg:border-l border-slate-200 dark:border-slate-800">
          {/* Editorial context — collapsed by default. Reader clicks
              the summary to expand. Uses the native <details>/<summary>
              so it works without client JS / hydration, styled with
              Tailwind + open:rotate-180 for the chevron. */}
          {story.editorial_context_fa?.context && (
            <details className="group mb-4 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
              <summary className="flex items-center justify-between cursor-pointer list-none px-4 py-2.5 select-none">
                <span className="text-[13px] font-bold text-slate-500 dark:text-slate-400">
                  زمینه خبر
                </span>
                <span
                  aria-hidden="true"
                  className="text-slate-400 text-[11px] transition-transform group-open:rotate-90"
                >
                  ◀
                </span>
              </summary>
              <p className="text-[13px] leading-6 text-slate-700 dark:text-slate-300 px-4 pb-3 pt-1">
                {story.editorial_context_fa.context}
              </p>
            </details>
          )}
          {/* Bias comparison */}
          <StoryAnalysisPanel analysis={analysis} />
          <SummaryRating storyId={id} />

          {/* Mobile-only: Telegram + narrative development + stats, placed
              between narratives and articles per Parham's 2026-04-15 spec. */}
          <div className="lg:hidden mt-6 pt-6 border-t border-slate-200 dark:border-slate-800">
            <StatsPanel
              analysis={analysis}
              storyId={id}
              articleCount={story.article_count}
              sourceCount={story.source_count}
              containerId="telegram-mobile"
              initialTab={tgParam}
              highlightText={hlParam}
            />
          </div>

          {/* Timeline — desktop only, collapsible. Can grow tall on
              big umbrella stories so we hide it behind a clickable
              summary; reader expands only if interested. Same pattern
              as «زمینه خبر» above. */}
          <details className="hidden lg:block group my-6 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
            <summary className="flex items-center justify-between cursor-pointer list-none px-4 py-2.5 select-none">
              <span className="text-[13px] font-bold text-slate-700 dark:text-slate-300">
                روند پوشش خبری
              </span>
              <span
                aria-hidden="true"
                className="text-slate-400 text-[11px] transition-transform group-open:rotate-90"
              >
                ◀
              </span>
            </summary>
            <div className="px-4 pb-4 pt-2">
              <StoryTimeline articles={story.articles} />
            </div>
          </details>

          {/* Articles */}
          <h2 className="mt-6 mb-4 text-base font-black text-slate-900 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3">
            مقالات مرتبط
          </h2>
          <ArticleFilterList articles={story.articles} storyId={id} />
        </div>

        {/* LEFT column (desktop sidebar only): stats → spectrum. Hidden on
            mobile because the same StatsPanel is rendered inline above. */}
        <div className="hidden lg:block lg:pr-6 lg:sticky lg:top-4 space-y-6" id="story-sidebar">
          <StatsPanel
            analysis={analysis}
            storyId={id}
            articleCount={story.article_count}
            sourceCount={story.source_count}
            initialTab={tgParam}
            highlightText={hlParam}
          />

          {/* Political spectrum — desktop only */}
          {coveringSources.length > 0 && (
            <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
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
