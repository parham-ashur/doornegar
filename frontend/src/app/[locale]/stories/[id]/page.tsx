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
import RatingModeBanner from "@/components/feedback/RatingModeBanner";
import StoryFeedbackOverlay from "@/components/improvement/StoryFeedbackOverlay";
import PublicFeedbackButton from "@/components/common/PublicFeedbackButton";
import { getStory, getStoryAnalysis, getRelatedStories } from "@/lib/api";
import RelatedStoriesSlider from "@/components/story/RelatedStoriesSlider";
import { formatRelativeTime, toFa } from "@/lib/utils";

// Serve the page as ISR with a 5-minute revalidate window — matches
// the getStory/getStoryAnalysis fetch cache. Accessing searchParams
// in this server component would opt out of ISR, so the tg/hl deep
// link params are now read client-side inside StatsPanel via
// useSearchParams() instead. First visitor after revalidate triggers
// one SSR; subsequent readers get the cached HTML edge-served.
export const revalidate = 300;

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
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  // Fetch story, analysis, and related stories in parallel. Sources for the
  // political spectrum + JSON-LD citations are now embedded in the story
  // response (covering_sources), so the separate /api/v1/sources fetch is
  // gone — one fewer Railway round trip per page regen.
  let story;
  let analysis = null;
  let relatedStories: any[] = [];

  try {
    const [storyResult, analysisResult, relatedResult] = await Promise.all([
      getStory(id),
      getStoryAnalysis(id).catch(() => null),
      getRelatedStories(id, 8).catch(() => ({ stories: [] })),
    ]);
    story = storyResult;
    analysis = analysisResult;
    relatedStories = relatedResult?.stories || [];
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

  // Sources covering this story — server now embeds these in the story
  // response. Fall back to the slug-filter shape on legacy responses while
  // the deploy rolls out so older Railway revisions still render.
  const coveringSources = story.covering_sources ?? [];

  // Aggregate per-article evidence by source slug so the spectrum
  // tooltip can show WHY a source got its neutrality number.
  const sourceEvidence: Record<string, {
    article_count: number;
    loaded_total: number;
    quote_count: number;
    llm_scores: number[];
  }> = {};
  const evidence = analysis?.article_evidence || {};
  for (const a of story.articles) {
    const ev = evidence[a.id];
    if (!a.source_slug || !ev) continue;
    const agg = sourceEvidence[a.source_slug] ||= {
      article_count: 0, loaded_total: 0, quote_count: 0, llm_scores: [],
    };
    agg.article_count += 1;
    const hits = ev.loaded_hits || { principlist: 0, reformist: 0, moderate: 0, radical: 0 };
    agg.loaded_total += (hits.principlist || 0) + (hits.reformist || 0) + (hits.moderate || 0) + (hits.radical || 0);
    agg.quote_count += ev.quote_count || 0;
    if (typeof ev.llm_neutrality === "number") agg.llm_scores.push(ev.llm_neutrality);
  }

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
    <RatingModeBanner locale={locale} />
    <StoryFeedbackOverlay storyId={id} storyTitle={title} />
    <PublicFeedbackButton storyId={id} />
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
          {(() => {
            const pubSrc = story.first_published_at || story.last_updated_at || story.updated_at;
            const updSrc = story.last_updated_at || story.updated_at;
            const showUpdated = pubSrc && updSrc
              && Math.abs(new Date(updSrc).getTime() - new Date(pubSrc).getTime()) > 3600000;
            return (
              <>
                {pubSrc && <span>نشر {formatRelativeTime(pubSrc, "fa")}</span>}
                {showUpdated && (
                  <span className="text-sm text-slate-500">به‌روز {formatRelativeTime(updSrc!, "fa")}</span>
                )}
              </>
            );
          })()}
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
                <span className="text-[15px] font-bold text-slate-500 dark:text-slate-400">
                  زمینه خبر
                </span>
                <span
                  aria-hidden="true"
                  className="text-slate-400 text-[12px] transition-transform group-open:rotate-90"
                >
                  ◀
                </span>
              </summary>
              <p className="text-[15px] leading-6 text-slate-700 dark:text-slate-300 px-4 pb-3 pt-1">
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
            />
          </div>

          {/* Timeline — desktop only, collapsible. Can grow tall on
              big umbrella stories so we hide it behind a clickable
              summary; reader expands only if interested. Same pattern
              as «زمینه خبر» above. */}
          <details className="hidden lg:block group my-6 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
            <summary className="flex items-center justify-between cursor-pointer list-none px-4 py-2.5 select-none">
              <span className="text-[15px] font-bold text-slate-700 dark:text-slate-300">
                روند پوشش خبری
              </span>
              <span
                aria-hidden="true"
                className="text-slate-400 text-[12px] transition-transform group-open:rotate-90"
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
          />

          {/* Political spectrum — temporarily hidden per Parham
              2026-04-26. Component still renders elsewhere; bringing
              it back here is a single-flag flip when neutrality
              scoring is producing data we trust. */}
          {false && coveringSources.length > 0 && (
            <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
              <h3 className="text-sm font-black text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-slate-800">
                جایگاه رسانه‌ها
              </h3>
              <PoliticalSpectrum sources={coveringSources} sourceNeutrality={analysis?.source_neutrality ?? null} sourceEvidence={sourceEvidence} />
            </div>
          )}
        </div>
      </div>

      {/* Related stories — arc siblings first, then cosine-similar
          neighbors. Horizontal-scroll slider. */}
      <RelatedStoriesSlider
        stories={relatedStories}
        currentArcId={story.arc?.id ?? null}
        locale={locale}
        storyId={id}
      />
    </div>
    </FeedbackProvider>
  );
}
