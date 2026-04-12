"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { Image as ImageIcon, Type, FileText, ArrowUp, ArrowDown, GitMerge } from "lucide-react";
import SafeImage from "@/components/common/SafeImage";
import AnalystTicker from "@/components/common/AnalystTicker";
import ImprovementModal from "@/components/improvement/ImprovementModal";
import type { StoryBrief } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";

// ─── Feedback types ───────────────────────────────────────────
type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "source_dimension" | "layout" | "homepage"
  | "merge_stories" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request"
  | "priority_higher" | "priority_lower" | "merge_stories" | "other";

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
  const published = story.first_published_at
    ? formatRelativeTime(story.first_published_at, "fa")
    : null;
  const updated = story.updated_at
    ? formatRelativeTime(story.updated_at, "fa")
    : null;
  const showUpdated = updated && story.updated_at && story.first_published_at
    && Math.abs(new Date(story.updated_at).getTime() - new Date(story.first_published_at).getTime()) > 3600000;
  const hasSides = story.state_pct > 0 || story.diaspora_pct > 0;
  return (
    <div className="mt-1.5" dir="rtl">
      <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-5">
        {story.source_count} رسانه · {story.article_count} مقاله
        {published && <span>{" · "}نشر {published}</span>}
        {showUpdated && <span>{" · "}به‌روز: {updated}</span>}
      </p>
      {hasSides && (
        <p className="text-[11px] leading-5 mt-0.5">
          {story.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">محافظه‌کار {story.state_pct}٪</span>}
          {story.state_pct > 0 && story.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
          {story.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">اپوزیسیون {story.diaspora_pct}٪</span>}
        </p>
      )}
    </div>
  );
}

// Wrap a Link. In feedback mode, navigation adds ?feedback=1 so the story
// detail page stays in feedback mode.
function storyHref(locale: string, id: string, feedbackMode: boolean) {
  return feedbackMode
    ? `/${locale}/stories/${id}?feedback=1`
    : `/${locale}/stories/${id}`;
}

// ─── Quick priority vote (submits directly, no modal) ─────────
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function PriorityVoteBtn({ storyId, direction, storyTitle }: {
  storyId: string;
  direction: "higher" | "lower";
  storyTitle: string;
}) {
  const Icon = direction === "higher" ? ArrowUp : ArrowDown;
  const label = direction === "higher" ? "مهم‌تر" : "کم‌اهمیت‌تر";
  const submit = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await fetch(`${API}/api/v1/improvements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "story",
          target_id: storyId,
          issue_type: `priority_${direction}`,
          reason: label,
          device_info: typeof window !== "undefined"
            ? `${window.innerWidth <= 768 ? "mobile" : "desktop"} ${window.innerWidth}×${window.innerHeight}`
            : null,
        }),
      });
    } catch {}
  };
  return (
    <button
      type="button"
      onClick={submit}
      title={label}
      className="p-1 bg-slate-900/80 dark:bg-white/80 text-white dark:text-slate-900 shadow-sm md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity hover:scale-110"
    >
      <Icon className="h-3 w-3" />
    </button>
  );
}

// ─── Reusable story action cluster (priority + merge, feedback mode only) ─
function StoryActions({ storyId, storyTitle, openFeedback }: {
  storyId: string;
  storyTitle: string;
  openFeedback: (ctx: FeedbackContext) => void;
}) {
  return (
    <div className="absolute bottom-1 right-1 z-20 flex gap-1 md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity" dir="ltr">
      <PriorityVoteBtn storyId={storyId} direction="higher" storyTitle={storyTitle} />
      <PriorityVoteBtn storyId={storyId} direction="lower" storyTitle={storyTitle} />
      <button type="button" title="ادغام با موضوع دیگر"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "merge_stories", targetId: storyId, defaultIssueType: "merge_stories", contextLabel: storyTitle }); }}
        className="p-1 bg-slate-900/80 dark:bg-white/80 text-white dark:text-slate-900 shadow-sm hover:scale-110">
        <GitMerge className="h-3 w-3" />
      </button>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────
interface Props {
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
  feedbackMode?: boolean;
}

export default function HomepageLayout({ stories, summaries, locale, feedbackMode = false }: Props) {
  // ALL HOOKS MUST BE ABOVE THE EARLY RETURN
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });

  const openFeedback = useCallback((ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  }, []);

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
      </div>
    );
  }

  const sorted = stories;
  const hero = sorted[0];

  // Most disputed: stories with biggest gap between conservative and opposition
  const disputedCandidates = [...sorted]
    .filter(s => s.state_pct > 0 && s.diaspora_pct > 0)
    .sort((a, b) => Math.abs(b.state_pct - b.diaspora_pct) - Math.abs(a.state_pct - a.diaspora_pct));
  const mostDisputed = disputedCandidates[0] || null;
  const secondDisputed = disputedCandidates[1] || null;

  // Most read: sorted by article count
  const mostRead = [...sorted].sort((a, b) => b.article_count - a.article_count).slice(0, 5);

  // Weekly briefing stories (stories 1-3)
  const briefingStories = sorted.slice(1, 4);

  // Remaining stories for overflow (after hero + briefing)
  const overflowStart = 4;
  const overflow = sorted.slice(overflowStart);

  // Build overflow sections: hero-thumb(2) -> hero-repeat(4) -> text(3)
  const ovSections: { type: "hero-thumb" | "hero-repeat" | "text"; items: StoryBrief[] }[] = [];
  const ovPattern = [
    { type: "hero-thumb" as const, size: 2 },
    { type: "hero-repeat" as const, size: 4 },
    { type: "text" as const, size: 3 },
  ];
  let ovCursor = 0;
  for (const step of ovPattern) {
    if (ovCursor >= overflow.length) break;
    const chunk = overflow.slice(ovCursor, ovCursor + step.size);
    if (chunk.length === 0) break;
    ovSections.push({ type: step.type, items: chunk });
    ovCursor += chunk.length;
  }

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

        {/* ═══ TOP SECTION: Hero (center) + side stories ═══ */}
        <div className="grid grid-cols-12 gap-0 border-b-2 border-slate-300 dark:border-slate-700">

          {/* RIGHT: Recent stories list */}
          <div className="col-span-3 py-6 pl-6 border-l border-slate-200 dark:border-slate-800">
            <h3 className="text-[13px] font-black text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-slate-800">
              آخرین اخبار
            </h3>
            <div className="space-y-3">
              {sorted.slice(4, 8).map((s, i) => (
                <div key={s.id} className={`relative group ${i > 0 ? "border-t border-slate-100 dark:border-slate-800 pt-3" : ""}`}>
                  <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                    <h4 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {s.title_fa}
                    </h4>
                    <p className="text-[11px] text-slate-400 mt-1">{s.source_count} رسانه · {s.article_count} مقاله</p>
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl"
                        onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                      <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* CENTER: Hero story — image + title below */}
          {hero && (
            <div className="col-span-6 py-6 relative group">
              <Link href={storyHref(locale, hero.id, feedbackMode)} className="group block">
                <div className="aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
                </div>
                <h1 className="mt-4 text-[26px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-3">
                  {hero.title_fa}
                </h1>
              </Link>
              <Meta story={hero} />
              {summaries[hero.id] && (
                <p className="mt-2 text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">{summaries[hero.id]}</p>
              )}
              {feedbackMode && (
                <>
                  <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl"
                    onClick={() => openFeedback({ targetType: "story_image", targetId: hero.id, defaultIssueType: "bad_image", contextLabel: hero.title_fa, imageUrl: hero.image_url })} />
                  <FeedbackBtn icon={Type} label="عنوان" position="tr"
                    onClick={() => openFeedback({ targetType: "story_title", targetId: hero.id, currentValue: hero.title_fa, defaultIssueType: "wrong_title", contextLabel: hero.title_fa })} />
                  {summaries[hero.id] && (
                    <FeedbackBtn icon={FileText} label="خلاصه" position="br"
                      onClick={() => openFeedback({ targetType: "story_summary", targetId: hero.id, currentValue: summaries[hero.id] || "", defaultIssueType: "bad_summary", contextLabel: hero.title_fa })} />
                  )}
                  <StoryActions storyId={hero.id} storyTitle={hero.title_fa} openFeedback={openFeedback} />
                </>
              )}
              <AnalystTicker />
            </div>
          )}

          {/* LEFT: Disputed stories */}
          <div className="col-span-3 py-6 pr-6 border-r border-slate-200 dark:border-slate-800 space-y-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">بیشترین اختلاف</span>
              <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            </div>
            {[mostDisputed, secondDisputed].filter(Boolean).map((s) => {
              const story = s!;
              return (
                <div key={story.id} className="relative group">
                  <Link href={storyHref(locale, story.id, feedbackMode)} className="group block border border-slate-200 dark:border-slate-700">
                    <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                      <SafeImage src={story.image_url} className="h-full w-full object-cover" />
                    </div>
                    <div className="p-3">
                      <h3 className="text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {story.title_fa}
                      </h3>
                      <div className="mt-2 flex h-1.5 w-full overflow-hidden">
                        <div className="bg-[#1e3a5f]" style={{ width: `${story.state_pct}%` }} />
                        <div className="bg-[#ea580c]" style={{ width: `${story.diaspora_pct}%` }} />
                      </div>
                      <div className="mt-1 flex items-center justify-between text-[11px]">
                        {story.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">محافظه‌کار {story.state_pct}٪</span>}
                        {story.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400 font-medium">اپوزیسیون {story.diaspora_pct}٪</span>}
                      </div>
                    </div>
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl"
                        onClick={() => openFeedback({ targetType: "story_image", targetId: story.id, defaultIssueType: "bad_image", contextLabel: story.title_fa, imageUrl: story.image_url })} />
                      <FeedbackBtn icon={Type} label="عنوان" position="tr"
                        onClick={() => openFeedback({ targetType: "story_title", targetId: story.id, currentValue: story.title_fa, defaultIssueType: "wrong_title", contextLabel: story.title_fa })} />
                      <StoryActions storyId={story.id} storyTitle={story.title_fa} openFeedback={openFeedback} />
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ═══ WEEKLY BRIEFING + MOST READ ═══ */}
        {briefingStories.length > 0 && (
          <div className="grid grid-cols-12 gap-0 py-8 border-b border-slate-200 dark:border-slate-800">
            {/* Weekly briefing (7 cols) */}
            <div className="col-span-7 pl-6 border-l border-slate-200 dark:border-slate-800">
              <h2 className="text-[22px] font-black text-slate-900 dark:text-white mb-6">هفته گذشته ...</h2>
              <div className="mr-8">
                {briefingStories.map((s, i) => (
                  <div key={s.id} className={`relative group py-5 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                      <h3 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {s.title_fa}
                      </h3>
                      <Meta story={s} />
                      {summaries[s.id] && (
                        <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-1">{summaries[s.id]}</p>
                      )}
                    </Link>
                    {feedbackMode && (
                      <>
                        <FeedbackBtn icon={Type} label="عنوان" position="tl"
                          onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                        {summaries[s.id] && (
                          <FeedbackBtn icon={FileText} label="خلاصه" position="tr"
                            onClick={() => openFeedback({ targetType: "story_summary", targetId: s.id, currentValue: summaries[s.id] || "", defaultIssueType: "bad_summary", contextLabel: s.title_fa })} />
                        )}
                        <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Most read (5 cols) */}
            <div className="col-span-5 pr-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
                <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">پرخواننده‌ترین</span>
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              </div>

              <div className="space-y-0">
                {mostRead.map((s, i) => (
                  <div key={s.id} className={`relative group ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    <Link href={storyHref(locale, s.id, feedbackMode)}
                      className="group flex items-start gap-3 py-3">
                      <span className="text-[20px] font-black text-slate-200 dark:text-slate-700 shrink-0 w-7 text-center mt-0.5">{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-1">
                          {s.title_fa}
                        </h3>
                        <p className="text-[11px] text-slate-400 mt-0.5">{s.article_count} مقاله · {s.source_count} رسانه</p>
                      </div>
                    </Link>
                    {feedbackMode && (
                      <>
                        <FeedbackBtn icon={Type} label="عنوان" position="tr"
                          onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                        <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ═══ OVERFLOW SECTIONS: hero-thumb → hero-repeat → text ═══ */}
        {ovSections.map((sec, si) => {
          if (sec.type === "hero-thumb" && sec.items.length >= 2) {
            const main = sec.items[0], thumb = sec.items[1];
            return (
              <div key={`ov${si}`} className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
                <div className="lg:col-span-3 lg:border-l border-slate-200 dark:border-slate-800 lg:pl-6 flex flex-col justify-center relative group">
                  <Link href={storyHref(locale, thumb.id, feedbackMode)} className="group block">
                    <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800">
                      <SafeImage src={thumb.image_url} className="h-full w-full object-cover" />
                    </div>
                    <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">{thumb.title_fa}</h3>
                    <Meta story={thumb} />
                    <p className="mt-1.5 text-[12px] leading-[20px] text-slate-400 dark:text-slate-500 line-clamp-3">{summaries[thumb.id] || thumb.title_fa}</p>
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl" onClick={() => openFeedback({ targetType: "story_image", targetId: thumb.id, defaultIssueType: "bad_image", contextLabel: thumb.title_fa, imageUrl: thumb.image_url })} />
                      <FeedbackBtn icon={Type} label="عنوان" position="tr" onClick={() => openFeedback({ targetType: "story_title", targetId: thumb.id, currentValue: thumb.title_fa, defaultIssueType: "wrong_title", contextLabel: thumb.title_fa })} />
                      <StoryActions storyId={thumb.id} storyTitle={thumb.title_fa} openFeedback={openFeedback} />
                    </>
                  )}
                </div>
                <div className="lg:col-span-4 flex flex-col justify-center relative group">
                  <Link href={storyHref(locale, main.id, feedbackMode)} className="group block">
                    <h2 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">{main.title_fa}</h2>
                    <Meta story={main} />
                    {summaries[main.id] && (
                      <div className="mt-4">
                        <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{summaries[main.id]}</p>
                        <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                      </div>
                    )}
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl" onClick={() => openFeedback({ targetType: "story_title", targetId: main.id, currentValue: main.title_fa, defaultIssueType: "wrong_title", contextLabel: main.title_fa })} />
                      <StoryActions storyId={main.id} storyTitle={main.title_fa} openFeedback={openFeedback} />
                    </>
                  )}
                </div>
                <div className="lg:col-span-5 relative group">
                  <Link href={storyHref(locale, main.id, feedbackMode)} className="block">
                    <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                      <SafeImage src={main.image_url} className="h-full w-full object-cover" />
                    </div>
                  </Link>
                  {feedbackMode && (
                    <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl" onClick={() => openFeedback({ targetType: "story_image", targetId: main.id, defaultIssueType: "bad_image", contextLabel: main.title_fa, imageUrl: main.image_url })} />
                  )}
                </div>
              </div>
            );
          }
          if (sec.type === "hero-repeat" && sec.items.length >= 1) {
            const heroS = sec.items[0], sideS = sec.items.slice(1);
            return (
              <div key={`ov${si}`} className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
                <div className="lg:col-span-4 flex flex-col justify-center relative group">
                  <Link href={storyHref(locale, heroS.id, feedbackMode)} className="group block">
                    <h1 className="text-[26px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">{heroS.title_fa}</h1>
                    <Meta story={heroS} />
                    <div className="mt-4">
                      <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{summaries[heroS.id] || heroS.title_fa}</p>
                      <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                    </div>
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl" onClick={() => openFeedback({ targetType: "story_title", targetId: heroS.id, currentValue: heroS.title_fa, defaultIssueType: "wrong_title", contextLabel: heroS.title_fa })} />
                      <StoryActions storyId={heroS.id} storyTitle={heroS.title_fa} openFeedback={openFeedback} />
                    </>
                  )}
                </div>
                <div className="lg:col-span-5 relative group">
                  <Link href={storyHref(locale, heroS.id, feedbackMode)} className="block">
                    <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                      <SafeImage src={heroS.image_url} className="h-full w-full object-cover" />
                    </div>
                  </Link>
                  {feedbackMode && (
                    <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl" onClick={() => openFeedback({ targetType: "story_image", targetId: heroS.id, defaultIssueType: "bad_image", contextLabel: heroS.title_fa, imageUrl: heroS.image_url })} />
                  )}
                </div>
                <div className="lg:col-span-3 flex flex-col justify-between lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6">
                  {sideS.map((s, j) => (
                    <div key={s.id} className={`relative group ${j > 0 ? "pt-4 mt-4 border-t border-slate-200 dark:border-slate-800" : ""}`}>
                      <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                        <h3 className="text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">{s.title_fa}</h3>
                        <Meta story={s} />
                      </Link>
                      {feedbackMode && (
                        <>
                          <FeedbackBtn icon={Type} label="عنوان" position="tl" onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                          <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          }
          // text row
          return (
            <div key={`ov${si}`} className={`grid grid-cols-1 ${sec.items.length >= 3 ? "sm:grid-cols-3" : sec.items.length === 2 ? "sm:grid-cols-2" : ""} border-b border-slate-200 dark:border-slate-800`}>
              {sec.items.map((s, i) => (
                <div key={s.id} className={`relative group py-7 ${i > 0 ? "sm:pr-6 sm:border-r border-slate-200 dark:border-slate-800" : ""} ${i < sec.items.length - 1 ? "sm:pl-6" : ""}`}>
                  <Link href={storyHref(locale, s.id, feedbackMode)} className="group block">
                    <h3 className="text-[17px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-1">{s.title_fa}</h3>
                    <Meta story={s} />
                    <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-3">{summaries[s.id] || s.title_fa}</p>
                  </Link>
                  {feedbackMode && (
                    <>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl" onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                      <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                    </>
                  )}
                </div>
              ))}
            </div>
          );
        })}

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
              {hero.state_pct > 0 && <span className="mr-2 text-blue-200"> · محافظه‌کار {hero.state_pct}٪</span>}
              {hero.diaspora_pct > 0 && <span className="mr-2 text-orange-300"> · اپوزیسیون {hero.diaspora_pct}٪</span>}
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
