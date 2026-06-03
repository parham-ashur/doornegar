import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import Link from "next/link";
import { Newspaper } from "lucide-react";
import CoverageBar from "@/components/common/CoverageBar";
import PoliticalSpectrum from "@/components/source/PoliticalSpectrum";
import StatsPanel from "@/components/story/StatsPanel";
import StoryAnalysisPanel from "@/components/story/StoryAnalysisPanel";
import DoornamaBriefing from "@/components/story/DoornamaBriefing";
import StoryTimeline from "@/components/story/StoryTimeline";
import ArticleFilterList from "@/components/story/ArticleFilterList";

import FeedbackProvider from "@/components/feedback/FeedbackProvider";
import EditableTitle from "@/components/feedback/EditableTitle";
import PriorityControl from "@/components/feedback/PriorityControl";
import RatingModeBanner from "@/components/feedback/RatingModeBanner";
import StoryFeedbackOverlay from "@/components/improvement/StoryFeedbackOverlay";
import PublicFeedbackButton from "@/components/common/PublicFeedbackButton";
import { getStory, getStoryAnalysis, getRelatedStories } from "@/lib/api";
import RelatedStoriesSlider from "@/components/story/RelatedStoriesSlider";
import { formatRelativeTime, toFa } from "@/lib/utils";

