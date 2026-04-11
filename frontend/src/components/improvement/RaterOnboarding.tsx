"use client";

import { useEffect, useState } from "react";
import { X, Sparkles, ChevronDown, ChevronUp, Clock } from "lucide-react";

const STORAGE_KEY = "doornegar_rater_onboarded";
const HISTORY_KEY = "doornegar_my_feedback";

interface HistoryItem {
  id: string;
  target_type: string;
  target_id: string | null;
  issue_type: string;
  reason: string;
  context_label: string;
  created_at: string;
}

const TARGET_LABELS: Record<string, string> = {
  story: "موضوع",
  story_title: "عنوان",
  story_image: "تصویر",
  story_summary: "خلاصه",
  article: "مقاله",
  source: "رسانه",
  source_dimension: "ابعاد رسانه‌ای",
  layout: "چیدمان",
  homepage: "صفحه اصلی",
  other: "سایر",
};

export default function RaterOnboarding() {
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // Show onboarding modal if not seen before
    if (!localStorage.getItem(STORAGE_KEY)) {
      // Small delay so it doesn't block the initial render
      setTimeout(() => setShowOnboarding(true), 500);
    }
    // Load history
    try {
      const raw = localStorage.getItem(HISTORY_KEY) || "[]";
      setHistory(JSON.parse(raw));
    } catch {}
  }, []);

  // Reload history when modal closes (so new submissions appear)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleStorage = () => {
      try {
        setHistory(JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"));
      } catch {}
    };
    window.addEventListener("storage", handleStorage);
    // Also poll every 2 seconds in case same-tab localStorage changes
    const interval = setInterval(handleStorage, 2000);
    return () => {
      window.removeEventListener("storage", handleStorage);
      clearInterval(interval);
    };
  }, []);

  const dismissOnboarding = () => {
    setShowOnboarding(false);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, "1");
    }
  };

  function formatRelative(iso: string): string {
    try {
      const d = new Date(iso);
      const diffMs = Date.now() - d.getTime();
      const mins = Math.floor(diffMs / 60000);
      if (mins < 1) return "همین الان";
      if (mins < 60) return `${mins} دقیقه پیش`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `${hours} ساعت پیش`;
      const days = Math.floor(hours / 24);
      return `${days} روز پیش`;
    } catch {
      return iso;
    }
  }

  return (
    <>
      {/* Onboarding modal */}
      {showOnboarding && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          onClick={dismissOnboarding}
          dir="rtl"
        >
          <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm" />
          <div
            className="relative w-full max-w-lg bg-white dark:bg-[#0a0e1a] border border-slate-200 dark:border-slate-800 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={dismissOnboarding}
              className="absolute top-3 left-3 p-2 text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
            <div className="px-8 py-10 md:px-10 md:py-12">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                <h2 className="text-2xl font-black text-slate-900 dark:text-white">
                  به حالت بازخورد خوش آمدید
                </h2>
              </div>
              <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400 mb-6">
                این صفحه شبیه صفحه اصلی است، اما کنار هر عنصر دکمه‌های کوچکی برای
                ارسال پیشنهاد قرار گرفته. می‌توانید روی عنوان، تصویر، خلاصه یا
                دسته‌بندی هر خبر کلیک کنید و نظر خود را به ما بگویید.
              </p>

              <div className="space-y-3 mb-6">
                <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wide">
                  مثال‌هایی از پیشنهادهای مفید
                </h3>
                <div className="border-r-2 border-blue-300 dark:border-blue-800 pr-3">
                  <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300">تصویر</p>
                  <p className="text-[12px] text-slate-500 dark:text-slate-400 leading-6">
                    «این تصویر به موضوع خبر ربطی ندارد» یا «کیفیت تصویر پایین است»
                  </p>
                </div>
                <div className="border-r-2 border-emerald-300 dark:border-emerald-800 pr-3">
                  <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300">عنوان</p>
                  <p className="text-[12px] text-slate-500 dark:text-slate-400 leading-6">
                    «عنوان گمراه‌کننده است» و پیشنهاد یک عنوان جایگزین
                  </p>
                </div>
                <div className="border-r-2 border-amber-300 dark:border-amber-800 pr-3">
                  <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300">دسته‌بندی</p>
                  <p className="text-[12px] text-slate-500 dark:text-slate-400 leading-6">
                    «این مقاله به این موضوع ربط ندارد، جدا شود»
                  </p>
                </div>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 mb-6">
                <p className="text-[11px] leading-6 text-slate-600 dark:text-slate-400">
                  ✓ پیشنهاد شما <strong>ناشناس</strong> است و نیازی به ورود یا نام نیست.
                  <br />
                  ✓ پس از ارسال، ۱۰ ثانیه فرصت دارید نظر خود را بازگردانید.
                  <br />
                  ✓ همه پیشنهادها در فهرست کارهای تیم ذخیره می‌شوند.
                </p>
              </div>

              <button
                onClick={dismissOnboarding}
                className="w-full py-2.5 text-xs font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200"
              >
                شروع می‌کنم
              </button>
            </div>
          </div>
        </div>
      )}

      {/* History panel — collapsible, shown below the banner */}
      {history.length > 0 && (
        <div dir="rtl" className="mx-auto max-w-7xl px-4 md:px-6 lg:px-8 py-3">
          <div className="border border-slate-200 dark:border-slate-800">
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-xs hover:bg-slate-50 dark:hover:bg-slate-900/50"
            >
              <div className="flex items-center gap-2">
                <Clock className="h-3.5 w-3.5 text-slate-400" />
                <span className="font-bold text-slate-700 dark:text-slate-300">
                  پیشنهادهای شما
                </span>
                <span className="text-slate-400">({history.length})</span>
              </div>
              {historyOpen ? (
                <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
              )}
            </button>
            {historyOpen && (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/50 max-h-80 overflow-y-auto">
                {history.map((item) => (
                  <div key={item.id} className="px-4 py-2.5 text-[11px]">
                    <div className="flex items-start justify-between gap-3 mb-0.5">
                      <span className="font-bold text-slate-700 dark:text-slate-300">
                        {TARGET_LABELS[item.target_type] || item.target_type}
                      </span>
                      <span className="text-slate-400 text-[10px] shrink-0">
                        {formatRelative(item.created_at)}
                      </span>
                    </div>
                    {item.context_label && (
                      <p className="text-slate-500 dark:text-slate-400 line-clamp-1 mb-0.5">
                        {item.context_label}
                      </p>
                    )}
                    {item.reason && (
                      <p className="text-slate-600 dark:text-slate-300 line-clamp-2">
                        {item.reason}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
