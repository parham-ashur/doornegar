"use client";

import { useState } from "react";
import Link from "next/link";
import { Image as ImageIcon, Type, FileText, LayoutGrid, MessageSquare } from "lucide-react";
import SafeImage from "@/components/common/SafeImage";
import AnalystTicker from "@/components/common/AnalystTicker";
import ImprovementModal from "@/components/improvement/ImprovementModal";
import type { StoryBrief } from "@/lib/types";

// ─── Feedback types ───────────────────────────────────────────
type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "source_dimension" | "layout" | "homepage" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request" | "other";

interface FeedbackContext {
  targetType: TargetType;
  targetId?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
  imageUrl?: string | null;
}

// ─── Feedback button (visible on mobile, hover on desktop) ────
function FeedbackBtn({
  onClick,
  label,
  icon: Icon,
  position = "tr",
}: {
  onClick: (e: React.MouseEvent) => void;
  label: string;
  icon: typeof Type;
  position?: "tr" | "tl" | "br" | "bl";
}) {
  const posClass = {
    tr: "top-1 right-1",
    tl: "top-1 left-1",
    br: "bottom-1 right-1",
    bl: "bottom-1 left-1",
  }[position];
  return (
    <button
      type="button"
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onClick(e); }}
      title={label}
      aria-label={label}
      className={`absolute ${posClass} z-20 p-1.5 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 shadow-md md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100 opacity-100 transition-opacity hover:scale-110`}
    >
      <Icon className="h-3 w-3" />
    </button>
  );
}

function Meta({ story }: { story: StoryBrief }) {
  return (
    <p className="mt-1.5 text-[12px] text-slate-400 dark:text-slate-500" dir="rtl">
      <span>{story.source_count} رسانه</span>
      <span>{" · "}</span>
      <span>{story.article_count} مقاله</span>
      {story.state_pct > 0 && <span className="text-red-500 mr-2">{" · "}حکومتی {story.state_pct}٪</span>}
      {story.independent_pct > 0 && <span className="text-emerald-600 mr-2">{" · "}مستقل {story.independent_pct}٪</span>}
      {story.diaspora_pct > 0 && <span className="text-blue-600 mr-2">{" · "}برون‌مرزی {story.diaspora_pct}٪</span>}
    </p>
  );
}

// Wrap a Link. In feedback mode, navigation adds ?feedback=1 so the story
// detail page stays in feedback mode.
function storyHref(locale: string, id: string, feedbackMode: boolean) {
  return feedbackMode
    ? `/${locale}/stories/${id}?feedback=1`
    : `/${locale}/stories/${id}`;
}

// ─── Main Component ───────────────────────────────────────────
interface Props {
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
  feedbackMode?: boolean;
}