// Serve the page as ISR. Accessing searchParams in this server
// component would opt out of ISR, so the tg/hl deep link params are
// read client-side inside StatsPanel via useSearchParams() instead.
// First visitor after revalidate triggers one SSR; subsequent readers
// get the cached HTML edge-served.
//
// 2026-05-06: bumped 300 → 900 to keep Vercel Fluid CPU under the
// free-tier limit. New articles join at most once per 6h cron so 15
// min was well inside data-freshness.
//
// 2026-05-10 (Phase G.3.4): bumped 900 → 1800 for the Neon ≤ 2 GB/day
// June target. Story-detail is the heaviest regen path on the site
// (story + 50-1500 articles + bias + telegram + analyst takes). With
// 18 Vercel ISR regions × 2 regens/hour × ~hundreds of indexed story
// pages, halving regen frequency is a direct ~50% Neon read cut on
// the dominant traffic path. Underlying data still only shifts on the
// 6h cron, so 30-min cache age stays inside the data-freshness envelope.
//
// Tripwire: tests/test_war_audit_fixes.py::TestStoryDetailIsrAtLeast30Min
// pins this >= 1800 to block silent reverts.
export const revalidate = 1800;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}): Promise<Metadata> {
  const { locale, id } = await params;
  try {
    const story = await getStory(id);

    // Per-locale title preference: translations[locale].title (Phase 2)
    // → legacy title_en for /en → title_fa fallback. The legacy field
    // stays load-bearing until enough stories have translations
    // populated to drop it.
    const enTranslation = story.translations?.en;
    const frTranslation = story.translations?.fr;
    const enHasReal = !!enTranslation?.title && !!enTranslation?.translated_at;
    const frHasReal = !!frTranslation?.title && !!frTranslation?.translated_at;

    let title: string;
    if (locale === "en") {
      title = enTranslation?.title || story.title_en || story.title_fa || "";
    } else if (locale === "fr") {
      title = frTranslation?.title || story.title_fa || story.title_en || "";
    } else {
      title = story.title_fa || story.title_en || "";
    }

    // Description: prefer the translated summary for the active locale
    // → fall back to summary_fa → deterministic stats line (empty
    // descriptions get penalized in search).
    let description: string;
    if (locale === "en" && enTranslation?.summary) {
      description = enTranslation.summary;
    } else if (locale === "fr" && frTranslation?.summary) {
      description = frTranslation.summary;
    } else {
      description =
        story.summary_fa ||
        story.summary_en ||
        `مقایسهٔ پوشش این خبر در ${story.source_count} رسانه (${story.article_count} مقاله) — ایران درون‌مرزی vs برون‌مرزی.`;
    }

    // Conditional hreflang policy (project_en_fr_rollout):
    // - If the current locale has a real translation, canonical = self,
    //   and the languages map advertises every locale that has one
    //   (plus x-default = /fa).
    // - If the current locale has no translation, canonical points at
    //   /fa (Google attributes the page to Persian), and the languages
    //   map omits /en + /fr to avoid advertising untranslated URLs.
    const currentLocaleHasReal =
      locale === "fa" || (locale === "en" && enHasReal) || (locale === "fr" && frHasReal);

    const canonical = currentLocaleHasReal
      ? `https://doornegar.org/${locale}/stories/${id}`
      : `https://doornegar.org/fa/stories/${id}`;

    const languages: Record<string, string> = {
      fa: `https://doornegar.org/fa/stories/${id}`,
      "x-default": `https://doornegar.org/fa/stories/${id}`,
    };
    if (enHasReal) languages.en = `https://doornegar.org/en/stories/${id}`;
    if (frHasReal) languages.fr = `https://doornegar.org/fr/stories/${id}`;

    const ogImage = story.image_url || undefined;
    const ogLocaleMap: Record<string, string> = {
      fa: "fa_IR",
      en: "en_US",
      fr: "fr_FR",
    };
    const ogLocale = ogLocaleMap[locale] || "fa_IR";
    const ogAlternateLocale = Object.keys(ogLocaleMap)
      .filter((l) => l !== locale)
      .filter((l) => l === "fa" || (l === "en" && enHasReal) || (l === "fr" && frHasReal))
      .map((l) => ogLocaleMap[l]);

    // Phase G follow-up (2026-05-11) — only stories that meet the
    // homepage-eligibility bar get indexed. Thin stories (< 4 articles)
    // and stories without a real cover image are noindex'd to stop
    // crawlers + AI scrapers walking the long tail. They remain
    // accessible via direct URL (journalist permalinks) but don't
    // appear in Google / Bing / Yandex results. Pairs with the
    // sitemap that now lists only trending + blindspot stories, the
    // WAF rule blocking AI crawlers, and the Cloudflare rate limit.
    const articleCount = story.article_count ?? 0;
    const hasRealImage = story.has_real_image !== false;
    const isHomepageEligible = articleCount >= 4 && hasRealImage;
    const robots = isHomepageEligible
      ? undefined
      : { index: false, follow: true, googleBot: { index: false, follow: true } };

    return {
      title, // root layout's template adds " — دورنگر"
      description,
      robots,
      alternates: {
        canonical,
        languages,
      },
      openGraph: {
        title,
        description,
        type: "article",
        url: canonical,
        siteName: "Doornegar - دورنگر",
        locale: ogLocale,
        alternateLocale: ogAlternateLocale,
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
  } catch (e) {
    // Phase G follow-up (2026-05-11) — Option C: when the backend
    // returns 410 Gone, the story is no longer on the homepage and
    // is archived. Call notFound() so Next.js renders a 404 page
    // (clean UX) instead of throwing a generic error. Search engines
    // see 404 here and the actual 410 on the underlying API call.
    const status = (e as { status?: number })?.status;
    if (status === 410 || status === 404) {
      notFound();
    }
    return (
      <div dir={locale === "fa" ? "rtl" : "ltr"} className="mx-auto max-w-7xl px-4 py-16 text-center">
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
    <div dir={locale === "fa" ? "rtl" : "ltr"} className="mx-auto max-w-7xl px-4 py-8">
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
            // Lead with freshness: an ongoing story updated today must not
            // read as «نشر ۶ روز پیش» off its first article (Parham 2026-06-03).
            return showUpdated ? (
              <>
                <span>به‌روزرسانی {formatRelativeTime(updSrc!, "fa")}</span>
                {pubSrc && (
                  <span className="text-sm text-slate-400 dark:text-slate-600">نشر {formatRelativeTime(pubSrc, "fa")}</span>
                )}
              </>
            ) : (
              <>{pubSrc && <span>نشر {formatRelativeTime(pubSrc, "fa")}</span>}</>
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
        <div className="lg:pe-6 lg:border-e border-slate-200 dark:border-slate-800">
          {/* Editorial context — collapsed by default. Reader clicks
              the summary to expand. Uses the native <details>/<summary>
              so it works without client JS / hydration, styled with
              Tailwind + open:rotate-180 for the chevron. */}
          {(() => {
            // Cycle-4 Phase 2-c (2026-05-08): prefer the translated
            // editorial blurb for the active locale (gpt-5-mini Niloofar
            // NYT/Le Monde voice via Phase 2-b cron). Fall back to the
            // FA blurb only if no translation exists.
            const slot = locale === "en"
              ? story.translations?.en
              : locale === "fr"
                ? story.translations?.fr
                : null;
            const tlContext = slot?.editorial_context;
            const ecText = tlContext || story.editorial_context_fa?.context || "";
            if (!ecText) return null;
            // The collapsed-summary label is also locale-aware. The chevron
            // direction matches reading direction (◀ for RTL, ▶ for LTR).
            const ecLabel = locale === "fa"
              ? "زمینه خبر"
              : locale === "fr"
                ? "Contexte"
                : "Context";
            const chevron = locale === "fa" ? "◀" : "▶";
            return (
              <details className="group mb-4 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                <summary className="flex items-center justify-between cursor-pointer list-none px-4 py-2.5 select-none">
                  <span className="text-[15px] font-bold text-slate-500 dark:text-slate-400">
                    {ecLabel}
                  </span>
                  <span
                    aria-hidden="true"
                    className="text-slate-400 text-[12px] transition-transform group-open:rotate-90"
                  >
                    {chevron}
                  </span>
                </summary>
                <p className="text-[15px] leading-6 text-slate-700 dark:text-slate-300 px-4 pb-3 pt-1">
                  {ecText}
                </p>
              </details>
            );
          })()}
          {/* دورنما — at-a-glance prose synthesis. Only renders for top-N
              trending stories where the backend doornama step has run.
              Cycle-4 Phase 2-d: prefer the locale-translated briefing
              (gpt-5-mini Niloofar voice via translate cron) over FA. */}
          {(() => {
            const slot = locale === "en"
              ? story.translations?.en
              : locale === "fr"
                ? story.translations?.fr
                : null;
            // The translation slot stores the briefing under the key
            // "doornama" (so the LLM sees a clean key in the JSON
            // schema), even though the FA source field is briefing_fa.
            const localized = (slot as { doornama?: string | null } | undefined)?.doornama;
            return <DoornamaBriefing briefing={localized || analysis?.briefing_fa} />;
          })()}
          {/* Bias comparison */}
          <StoryAnalysisPanel analysis={analysis} />

          {/* Mobile-only: Telegram + narrative development + stats, placed
              between narratives and articles per Parham's 2026-04-15 spec. */}
          <div className="lg:hidden mt-6 pt-6 border-t border-slate-200 dark:border-slate-800">
            <StatsPanel
              analysis={analysis}
              storyId={id}
              articleCount={story.article_count}
              sourceCount={story.source_count}
              coveringSources={coveringSources}
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
        <div className="hidden lg:block lg:ps-6 lg:sticky lg:top-4 space-y-6" id="story-sidebar">
          <StatsPanel
            analysis={analysis}
            storyId={id}
            articleCount={story.article_count}
            sourceCount={story.source_count}
            coveringSources={coveringSources}
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
