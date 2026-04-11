"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale } from "next-intl";
import { Edit2, Image as ImageIcon, Type, FileText, Layout } from "lucide-react";
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

export default function ImprovePage() {
  const locale = useLocale();
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });

  useEffect(() => {
    fetch(`${API}/api/v1/stories/trending?limit=30`)
      .then((r) => r.json())
      .then((data) => {
        setStories(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const openModal = (ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  };

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8 md:py-12">
      {/* Header */}
      <div className="mb-6 pb-4 border-b border-slate-200 dark:border-slate-800">
        <h1 className="text-2xl md:text-3xl font-black text-slate-900 dark:text-white mb-2">
          صفحه پیشنهاد اصلاحات
        </h1>
        <p className="text-sm leading-7 text-slate-500 dark:text-slate-400">
          این صفحه برای ارائه پیشنهاد اصلاحات درباره محتوای سایت است. روی دکمه‌های
          کنار هر خبر کلیک کنید تا پیشنهاد خود را ارسال کنید. پیشنهاد شما به
          فهرست کارهای تیم اضافه می‌شود.
        </p>
      </div>

      {/* Homepage layout feedback */}
      <div className="mb-6 p-4 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            پیشنهاد درباره صفحه اصلی
          </h3>
          <p className="text-xs text-slate-500 mt-1">
            چیدمان، طراحی، یا بخش‌هایی از صفحه اصلی نیاز به اصلاح دارند؟
          </p>
        </div>
        <button
          onClick={() =>
            openModal({
              targetType: "homepage",
              defaultIssueType: "layout_issue",
              contextLabel: "صفحه اصلی",
            })
          }
          className="shrink-0 px-3 py-2 text-xs font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200"
        >
          <Layout className="h-4 w-4 inline ml-1" />
          پیشنهاد صفحه
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500 py-8 text-center">در حال بارگذاری...</p>
      ) : (
        <div className="space-y-4">
          {stories.map((s) => (
            <div
              key={s.id}
              className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 grid grid-cols-1 md:grid-cols-[120px_1fr_auto] gap-4 items-start"
            >
              {/* Thumbnail */}
              <div className="relative group">
                <div className="aspect-[4/3] w-full md:w-[120px] overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                </div>
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story_image",
                      targetId: s.id,
                      defaultIssueType: "bad_image",
                      contextLabel: s.title_fa,
                    })
                  }
                  className="absolute -top-1 -left-1 p-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:scale-110 transition-transform"
                  title="پیشنهاد برای تصویر"
                >
                  <ImageIcon className="h-3 w-3" />
                </button>
              </div>

              {/* Content */}
              <div className="min-w-0">
                <div className="flex items-start gap-2">
                  <Link
                    href={`/${locale}/stories/${s.id}`}
                    className="flex-1 min-w-0"
                    target="_blank"
                  >
                    <h3 className="text-[15px] font-bold text-slate-900 dark:text-white leading-snug hover:text-blue-700 dark:hover:text-blue-400 line-clamp-2">
                      {s.title_fa}
                    </h3>
                  </Link>
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
                    className="shrink-0 p-1.5 text-slate-400 hover:text-slate-900 dark:hover:text-white"
                    title="پیشنهاد برای عنوان"
                  >
                    <Type className="h-3.5 w-3.5" />
                  </button>
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  {s.source_count} رسانه · {s.article_count} مقاله
                  {s.state_pct > 0 && <span className="mr-2 text-red-500">· حکومتی {s.state_pct}٪</span>}
                  {s.independent_pct > 0 && <span className="mr-2 text-emerald-600">· مستقل {s.independent_pct}٪</span>}
                  {s.diaspora_pct > 0 && <span className="mr-2 text-blue-600">· برون‌مرزی {s.diaspora_pct}٪</span>}
                </p>
              </div>

              {/* Quick action buttons */}
              <div className="flex md:flex-col gap-1.5 shrink-0">
                <button
                  onClick={() =>
                    openModal({
                      targetType: "story_summary",
                      targetId: s.id,
                      defaultIssueType: "bad_summary",
                      contextLabel: s.title_fa,
                    })
                  }
                  className="flex items-center gap-1 px-2 py-1.5 text-[10px] border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-500"
                  title="پیشنهاد برای خلاصه"
                >
                  <FileText className="h-3 w-3" />
                  خلاصه
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
                  className="flex items-center gap-1 px-2 py-1.5 text-[10px] border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-500"
                  title="مقاله‌های این موضوع به هم نامربوط هستند"
                >
                  <Edit2 className="h-3 w-3" />
                  دسته‌بندی
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
                  className="flex items-center gap-1 px-2 py-1.5 text-[10px] border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-500"
                  title="سایر پیشنهادها"
                >
                  سایر
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* General feedback at the bottom */}
      <div className="mt-8 p-4 border border-slate-200 dark:border-slate-800 text-center">
        <p className="text-xs text-slate-500 mb-3">
          پیشنهاد کلی دیگری دارید که به هیچ خبر خاصی مربوط نیست؟
        </p>
        <button
          onClick={() =>
            openModal({
              targetType: "other",
              defaultIssueType: "other",
              contextLabel: "پیشنهاد کلی",
            })
          }
          className="px-4 py-2 text-xs font-bold border border-slate-900 dark:border-white text-slate-900 dark:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          ارسال پیشنهاد کلی
        </button>
      </div>

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
