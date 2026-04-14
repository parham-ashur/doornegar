"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { Image as ImageIcon, Type, FileText, ArrowUp, ArrowDown, GitMerge } from "lucide-react";
import SafeImage from "@/components/common/SafeImage";
import TelegramDiscussions from "@/components/home/TelegramDiscussions";
import WordsOfWeek from "@/components/home/WordsOfWeek";
import WeeklyDigest from "@/components/home/WeeklyDigest";
import ImprovementModal from "@/components/improvement/ImprovementModal";
import RaterOnboarding from "@/components/improvement/RaterOnboarding";
import type { StoryBrief } from "@/lib/types";
import { formatRelativeTime, toFa } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ───
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

type AnalysisMap = Record<string, { bias_explanation_fa?: string; state_summary_fa?: string; diaspora_summary_fa?: string; dispute_score?: number; loaded_words?: { conservative: string[]; opposition: string[] } } | null>;

// ─── Feedback buttons ───
function FeedbackBtn({ onClick, label, icon: Icon, position = "tr" }: {
  onClick: (e: React.MouseEvent) => void;
  label: string;
  icon: any;
  position?: "tr" | "tl" | "br" | "bl";
}) {
  const posClass = { tr: "top-1 right-1", tl: "top-1 left-1", br: "bottom-1 right-1", bl: "bottom-1 left-1" }[position];
  return (
    <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); onClick(e); }}
      title={label} aria-label={label}
      className={`absolute ${posClass} z-20 p-1.5 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 shadow-md md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity hover:scale-110`}>
      <Icon className="h-3 w-3" />
    </button>
  );
}

function PriorityVoteBtn({ storyId, direction, storyTitle }: { storyId: string; direction: "higher" | "lower"; storyTitle: string }) {
  const Icon = direction === "higher" ? ArrowUp : ArrowDown;
  const label = direction === "higher" ? "مهم‌تر" : "کم‌اهمیت‌تر";
  const submit = async (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    try {
      await fetch(`${API}/api/v1/improvements`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: "story", target_id: storyId, issue_type: `priority_${direction}`, reason: label }),
      });
    } catch {}
  };
  return (
    <button type="button" onClick={submit} title={label}
      className="p-1 bg-slate-900/80 dark:bg-white/80 text-white dark:text-slate-900 shadow-sm md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity hover:scale-110">
      <Icon className="h-3 w-3" />
    </button>
  );
}

