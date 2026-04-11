"use client";

import { useEffect, useState } from "react";
import { useLocale } from "next-intl";
import {
  Image as ImageIcon, Type, FileText, LayoutGrid,
  MessageSquare, Info, Sparkles,
} from "lucide-react";
import SafeImage from "@/components/common/SafeImage";
import ImprovementModal from "@/components/improvement/ImprovementModal";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Story {
  id: string;
  title_fa: string;
  slug: string;
  article_count: number;
  source_count: number;
  image_url: string | null;
  state_pct: number;
  diaspora_pct: number;
  independent_pct: number;
}

type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "layout" | "homepage" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request" | "other";

interface FeedbackContext {
  targetType: TargetType;
  targetId?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
}

async function fetchSummary(storyId: string): Promise<string | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.summary_fa || null;
  } catch {
    return null;
  }
}

// Small floating feedback icon that appears on hover
function FeedbackIcon({
  onClick,
  label,
  icon: Icon,
  position = "top-right",
}: {
  onClick: (e: React.MouseEvent) => void;
  label: string;
  icon: typeof Type;
  position?: "top-right" | "top-left" | "center";
}) {
  const posClass = {
    "top-right": "top-1 right-1",
    "top-left": "top-1 left-1",
    "center": "top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2",
  }[position];

  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick(e);
      }}
      title={label}
      aria-label={label}
      className={`absolute ${posClass} z-20 p-1.5 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 hover:scale-110 transition-transform shadow-md opacity-0 group-hover:opacity-100 focus:opacity-100`}
    >
      <Icon className="h-3 w-3" />
    </button>
  );
}