export default function HomepageLayout({ stories, summaries, locale, feedbackMode = false }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });

  const openFeedback = (ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  };

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
      </div>
    );
  }

  const sorted = stories;
  const hero = sorted[0];
  const leftTextStories = sorted.slice(1, 4);
  const row2Stories = sorted.slice(4, 6);
  const remaining1 = sorted.slice(6);
  const shortTitle = remaining1.filter(s => (s.title_fa?.length || 100) <= 45);
  const midRow = (shortTitle.length >= 3 ? shortTitle : remaining1).slice(0, 3);
  const midRowIds = new Set(midRow.map(s => s.id));
  const afterMid = remaining1.filter(s => !midRowIds.has(s.id));
  const bottomLeft = afterMid.slice(0, 2);
  const bottomRight = afterMid.slice(2, 6);
  const bottomTextRow = afterMid.slice(6, 7);

  return (
    <>
      <div dir="rtl" className="mx-auto max-w-7xl px-0 md:px-6 lg:px-8">

        {/* ════════════════════════════════════════════ */}
        {/* MOBILE LAYOUT (phones only, below md)        */}
        {/* ════════════════════════════════════════════ */}
        <MobileHome
          hero={hero}
          stories={sorted}
          summaries={summaries}
          locale={locale}
          feedbackMode={feedbackMode}
          openFeedback={openFeedback}
        />

        {/* ════════════════════════════════════════════ */}
        {/* DESKTOP LAYOUT (tablet and up)                */}
        {/* ════════════════════════════════════════════ */}
        <div className="hidden md:block">

        {/* ROW 1: Hero */}
        <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
          {hero && (
            <div className="lg:col-span-4 flex flex-col justify-center relative group">
              <Link href={storyHref(locale, hero.id, feedbackMode)} className="group block">
                <h1 className="text-[26px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 pr-8">
                  {hero.title_fa}
                </h1>
                <Meta story={hero} />
                {summaries[hero.id] && (
                  <div className="mt-4 relative">
                    <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{summaries[hero.id]}</p>
                    <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                  </div>
                )}
              </Link>
              {feedbackMode && (
                <>
                  <FeedbackBtn icon={Type} label="عنوان" position="tr"
                    onClick={() => openFeedback({ targetType: "story_title", targetId: hero.id, currentValue: hero.title_fa, defaultIssueType: "wrong_title", contextLabel: hero.title_fa })} />
                  {summaries[hero.id] && (
                    <FeedbackBtn icon={FileText} label="خلاصه" position="bl"
                      onClick={() => openFeedback({ targetType: "story_summary", targetId: hero.id, currentValue: summaries[hero.id] || "", defaultIssueType: "bad_summary", contextLabel: hero.title_fa })} />
                  )}
                </>
              )}
              <AnalystTicker />
            </div>
          )}
          {hero && (
            <div className="lg:col-span-5 relative group">
              <Link href={storyHref(locale, hero.id, feedbackMode)} className="block">
                <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
                </div>
              </Link>
              {feedbackMode && (
                <FeedbackBtn icon={ImageIcon} label="تصویر" position="tr"
                  onClick={() => openFeedback({ targetType: "story_image", targetId: hero.id, defaultIssueType: "bad_image", contextLabel: hero.title_fa, imageUrl: hero.image_url })} />
              )}
            </div>
          )}
          <div className="lg:col-span-3 lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6 flex flex-col justify-center">
            {leftTextStories.length > 0 && (() => {
              const s = leftTextStories[leftTextStories.length - 1];
              return (
                <div className="relative group">
                  <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                    <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800 relative">
                      <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                    </div>
                    <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2 pl-6">
                      {s.title_fa}
                    </h3>
                    <p className="mt-1 text-[11px] text-slate-400">
                      {s.source_count} رسانه · {s.article_count} مقاله
                    </p>
                    {summaries[s.id] && (
                      <p className="mt-1.5 text-[12px] leading-[20px] text-slate-400 dark:text-slate-500 line-clamp-3">{summaries[s.id]}</p>
                    )}
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={ImageIcon} label="تصویر" position="tr"
                        onClick={() => openFeedback({ targetType: "story_image", targetId: s.id, defaultIssueType: "bad_image", contextLabel: s.title_fa, imageUrl: s.image_url })} />
                      <FeedbackBtn icon={Type} label="عنوان" position="bl"
                        onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                    </>
                  )}
                </div>
              );
            })()}
          </div>
        </div>

        {/* ROW 2: hero-thumb layout */}
        {row2Stories.length >= 2 && (
          <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
            <div className="lg:col-span-3 lg:border-l border-slate-200 dark:border-slate-800 lg:pl-6 flex flex-col justify-center relative group">
              <Link href={storyHref(locale, row2Stories[1].id, feedbackMode)} className="group block">
                <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800 relative">
                  <SafeImage src={row2Stories[1].image_url} className="h-full w-full object-cover" />
                </div>
                <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {row2Stories[1].title_fa}
                </h3>
                <Meta story={row2Stories[1]} />
                <p className="mt-1.5 text-[12px] leading-[20px] text-slate-400 dark:text-slate-500 line-clamp-3">{summaries[row2Stories[1].id] || row2Stories[1].title_fa}</p>
              </Link>
              {feedbackMode && (
                <>
                  <FeedbackBtn icon={ImageIcon} label="تصویر" position="tr"
                    onClick={() => openFeedback({ targetType: "story_image", targetId: row2Stories[1].id, defaultIssueType: "bad_image", contextLabel: row2Stories[1].title_fa, imageUrl: row2Stories[1].image_url })} />
                </>
              )}
            </div>
            <div className="lg:col-span-4 flex flex-col justify-center relative group">
              <Link href={storyHref(locale, row2Stories[0].id, feedbackMode)} className="group block">
                <h2 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 pr-8">
                  {row2Stories[0].title_fa}
                </h2>
                <Meta story={row2Stories[0]} />
                {summaries[row2Stories[0].id] && (
                  <div className="mt-4">
                    <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{summaries[row2Stories[0].id]}</p>
                    <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                  </div>
                )}
              </Link>
              {feedbackMode && (
                <>
                  <FeedbackBtn icon={Type} label="عنوان" position="tr"
                    onClick={() => openFeedback({ targetType: "story_title", targetId: row2Stories[0].id, currentValue: row2Stories[0].title_fa, defaultIssueType: "wrong_title", contextLabel: row2Stories[0].title_fa })} />
                  {summaries[row2Stories[0].id] && (
                    <FeedbackBtn icon={FileText} label="خلاصه" position="bl"
                      onClick={() => openFeedback({ targetType: "story_summary", targetId: row2Stories[0].id, currentValue: summaries[row2Stories[0].id] || "", defaultIssueType: "bad_summary", contextLabel: row2Stories[0].title_fa })} />
                  )}
                </>
              )}
            </div>
            <div className="lg:col-span-5 relative group">
              <Link href={storyHref(locale, row2Stories[0].id, feedbackMode)} className="block">
                <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage src={row2Stories[0].image_url} className="h-full w-full object-cover" />
                </div>
              </Link>
              {feedbackMode && (
                <FeedbackBtn icon={ImageIcon} label="تصویر" position="tr"
                  onClick={() => openFeedback({ targetType: "story_image", targetId: row2Stories[0].id, defaultIssueType: "bad_image", contextLabel: row2Stories[0].title_fa, imageUrl: row2Stories[0].image_url })} />
              )}
            </div>
          </div>
        )}

        {/* ROW 3: Text-only */}
        {midRow.length > 0 && (
          <div className={`grid grid-cols-1 ${midRow.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3"} border-b border-slate-200 dark:border-slate-800`}>
            {midRow.map((s, i) => (
              <div key={s.id} className={`relative group block py-7 ${i > 0 ? "sm:pr-6 sm:border-r border-slate-200 dark:border-slate-800" : ""} ${i < midRow.length - 1 ? "sm:pl-6" : ""}`}>
                <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                  <h3 className="text-[17px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-1 pr-8">
                    {s.title_fa}
                  </h3>
                  <Meta story={s} />
                  <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-3">{summaries[s.id] || s.title_fa}</p>
                </Link>
                {feedbackMode && (
                  <FeedbackBtn icon={Type} label="عنوان" position="tr"
                    onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                )}
              </div>
            ))}
          </div>
        )}

        {/* ROW 4: Feature + thumbnails */}
        {(bottomLeft.length > 0 || bottomRight.length > 0) && (
          <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800">
            <div className="lg:col-span-8 py-7 lg:pl-8 lg:border-l border-slate-200 dark:border-slate-800">
              {bottomLeft.map((s, i) => (
                <div key={s.id} className={`relative group ${i > 0 ? "pt-5 mt-5 border-t border-slate-200 dark:border-slate-800" : ""}`}>
                  <Link href={storyHref(locale, s.id, feedbackMode)} className="group grid grid-cols-1 sm:grid-cols-5 gap-5">
                    <div className="sm:col-span-2">
                      <h3 className="text-[20px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 pr-8">
                        {s.title_fa}
                      </h3>
                      <Meta story={s} />
                      {summaries[s.id] && (
                        <div className="mt-2">
                          <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-4">{summaries[s.id]}</p>
                          <span className="text-[12px] text-blue-600 dark:text-blue-400 mt-0.5 inline-block">ادامه ←</span>
                        </div>
                      )}
                    </div>
                    <div className="sm:col-span-3 aspect-[16/10] overflow-hidden bg-slate-100 dark:bg-slate-800">
                      <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                    </div>
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl"
                        onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                      <FeedbackBtn icon={ImageIcon} label="تصویر" position="tr"
                        onClick={() => openFeedback({ targetType: "story_image", targetId: s.id, defaultIssueType: "bad_image", contextLabel: s.title_fa, imageUrl: s.image_url })} />
                    </>
                  )}
                </div>
              ))}
            </div>
            <div className="lg:col-span-4 py-7 lg:pr-6">
              <div className="grid grid-cols-2 gap-5">
                {bottomRight.map((s) => (
                  <div key={s.id} className="relative group">
                    <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                      <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                        <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                      </div>
                      <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {s.title_fa}
                      </h3>
                      <p className="mt-1 text-[12px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
                      {(s.state_pct > 0 || s.independent_pct > 0 || s.diaspora_pct > 0) && (
                        <div className="mt-1 flex items-center gap-2">
                          {s.state_pct > 0 && <span className="text-[11px] font-medium text-red-500">حکومتی {s.state_pct}٪</span>}
                          {s.independent_pct > 0 && <span className="text-[11px] font-medium text-emerald-600">مستقل {s.independent_pct}٪</span>}
                          {s.diaspora_pct > 0 && <span className="text-[11px] font-medium text-blue-600">برون‌مرزی {s.diaspora_pct}٪</span>}
                        </div>
                      )}
                    </Link>
                    {feedbackMode && (
                      <FeedbackBtn icon={ImageIcon} label="تصویر" position="tr"
                        onClick={() => openFeedback({ targetType: "story_image", targetId: s.id, defaultIssueType: "bad_image", contextLabel: s.title_fa, imageUrl: s.image_url })} />
                    )}
                  </div>
                ))}
              </div>
              {bottomTextRow.map((s) => (
                <div key={s.id} className="relative group pt-5 mt-5 border-t border-slate-200 dark:border-slate-800">
                  <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                    <h3 className="text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 pr-8">
                      {s.title_fa}
                    </h3>
                    <p className="mt-1 text-[12px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
                    {summaries[s.id] && (
                      <p className="mt-1.5 text-[12px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">{summaries[s.id]}</p>
                    )}
                  </Link>
                  {feedbackMode && (
                    <FeedbackBtn icon={Type} label="عنوان" position="tr"
                      onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        </div>
      </div>

      <ImprovementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        targetType={context.targetType}
        targetId={context.targetId}
        currentValue={context.currentValue}
        defaultIssueType={context.defaultIssueType}
        contextLabel={context.contextLabel}
        imageUrl={context.imageUrl}
      />
    </>
  );
}

// ─── Mobile-only layout with optional feedback mode ───────────
function MobileHome({
  hero, stories, summaries, locale, feedbackMode, openFeedback,
}: {
  hero: StoryBrief | undefined;
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
  feedbackMode: boolean;
  openFeedback: (ctx: FeedbackContext) => void;
}) {
  if (!hero) return null;

  const after = stories.slice(1);
  const blocks: { type: "thumbs" | "text"; items: StoryBrief[] }[] = [];
  let cursor = 0;
  const pattern: { type: "thumbs" | "text"; size: number }[] = [
    { type: "thumbs", size: 4 },
    { type: "text", size: 3 },
    { type: "thumbs", size: 4 },
    { type: "text", size: 3 },
    { type: "thumbs", size: 4 },
  ];
  for (const step of pattern) {
    const chunk = after.slice(cursor, cursor + step.size);
    if (chunk.length === 0) break;
    blocks.push({ type: step.type, items: chunk });
    cursor += chunk.length;
  }

  return (
    <div className="md:hidden">
      {/* Hero */}
      <div className="relative">
        <Link href={storyHref(locale, hero.id, feedbackMode)} className="relative block border-b border-slate-200 dark:border-slate-800">
          <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
            <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
          </div>
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/50 to-transparent p-4 pt-16">
            <h1 className="text-[22px] font-black leading-snug text-white line-clamp-3">{hero.title_fa}</h1>
            <p className="mt-2 text-[11px] text-white/80">
              {hero.source_count} رسانه · {hero.article_count} مقاله
              {hero.state_pct > 0 && <span className="mr-2 text-red-300"> · حکومتی {hero.state_pct}٪</span>}
              {hero.independent_pct > 0 && <span className="mr-2 text-emerald-300"> · مستقل {hero.independent_pct}٪</span>}
              {hero.diaspora_pct > 0 && <span className="mr-2 text-blue-300"> · برون‌مرزی {hero.diaspora_pct}٪</span>}
            </p>
          </div>
        </Link>
        {feedbackMode && (
          <div className="absolute top-2 right-2 z-20 flex gap-1">
            <button type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "story_image", targetId: hero.id, defaultIssueType: "bad_image", contextLabel: hero.title_fa, imageUrl: hero.image_url }); }}
              className="p-2 bg-white/95 dark:bg-slate-900/95 text-slate-900 dark:text-white shadow-md" title="تصویر">
              <ImageIcon className="h-4 w-4" />
            </button>
            <button type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "story_title", targetId: hero.id, currentValue: hero.title_fa, defaultIssueType: "wrong_title", contextLabel: hero.title_fa }); }}
              className="p-2 bg-white/95 dark:bg-slate-900/95 text-slate-900 dark:text-white shadow-md" title="عنوان">
              <Type className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {/* Blocks */}
      {blocks.map((block, bi) => {
        if (block.type === "thumbs") {
          return (
            <div key={`m${bi}`} className="grid grid-cols-2 gap-4 p-4 border-b border-slate-200 dark:border-slate-800">
              {block.items.map((s) => (
                <div key={s.id} className="relative">
                  <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                    <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800 mb-2">
                      <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                    </div>
                    <h3 className="text-[13px] font-bold leading-snug line-clamp-2 text-slate-900 dark:text-white pr-6">{s.title_fa}</h3>
                    <p className="mt-1 text-[10px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
                  </Link>
                  {feedbackMode && (
                    <div className="absolute top-1 right-1 flex gap-1">
                      <button type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "story_image", targetId: s.id, defaultIssueType: "bad_image", contextLabel: s.title_fa, imageUrl: s.image_url }); }}
                        className="p-1.5 bg-white/95 dark:bg-slate-900/95 text-slate-900 dark:text-white shadow-md">
                        <ImageIcon className="h-3 w-3" />
                      </button>
                      <button type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa }); }}
                        className="p-1.5 bg-white/95 dark:bg-slate-900/95 text-slate-900 dark:text-white shadow-md">
                        <Type className="h-3 w-3" />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          );
        }
        return (
          <div key={`m${bi}`} className="divide-y divide-slate-200 dark:divide-slate-800 border-b border-slate-200 dark:border-slate-800">
            {block.items.map((s) => (
              <div key={s.id} className="relative">
                <Link href={storyHref(locale, s.id, feedbackMode)} className="block py-4 px-4">
                  <h3 className="text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white pr-10">{s.title_fa}</h3>
                  <p className="mt-1 text-[11px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
                  {summaries[s.id] && (
                    <p className="mt-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">{summaries[s.id]}</p>
                  )}
                </Link>
                {feedbackMode && (
                  <button type="button"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa }); }}
                    className="absolute top-4 right-4 p-1.5 bg-white/95 dark:bg-slate-900/95 text-slate-900 dark:text-white shadow-md" title="عنوان">
                    <Type className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