function StoryActions({ storyId, storyTitle, openFeedback }: {
  storyId: string; storyTitle: string; openFeedback: (ctx: FeedbackContext) => void;
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

function storyHref(locale: string, id: string) {
  return `/${locale}/stories/${id}?feedback=1`;
}

function Meta({ story }: { story: StoryBrief }) {
  const published = story.first_published_at ? formatRelativeTime(story.first_published_at, "fa") : null;
  const updated = story.updated_at ? formatRelativeTime(story.updated_at, "fa") : null;
  const showUpdated = updated && story.updated_at && story.first_published_at
    && Math.abs(new Date(story.updated_at).getTime() - new Date(story.first_published_at).getTime()) > 3600000;
  const hasSides = story.state_pct > 0 || story.diaspora_pct > 0;
  return (
    <div className="mt-1.5" dir="rtl">
      <div className="flex items-center justify-between text-[13px] leading-5">
        <p className="text-slate-400 dark:text-slate-500">
          {toFa(story.source_count)} رسانه · {toFa(story.article_count)} مقاله
          {published && <span>{" · "}نشر {published}</span>}
          {showUpdated && <span>{" · "}به‌روز {updated}</span>}
        </p>
        {hasSides && (
          <p className="shrink-0">
            {story.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">محافظه‌کار {toFa(story.state_pct)}٪</span>}
            {story.state_pct > 0 && story.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
            {story.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">اپوزیسیون {toFa(story.diaspora_pct)}٪</span>}
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Props ───
interface Props {
  locale: string;
  hero: StoryBrief;
  sorted: StoryBrief[];
  leftTextStories: StoryBrief[];
  mostViewed: (StoryBrief & { _popScore: number })[];
  mostDisputed: StoryBrief | null;
  secondDisputed: StoryBrief | null;
  conservativeBlind: StoryBrief | null;
  oppositionBlind: StoryBrief | null;
  allSummaries: Record<string, string | null>;
  allAnalyses: AnalysisMap;
  heroTelegram: any;
  prefetchedTelegram: { storyId: string; analysis: any }[];
}

export default function RateHomeClient({
  locale, hero, sorted, leftTextStories, mostViewed,
  mostDisputed, secondDisputed, conservativeBlind, oppositionBlind,
  allSummaries, allAnalyses, heroTelegram, prefetchedTelegram,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });

  const openFeedback = useCallback((ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  }, []);

  return (
    <>
      <RaterOnboarding />
      {/* Feedback banner */}
      <div dir="rtl" className="bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-900/50 px-4 py-3">
        <div className="mx-auto max-w-7xl">
          <p className="text-[13px] leading-6 text-slate-700 dark:text-slate-300">
            <span className="font-bold">حالت بازخورد</span> —
            دکمه‌های کوچک کنار هر خبر را ببینید: عنوان، تصویر، خلاصه، اولویت و ادغام. کلیک روی هر خبر آن را در حالت بازخورد باز می‌کند.
          </p>
        </div>
      </div>

      <div dir="rtl" className="mx-auto max-w-7xl px-0 md:px-6 lg:px-8">

        {/* ════════════════════════════════════════════ */}
        {/* DESKTOP LAYOUT                               */}
        {/* ════════════════════════════════════════════ */}
        <div className="hidden md:block">

        {/* ═══ TOP: Blind spots | Hero | Telegram ═══ */}
        <div className="grid grid-cols-12 gap-0 border-b-2 border-slate-300 dark:border-slate-700">

          {/* RIGHT: Telegram */}
          <div className="col-span-3 py-6 pl-6 border-l border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden" style={{ maxHeight: 700 }}>
            <h3 className="text-[13px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800 shrink-0">
              تحلیل روایت‌های تلگرام
            </h3>
            <div className="flex-1 min-h-0 overflow-hidden">
              <TelegramDiscussions prefetchedData={prefetchedTelegram} locale={locale} />
            </div>
            <div className="shrink-0 pt-4 border-t border-slate-200 dark:border-slate-800">
              <WordsOfWeek />
            </div>
          </div>

          {/* CENTER: Hero */}
          <div className="col-span-6 py-6 px-5 relative group">
            <Link href={storyHref(locale, hero.id)} className="group block">
              <div className="relative aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
                <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl"
                  onClick={() => openFeedback({ targetType: "story_image", targetId: hero.id, imageUrl: hero.image_url, defaultIssueType: "bad_image", contextLabel: hero.title_fa })} />
              </div>
              <h1 className="mt-4 text-[28px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-3">
                {hero.title_fa}
              </h1>
            </Link>
            <FeedbackBtn icon={Type} label="عنوان" position="tr"
              onClick={() => openFeedback({ targetType: "story_title", targetId: hero.id, currentValue: hero.title_fa, defaultIssueType: "wrong_title", contextLabel: hero.title_fa })} />
            <StoryActions storyId={hero.id} storyTitle={hero.title_fa} openFeedback={openFeedback} />
            <Meta story={hero} />
            {/* Two-side bias */}
            {(() => {
              const analysis = allAnalyses[hero.id];
              const stateSummary = analysis?.state_summary_fa;
              const diasporaSummary = analysis?.diaspora_summary_fa;
              if (!stateSummary && !diasporaSummary) {
                const bias = analysis?.bias_explanation_fa;
                const points = bias?.split(/[.؛]/).map((p: string) => p.trim()).filter((p: string) => p.length > 10).slice(0, 2) || [];
                if (!points.length) return null;
                return (
                  <div className="mt-3 space-y-1">
                    {points.map((point, i) => (
                      <p key={i} className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">• {point}</p>
                    ))}
                  </div>
                );
              }
              return (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {stateSummary && (
                    <div className="border-r-2 border-[#1e3a5f] pr-3">
                      <p className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300 mb-1">روایت محافظه‌کار</p>
                      <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">{stateSummary}</p>
                    </div>
                  )}
                  {diasporaSummary && (
                    <div className="border-r-2 border-[#ea580c] pr-3">
                      <p className="text-[13px] font-bold text-[#ea580c] dark:text-orange-400 mb-1">روایت اپوزیسیون</p>
                      <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">{diasporaSummary}</p>
                    </div>
                  )}
                </div>
              );
            })()}
            {/* Telegram discourse */}
            {heroTelegram?.discourse_summary && (
              <div className="mt-3 px-1">
                <p className="text-[14px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                  <span className="font-bold text-slate-600 dark:text-slate-300">تحلیل روایت‌های تلگرام.</span>
                  {" "}{heroTelegram.discourse_summary}
                </p>
                {heroTelegram.predictions?.length > 0 && (
                  <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-blue-500">پیش‌بینی:</span> {typeof heroTelegram.predictions[0] === "string" ? heroTelegram.predictions[0] : heroTelegram.predictions[0]?.text || ""}
                  </p>
                )}
                {heroTelegram.key_claims?.length > 0 && (
                  <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">
                    <span className="font-bold text-amber-500">ادعا:</span> {typeof heroTelegram.key_claims[0] === "string" ? heroTelegram.key_claims[0] : heroTelegram.key_claims[0]?.text || ""}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* LEFT: Blind spots */}
          <div className="col-span-3 py-4 pr-6 border-r border-slate-200 dark:border-slate-800 space-y-4 flex flex-col justify-center">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</span>
              <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
            </div>
            {conservativeBlind && (
              <div className="relative group">
                <Link href={storyHref(locale, conservativeBlind.id)} className="group block border-[3px] border-[#1e3a5f] shadow-[0_0_12px_rgba(30,58,95,0.4)] hover:shadow-[0_0_20px_rgba(30,58,95,0.6)] transition-shadow animate-pulse-glow-blue">
                  <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={conservativeBlind.image_url} className="h-full w-full object-cover" />
                  </div>
                  <div className="p-3">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {conservativeBlind.title_fa}
                    </h3>
                    <p className="mt-1.5 text-[13px] text-slate-400">فقط روایت محافظه‌کار · {conservativeBlind.article_count} مقاله</p>
                  </div>
                </Link>
                <FeedbackBtn icon={Type} label="عنوان" position="tl"
                  onClick={() => openFeedback({ targetType: "story_title", targetId: conservativeBlind.id, currentValue: conservativeBlind.title_fa, defaultIssueType: "wrong_title", contextLabel: conservativeBlind.title_fa })} />
                <StoryActions storyId={conservativeBlind.id} storyTitle={conservativeBlind.title_fa} openFeedback={openFeedback} />
              </div>
            )}
            {oppositionBlind && (
              <div className="relative group">
                <Link href={storyHref(locale, oppositionBlind.id)} className="group block border-[3px] border-[#ea580c] shadow-[0_0_12px_rgba(234,88,12,0.4)] hover:shadow-[0_0_20px_rgba(234,88,12,0.6)] transition-shadow animate-pulse-glow-orange">
                  <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={oppositionBlind.image_url} className="h-full w-full object-cover" />
                  </div>
                  <div className="p-3">
                    <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {oppositionBlind.title_fa}
                    </h3>
                    <p className="mt-1.5 text-[13px] text-orange-500">فقط روایت اپوزیسیون · {oppositionBlind.article_count} مقاله</p>
                  </div>
                </Link>
                <FeedbackBtn icon={Type} label="عنوان" position="tl"
                  onClick={() => openFeedback({ targetType: "story_title", targetId: oppositionBlind.id, currentValue: oppositionBlind.title_fa, defaultIssueType: "wrong_title", contextLabel: oppositionBlind.title_fa })} />
                <StoryActions storyId={oppositionBlind.id} storyTitle={oppositionBlind.title_fa} openFeedback={openFeedback} />
              </div>
            )}
          </div>
        </div>

        {/* ═══ WEEKLY BRIEFING + MOST VIEWED ═══ */}
        {sorted.length > 1 && (
          <div className="grid grid-cols-12 gap-0 py-8 border-b border-slate-200 dark:border-slate-800">
            <div className="col-span-7 pl-6 border-l border-slate-200 dark:border-slate-800">
              <h2 className="text-[24px] font-black text-slate-900 dark:text-white mb-6">در روزهای گذشته ...</h2>
              <div className="mr-8">
                {leftTextStories.map((s, i) => (
                  <div key={s.id} className={`relative group py-5 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                    <Link href={storyHref(locale, s.id)} className="group block">
                      <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                        {s.title_fa}
                      </h3>
                      <Meta story={s} />
                      {(() => {
                        const bias = allAnalyses[s.id]?.bias_explanation_fa;
                        if (!bias) return null;
                        const firstPoint = bias.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
                        if (!firstPoint) return null;
                        return <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>;
                      })()}
                    </Link>
                    <FeedbackBtn icon={Type} label="عنوان" position="tl"
                      onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                    <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                  </div>
                ))}
              </div>
            </div>

            {/* Most viewed */}
            <div className="col-span-5 pr-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
                <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">پرمخاطب‌ترین</span>
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              </div>
              <div className="space-y-0">
                {mostViewed.map((s, i) => {
                  const bias = allAnalyses[s.id]?.bias_explanation_fa;
                  const firstPoint = bias?.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
                  return (
                    <div key={s.id} className={`relative group py-4 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                      <Link href={storyHref(locale, s.id)} className="group flex items-start gap-3">
                        <span className="text-[24px] font-black text-slate-200 dark:text-slate-700 shrink-0 w-8 text-center mt-0.5">{toFa(i + 1)}</span>
                        <div className="flex-1 min-w-0">
                          <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                            {s.title_fa}
                          </h3>
                          <p className="text-[14px] text-slate-400 mt-1">
                            {toFa(s.article_count)} مقاله · {toFa(s.source_count)} رسانه
                            {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                            {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
                          </p>
                          {firstPoint && (
                            <p className="text-[14px] text-slate-400 dark:text-slate-500 mt-1 line-clamp-1">• {firstPoint}</p>
                          )}
                        </div>
                      </Link>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl"
                        onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                      <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ═══ MOST DISPUTED + BATTLE OF NUMBERS ═══ */}
        <div className="grid grid-cols-2 gap-6 py-8 border-b border-slate-200 dark:border-slate-800 items-stretch">
          {/* Most disputed */}
          <div>
            <div className="border border-slate-300 dark:border-slate-600 h-full flex flex-col">
              <div className="flex items-center -mt-3 mx-4">
                <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
                <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">بیشترین اختلاف نگاه</span>
                <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
              </div>
              <div className="px-4 pb-4 pt-2 flex-1">
                {[mostDisputed, secondDisputed].filter(Boolean).map((story, i) => {
                  const s = story!;
                  const analysis = allAnalyses[s.id];
                  const stateSummary = analysis?.state_summary_fa;
                  const diasporaSummary = analysis?.diaspora_summary_fa;
                  return (
                    <div key={s.id} className={`relative group py-4 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""}`}>
                      <Link href={storyHref(locale, s.id)} className="group block">
                        <h4 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                          {s.title_fa}
                        </h4>
                        <div className="mt-1 flex items-center justify-end gap-3 text-[13px]">
                          <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">محافظه‌کار {toFa(s.state_pct)}٪</span>
                          <span className="text-[#ea580c] dark:text-orange-400 font-medium">اپوزیسیون {toFa(s.diaspora_pct)}٪</span>
                        </div>
                      </Link>
                      {(stateSummary || diasporaSummary) && (
                        <div className="mt-2 space-y-1">
                          {stateSummary && (
                            <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">
                              <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">• </span>{stateSummary}
                            </p>
                          )}
                          {diasporaSummary && (
                            <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-1">
                              <span className="text-[#ea580c] dark:text-orange-400 font-medium">در مقابل </span>{diasporaSummary}
                            </p>
                          )}
                        </div>
                      )}
                      <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Battle of numbers */}
          <div>
            <div className="border border-slate-300 dark:border-slate-600 h-full flex flex-col">
              <div className="flex items-center -mt-3 mx-4">
                <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
                <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">تقابل روایت‌ها</span>
                <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
              </div>
              <div className="space-y-5 px-4 pb-4 pt-2 flex-1 flex flex-col justify-between">
                {(() => {
                  type BattleItem = { title: string; conservative: string; opposition: string; conservativeLabel: string; oppositionLabel: string };
                  const battleItems: BattleItem[] = [];
                  for (const story of [mostDisputed, secondDisputed]) {
                    if (!story) continue;
                    const analysis = allAnalyses[story.id];
                    if (!analysis) continue;
                    const words = analysis.loaded_words;
                    const stateSummary = analysis.state_summary_fa;
                    const diasporaSummary = analysis.diaspora_summary_fa;
                    const biasText = analysis.bias_explanation_fa;
                    if (words?.conservative?.length && words?.opposition?.length) {
                      battleItems.push({
                        title: story.title_fa || "",
                        conservative: `«${words.conservative[0].replace(/[«»]/g, "")}»`,
                        opposition: `«${words.opposition[0].replace(/[«»]/g, "")}»`,
                        conservativeLabel: words.conservative.length > 1 ? words.conservative.slice(1, 3).join("، ") : "روایت محافظه‌کار",
                        oppositionLabel: words.opposition.length > 1 ? words.opposition.slice(1, 3).join("، ") : "روایت اپوزیسیون",
                      });
                      continue;
                    }
                    if (biasText) {
                      const quotes = biasText.match(/«[^»]+»/g);
                      if (quotes && quotes.length >= 2) {
                        battleItems.push({
                          title: story.title_fa || "",
                          conservative: quotes[0],
                          opposition: quotes[1],
                          conservativeLabel: stateSummary ? stateSummary.slice(0, 40) + (stateSummary.length > 40 ? "..." : "") : "روایت محافظه‌کار",
                          oppositionLabel: diasporaSummary ? diasporaSummary.slice(0, 40) + (diasporaSummary.length > 40 ? "..." : "") : "روایت اپوزیسیون",
                        });
                        continue;
                      }
                    }
                    if (stateSummary && diasporaSummary) {
                      const stateShort = stateSummary.length > 25 ? stateSummary.slice(0, 25) + "..." : stateSummary;
                      const diasporaShort = diasporaSummary.length > 25 ? diasporaSummary.slice(0, 25) + "..." : diasporaSummary;
                      battleItems.push({
                        title: story.title_fa || "",
                        conservative: `«${stateShort}»`,
                        opposition: `«${diasporaShort}»`,
                        conservativeLabel: "خلاصه رسانه‌های محافظه‌کار",
                        oppositionLabel: "خلاصه رسانه‌های اپوزیسیون",
                      });
                    }
                  }
                  if (battleItems.length === 0) {
                    battleItems.push(
                      { title: "تلفات حملات هوایی", conservative: "«شهدای مدافع»", opposition: "«صدها غیرنظامی»", conservativeLabel: "تلفات محدود نظامی", oppositionLabel: "کشتار گسترده مردم" },
                      { title: "قطع اینترنت", conservative: "«اختلال موقت»", opposition: "«۴۰ روز قطع کامل»", conservativeLabel: "محدودیت امنیتی", oppositionLabel: "قطع عمدی و سراسری" },
                    );
                  }
                  return battleItems.slice(0, 2).map((item, idx) => (
                    <div key={idx}>
                      <p className="text-[13px] font-bold text-slate-900 dark:text-white mb-3 line-clamp-1">{item.title}</p>
                      <div className="flex gap-0 text-center">
                        <div className="flex-1 py-3 bg-[#1e3a5f]/10 dark:bg-blue-900/20 border-t-[3px] border-[#1e3a5f]">
                          <p className={`${item.conservative.length > 20 ? "text-[24px]" : "text-[14px]"} font-black text-[#1e3a5f] dark:text-blue-300 line-clamp-1 px-2`}>{item.conservative}</p>
                          <p className="text-[13px] text-slate-500 mt-1 line-clamp-1 px-2">{item.conservativeLabel}</p>
                          <p className="text-[13px] text-[#1e3a5f] dark:text-blue-300 font-medium mt-0.5">محافظه‌کار</p>
                        </div>
                        <div className="flex-1 py-3 bg-[#ea580c]/10 dark:bg-orange-900/20 border-t-[3px] border-[#ea580c]">
                          <p className={`${item.opposition.length > 20 ? "text-[24px]" : "text-[14px]"} font-black text-[#ea580c] dark:text-orange-400 line-clamp-1 px-2`}>{item.opposition}</p>
                          <p className="text-[13px] text-slate-500 mt-1 line-clamp-1 px-2">{item.oppositionLabel}</p>
                          <p className="text-[13px] text-[#ea580c] dark:text-orange-400 font-medium mt-0.5">اپوزیسیون</p>
                        </div>
                      </div>
                    </div>
                  ));
                })()}
              </div>
            </div>
          </div>
        </div>

        {/* ═══ WEEKLY DIGEST ═══ */}
        <div className="py-8">
          <WeeklyDigest />
        </div>

        </div>

        {/* ════════════════════════════════════════════ */}
        {/* MOBILE LAYOUT                                */}
        {/* ════════════════════════════════════════════ */}
        <div className="md:hidden">
          {/* Hero */}
          <div className="relative group border-b border-slate-200 dark:border-slate-800">
            <Link href={storyHref(locale, hero.id)} className="block">
              <div className="relative aspect-[16/9] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
                <FeedbackBtn icon={ImageIcon} label="تصویر" position="tl"
                  onClick={() => openFeedback({ targetType: "story_image", targetId: hero.id, imageUrl: hero.image_url, defaultIssueType: "bad_image", contextLabel: hero.title_fa })} />
              </div>
              <div className="px-4 py-4">
                <h1 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white line-clamp-3">{hero.title_fa}</h1>
                <div className="mt-2">
                  <p className="text-[13px] text-slate-400 dark:text-slate-500">
                    {toFa(hero.source_count)} رسانه · {toFa(hero.article_count)} مقاله
                  </p>
                  {(hero.state_pct > 0 || hero.diaspora_pct > 0) && (
                    <p className="text-[13px] mt-0.5">
                      {hero.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">محافظه‌کار {toFa(hero.state_pct)}٪</span>}
                      {hero.state_pct > 0 && hero.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
                      {hero.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">اپوزیسیون {toFa(hero.diaspora_pct)}٪</span>}
                    </p>
                  )}
                </div>
              </div>
            </Link>
            <FeedbackBtn icon={Type} label="عنوان" position="tr"
              onClick={() => openFeedback({ targetType: "story_title", targetId: hero.id, currentValue: hero.title_fa, defaultIssueType: "wrong_title", contextLabel: hero.title_fa })} />
            <StoryActions storyId={hero.id} storyTitle={hero.title_fa} openFeedback={openFeedback} />
          </div>

          {/* Blind spots */}
          {(conservativeBlind || oppositionBlind) && (
            <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
                <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">نگاه یک‌جانبه</span>
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              </div>
              <div className="space-y-4">
                {conservativeBlind && (
                  <div className="relative group">
                    <Link href={storyHref(locale, conservativeBlind.id)}
                      className="group block border-[3px] border-[#1e3a5f] shadow-[0_0_12px_rgba(30,58,95,0.4)] animate-pulse-glow-blue">
                      <div className="flex gap-3 p-3">
                        <div className="w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                          <SafeImage src={conservativeBlind.image_url} className="h-full w-full object-cover" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white line-clamp-2">{conservativeBlind.title_fa}</h3>
                          <p className="mt-1 text-[13px] text-slate-400">فقط روایت محافظه‌کار · {conservativeBlind.article_count} مقاله</p>
                        </div>
                      </div>
                    </Link>
                    <StoryActions storyId={conservativeBlind.id} storyTitle={conservativeBlind.title_fa} openFeedback={openFeedback} />
                  </div>
                )}
                {oppositionBlind && (
                  <div className="relative group">
                    <Link href={storyHref(locale, oppositionBlind.id)}
                      className="group block border-[3px] border-[#ea580c] shadow-[0_0_12px_rgba(234,88,12,0.4)] animate-pulse-glow-orange">
                      <div className="flex gap-3 p-3">
                        <div className="w-20 h-20 shrink-0 overflow-hidden bg-slate-100 dark:bg-slate-800">
                          <SafeImage src={oppositionBlind.image_url} className="h-full w-full object-cover" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white line-clamp-2">{oppositionBlind.title_fa}</h3>
                          <p className="mt-1 text-[13px] text-orange-500">فقط روایت اپوزیسیون · {oppositionBlind.article_count} مقاله</p>
                        </div>
                      </div>
                    </Link>
                    <StoryActions storyId={oppositionBlind.id} storyTitle={oppositionBlind.title_fa} openFeedback={openFeedback} />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Weekly briefing */}
          {leftTextStories.length > 0 && (
            <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
              <h2 className="text-[20px] font-black text-slate-900 dark:text-white mb-3">در روزهای گذشته ...</h2>
              <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {leftTextStories.map((s) => {
                  const bias = allAnalyses[s.id]?.bias_explanation_fa;
                  const firstPoint = bias?.split(/[.؛]/).map((p: string) => p.trim()).find((p: string) => p.length > 10);
                  return (
                    <div key={s.id} className="relative group py-4">
                      <Link href={storyHref(locale, s.id)} className="group block">
                        <h3 className="text-[22px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                          {s.title_fa}
                        </h3>
                        <p className="mt-1 text-[13px] text-slate-400 dark:text-slate-500">
                          {toFa(s.source_count)} رسانه · {toFa(s.article_count)} مقاله
                          {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                          {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
                        </p>
                        {firstPoint && (
                          <p className="mt-1.5 text-[14px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-1">• {firstPoint}</p>
                        )}
                      </Link>
                      <FeedbackBtn icon={Type} label="عنوان" position="tl"
                        onClick={() => openFeedback({ targetType: "story_title", targetId: s.id, currentValue: s.title_fa, defaultIssueType: "wrong_title", contextLabel: s.title_fa })} />
                      <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Most viewed */}
          {mostViewed.length > 0 && (
            <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
                <span className="text-[13px] font-black text-slate-900 dark:text-white shrink-0">پرمخاطب‌ترین</span>
                <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
              </div>
              <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {mostViewed.map((s, i) => (
                  <div key={s.id} className="relative group py-3">
                    <Link href={storyHref(locale, s.id)} className="group flex items-start gap-3">
                      <span className="text-[14px] font-black text-slate-200 dark:text-slate-700 shrink-0 w-7 text-center mt-0.5">{toFa(i + 1)}</span>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-[18px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                          {s.title_fa}
                        </h3>
                        <p className="text-[13px] text-slate-400 mt-0.5">
                          {toFa(s.article_count)} مقاله · {toFa(s.source_count)} رسانه
                          {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · محافظه‌کار {toFa(s.state_pct)}٪</span>}
                          {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · اپوزیسیون {toFa(s.diaspora_pct)}٪</span>}
                        </p>
                      </div>
                    </Link>
                    <StoryActions storyId={s.id} storyTitle={s.title_fa} openFeedback={openFeedback} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Telegram */}
          <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
            <h3 className="text-[13px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
              تحلیل روایت‌های تلگرام
            </h3>
            <TelegramDiscussions storyIds={sorted.slice(0, 5).map(s => s.id)} locale={locale} />
          </div>

          {/* Words of day */}
          <div className="px-4 py-5 border-b border-slate-200 dark:border-slate-800">
            <WordsOfWeek />
          </div>
        </div>
      </div>

      {/* Feedback modal */}
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