export default function RatePage() {
  const locale = useLocale();
  const [stories, setStories] = useState<Story[]>([]);
  const [summaries, setSummaries] = useState<Record<string, string | null>>({});
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });
  const [helpShown, setHelpShown] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/v1/stories/trending?limit=30`)
      .then((r) => r.json())
      .then(async (data) => {
        const list: Story[] = Array.isArray(data) ? data : [];
        setStories(list);
        setLoading(false);
        // Fetch summaries in parallel
        const results = await Promise.all(
          list.slice(0, 20).map((s) => fetchSummary(s.id).then((sum) => [s.id, sum] as [string, string | null]))
        );
        const map: Record<string, string | null> = {};
        for (const [id, sum] of results) map[id] = sum;
        setSummaries(map);
      })
      .catch(() => setLoading(false));
  }, []);

  const openModal = (ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  };

  if (loading) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-6 lg:px-8 py-12 text-center">
        <p className="text-sm text-slate-500">در حال بارگذاری...</p>
      </div>
    );
  }

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-6 lg:px-8 py-12 text-center">
        <p className="text-sm text-slate-500">هنوز خبری برای بازبینی وجود ندارد</p>
      </div>
    );
  }

  const hero = stories[0];
  const thumbs1 = stories.slice(1, 5);
  const feature = stories[5];
  const textRow = stories.slice(6, 9);
  const thumbs2 = stories.slice(9, 13);
  const remaining = stories.slice(13, 20);

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-4 md:px-6 lg:px-8 py-4">
      {/* Help banner — shows first time */}
      {helpShown && (
        <div className="mb-6 p-4 border border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 flex items-start gap-3">
          <Sparkles className="h-5 w-5 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
              حالت بازخورد
            </h3>
            <p className="text-[12px] leading-6 text-slate-600 dark:text-slate-400">
              این همان صفحه اصلی است، اما با امکان ثبت بازخورد. روی هر تصویر، عنوان
              یا خلاصه‌ای که می‌خواهید نظر بدهید کلیک کنید. پیشنهاد شما بدون نام
              ارسال می‌شود و مستقیماً به فهرست کارهای تیم می‌رود.
            </p>
          </div>
          <button
            onClick={() => setHelpShown(false)}
            className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline shrink-0"
          >
            بستن
          </button>
        </div>
      )}

      {/* Quick general feedback buttons */}
      <div className="mb-6 flex flex-wrap gap-2">
        <button
          onClick={() =>
            openModal({
              targetType: "homepage",
              defaultIssueType: "layout_issue",
              contextLabel: "صفحه اصلی / چیدمان",
            })
          }
          className="px-3 py-1.5 text-xs border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-900 dark:hover:border-white flex items-center gap-1.5"
        >
          <LayoutGrid className="h-3 w-3" />
          پیشنهاد درباره چیدمان
        </button>
        <button
          onClick={() =>
            openModal({
              targetType: "other",
              defaultIssueType: "feature_request",
              contextLabel: "پیشنهاد کلی",
            })
          }
          className="px-3 py-1.5 text-xs border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-900 dark:hover:border-white flex items-center gap-1.5"
        >
          <MessageSquare className="h-3 w-3" />
          پیشنهاد ویژگی
        </button>
        <button
          onClick={() =>
            openModal({
              targetType: "other",
              defaultIssueType: "bug",
              contextLabel: "گزارش مشکل",
            })
          }
          className="px-3 py-1.5 text-xs border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-900 dark:hover:border-white flex items-center gap-1.5"
        >
          <Info className="h-3 w-3" />
          گزارش باگ
        </button>
      </div>

      {/* ROW 1: Hero */}
      {hero && (
        <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
          <div className="lg:col-span-4 flex flex-col justify-center relative group">
            <div className="group block">
              <h1 className="text-[26px] font-black leading-snug text-slate-900 dark:text-white pr-8">
                {hero.title_fa}
              </h1>
              <FeedbackIcon
                icon={Type}
                label="بازخورد درباره عنوان"
                onClick={() =>
                  openModal({
                    targetType: "story_title",
                    targetId: hero.id,
                    currentValue: hero.title_fa,
                    defaultIssueType: "wrong_title",
                    contextLabel: hero.title_fa,
                  })
                }
                position="top-right"
              />
              <p className="mt-1.5 text-[13px] text-slate-400 dark:text-slate-500">
                <span>{hero.source_count} رسانه</span>
                <span>{" · "}</span>
                <span>{hero.article_count} مقاله</span>
                {hero.state_pct > 0 && <span className="text-red-500 mr-2">{" · "}حکومتی {hero.state_pct}٪</span>}
                {hero.independent_pct > 0 && <span className="text-emerald-600 mr-2">{" · "}مستقل {hero.independent_pct}٪</span>}
                {hero.diaspora_pct > 0 && <span className="text-blue-600 mr-2">{" · "}برون‌مرزی {hero.diaspora_pct}٪</span>}
              </p>
              {summaries[hero.id] && (
                <div className="mt-4 relative group/summary">
                  <p className="text-[13px] leading-7 text-slate-500 dark:text-slate-400 line-clamp-5 pl-8">
                    {summaries[hero.id]}
                  </p>
                  <button
                    onClick={() =>
                      openModal({
                        targetType: "story_summary",
                        targetId: hero.id,
                        currentValue: summaries[hero.id] || "",
                        defaultIssueType: "bad_summary",
                        contextLabel: hero.title_fa,
                      })
                    }
                    title="بازخورد درباره خلاصه"
                    className="absolute top-0 left-0 p-1.5 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 hover:scale-110 transition-transform opacity-0 group-hover/summary:opacity-100 focus:opacity-100"
                  >
                    <FileText className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-5 relative group">
            <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
              <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
            </div>
            <FeedbackIcon
              icon={ImageIcon}
              label="بازخورد درباره تصویر"
              onClick={() =>
                openModal({
                  targetType: "story_image",
                  targetId: hero.id,
                  defaultIssueType: "bad_image",
                  contextLabel: hero.title_fa,
                })
              }
              position="top-right"
            />
          </div>

          {thumbs1[0] && (
            <div className="lg:col-span-3 lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6 flex flex-col justify-center relative group">
              <div className="block">
                <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800 relative">
                  <SafeImage src={thumbs1[0].image_url} className="h-full w-full object-cover" />
                  <FeedbackIcon
                    icon={ImageIcon}
                    label="تصویر"
                    onClick={() =>
                      openModal({
                        targetType: "story_image",
                        targetId: thumbs1[0].id,
                        defaultIssueType: "bad_image",
                        contextLabel: thumbs1[0].title_fa,
                      })
                    }
                  />
                </div>
                <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white line-clamp-2 pl-6 relative">
                  {thumbs1[0].title_fa}
                  <button
                    onClick={() =>
                      openModal({
                        targetType: "story_title",
                        targetId: thumbs1[0].id,
                        currentValue: thumbs1[0].title_fa,
                        defaultIssueType: "wrong_title",
                        contextLabel: thumbs1[0].title_fa,
                      })
                    }
                    title="عنوان"
                    className="absolute top-0 left-0 p-1 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Type className="h-3 w-3" />
                  </button>
                </h3>
                <p className="mt-1 text-[12px] text-slate-400">
                  {thumbs1[0].source_count} رسانه · {thumbs1[0].article_count} مقاله
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ROW 2: Thumbnails */}
      {thumbs1.length > 1 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 border-b border-slate-200 dark:border-slate-800 py-6">
          {thumbs1.slice(1).map((s) => (
            <div key={s.id} className="group block">
              <div className="aspect-[4/3] w-full overflow-hidden bg-slate-100 dark:bg-slate-800 mb-3 relative">
                <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                <FeedbackIcon
                  icon={ImageIcon}
                  label="تصویر"
                  onClick={() =>
                    openModal({
                      targetType: "story_image",
                      targetId: s.id,
                      defaultIssueType: "bad_image",
                      contextLabel: s.title_fa,
                    })
                  }
                />
              </div>
              <div className="relative">
                <h3 className="text-[14px] font-extrabold leading-snug text-slate-900 dark:text-white line-clamp-2 pl-6">
                  {s.title_fa}
                </h3>
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story_title",
                      targetId: s.id,
                      currentValue: s.title_fa,
                      defaultIssueType: "wrong_title",
                      contextLabel: s.title_fa,
                    })
                  }
                  title="عنوان"
                  className="absolute top-0 left-0 p-1 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Type className="h-3 w-3" />
                </button>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                {s.source_count} رسانه · {s.article_count} مقاله
              </p>
              <button
                onClick={() =>
                  openModal({
                    targetType: "story",
                    targetId: s.id,
                    defaultIssueType: "wrong_clustering",
                    contextLabel: s.title_fa,
                  })
                }
                className="mt-2 text-[10px] text-slate-400 hover:text-slate-900 dark:hover:text-white underline decoration-dotted"
              >
                بازخورد درباره دسته‌بندی
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ROW 3: Text-only stories */}
      {textRow.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 border-b border-slate-200 dark:border-slate-800">
          {textRow.map((s, i) => (
            <div
              key={s.id}
              className={`group py-6 relative ${i > 0 ? "md:pr-6 md:border-r border-slate-200 dark:border-slate-800" : ""} ${i < textRow.length - 1 ? "md:pl-6" : ""}`}
            >
              <h3 className="text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white pl-6 line-clamp-2">
                {s.title_fa}
              </h3>
              <button
                onClick={() =>
                  openModal({
                    targetType: "story_title",
                    targetId: s.id,
                    currentValue: s.title_fa,
                    defaultIssueType: "wrong_title",
                    contextLabel: s.title_fa,
                  })
                }
                title="عنوان"
                className="absolute top-6 left-0 p-1 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <Type className="h-3 w-3" />
              </button>
              <p className="mt-1.5 text-[12px] text-slate-400 dark:text-slate-500">
                <span>{s.source_count} رسانه</span>
                <span>{" · "}</span>
                <span>{s.article_count} مقاله</span>
              </p>
              {summaries[s.id] && (
                <div className="mt-2 relative group/sum">
                  <p className="text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3 pl-6">
                    {summaries[s.id]}
                  </p>
                  <button
                    onClick={() =>
                      openModal({
                        targetType: "story_summary",
                        targetId: s.id,
                        currentValue: summaries[s.id] || "",
                        defaultIssueType: "bad_summary",
                        contextLabel: s.title_fa,
                      })
                    }
                    title="خلاصه"
                    className="absolute top-0 left-0 p-1 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 opacity-0 group-hover/sum:opacity-100 transition-opacity"
                  >
                    <FileText className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* More thumbnails */}
      {thumbs2.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 border-b border-slate-200 dark:border-slate-800 py-6">
          {thumbs2.map((s) => (
            <div key={s.id} className="group block">
              <div className="aspect-[4/3] w-full overflow-hidden bg-slate-100 dark:bg-slate-800 mb-3 relative">
                <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                <FeedbackIcon
                  icon={ImageIcon}
                  label="تصویر"
                  onClick={() =>
                    openModal({
                      targetType: "story_image",
                      targetId: s.id,
                      defaultIssueType: "bad_image",
                      contextLabel: s.title_fa,
                    })
                  }
                />
              </div>
              <div className="relative">
                <h3 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white line-clamp-2 pl-6">
                  {s.title_fa}
                </h3>
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story_title",
                      targetId: s.id,
                      currentValue: s.title_fa,
                      defaultIssueType: "wrong_title",
                      contextLabel: s.title_fa,
                    })
                  }
                  title="عنوان"
                  className="absolute top-0 left-0 p-1 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Type className="h-3 w-3" />
                </button>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                {s.source_count} رسانه · {s.article_count} مقاله
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Remaining as compact text */}
      {remaining.length > 0 && (
        <div className="divide-y divide-slate-200 dark:divide-slate-800 py-2">
          {remaining.map((s) => (
            <div key={s.id} className="group py-4 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white line-clamp-2">
                  {s.title_fa}
                </h3>
                <p className="mt-1 text-[11px] text-slate-400">
                  {s.source_count} رسانه · {s.article_count} مقاله
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story_title",
                      targetId: s.id,
                      currentValue: s.title_fa,
                      defaultIssueType: "wrong_title",
                      contextLabel: s.title_fa,
                    })
                  }
                  title="عنوان"
                  className="p-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-900 dark:hover:bg-white hover:text-white dark:hover:text-slate-900"
                >
                  <Type className="h-3 w-3" />
                </button>
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story",
                      targetId: s.id,
                      defaultIssueType: "wrong_clustering",
                      contextLabel: s.title_fa,
                    })
                  }
                  title="دسته‌بندی"
                  className="p-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-900 dark:hover:bg-white hover:text-white dark:hover:text-slate-900"
                >
                  <LayoutGrid className="h-3 w-3" />
                </button>
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story",
                      targetId: s.id,
                      defaultIssueType: "other",
                      contextLabel: s.title_fa,
                    })
                  }
                  title="سایر"
                  className="p-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-900 dark:hover:bg-white hover:text-white dark:hover:text-slate-900"
                >
                  <MessageSquare className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ImprovementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        targetType={context.targetType}
        targetId={context.targetId}
        currentValue={context.currentValue}
        defaultIssueType={context.defaultIssueType}
        contextLabel={context.contextLabel}
      />
    </div>
  );
}
