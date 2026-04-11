"use client";

import { useState } from "react";
import { X, Send } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "layout" | "homepage" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request" | "other";

interface Props {
  open: boolean;
  onClose: () => void;
  targetType: TargetType;
  targetId?: string;
  targetUrl?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
}

const ISSUE_LABELS: Record<IssueType, string> = {
  wrong_title: "عنوان نادرست",
  bad_image: "تصویر نامناسب",
  wrong_clustering: "دسته‌بندی اشتباه مقاله‌ها",
  bad_summary: "خلاصه نادرست یا ناقص",
  wrong_source_class: "دسته‌بندی اشتباه رسانه",
  layout_issue: "مشکل چیدمان",
  bug: "باگ یا خطا",
  feature_request: "پیشنهاد ویژگی جدید",
  other: "سایر",
};

export default function ImprovementModal({
  open,
  onClose,
  targetType,
  targetId,
  targetUrl,
  currentValue,
  defaultIssueType = "other",
  contextLabel,
}: Props) {
  const [issueType, setIssueType] = useState<IssueType>(defaultIssueType);
  const [suggestedValue, setSuggestedValue] = useState("");
  const [reason, setReason] = useState("");
  const [raterName, setRaterName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/v1/improvements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: targetType,
          target_id: targetId || null,
          target_url: targetUrl || (typeof window !== "undefined" ? window.location.href : null),
          issue_type: issueType,
          current_value: currentValue || null,
          suggested_value: suggestedValue || null,
          reason: reason || null,
          rater_name: raterName || null,
        }),
      });
      if (res.ok) {
        setSuccess(true);
        // Remember the rater name for next submissions
        if (raterName && typeof window !== "undefined") {
          localStorage.setItem("doornegar_rater_name", raterName);
        }
        setTimeout(() => {
          setSuccess(false);
          setSuggestedValue("");
          setReason("");
          onClose();
        }, 1500);
      } else {
        alert("ارسال ناموفق بود");
      }
    } catch {
      alert("خطای ارتباطی");
    }
    setSubmitting(false);
  };

  // Load saved rater name
  if (!raterName && typeof window !== "undefined") {
    const saved = localStorage.getItem("doornegar_rater_name");
    if (saved) setRaterName(saved);
  }

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center p-4"
      onClick={onClose}
      dir="rtl"
    >
      <div className="absolute inset-0 bg-slate-900/70 backdrop-blur-sm" />

      <div
        className="relative w-full max-w-xl bg-white dark:bg-[#0a0e1a] border border-slate-200 dark:border-slate-800 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-3 left-3 p-2 text-slate-400 hover:text-slate-900 dark:hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="px-6 py-6 md:px-8 md:py-8">
          <h2 className="text-xl font-black text-slate-900 dark:text-white mb-1">
            پیشنهاد اصلاح
          </h2>
          {contextLabel && (
            <p className="text-xs text-slate-500 mb-6 line-clamp-2">درباره: {contextLabel}</p>
          )}

          {success ? (
            <div className="py-8 text-center">
              <p className="text-emerald-600 dark:text-emerald-400 font-bold">
                متشکریم. پیشنهاد شما ثبت شد.
              </p>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              {/* Issue type */}
              <div>
                <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                  نوع مشکل
                </label>
                <select
                  value={issueType}
                  onChange={(e) => setIssueType(e.target.value as IssueType)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
                >
                  {Object.entries(ISSUE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>

              {/* Current value preview */}
              {currentValue && (
                <div className="p-2 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800">
                  <p className="text-[10px] text-slate-400 mb-1">مقدار فعلی</p>
                  <p className="text-xs text-slate-700 dark:text-slate-300 line-clamp-3">
                    {currentValue}
                  </p>
                </div>
              )}

              {/* Suggested value */}
              <div>
                <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                  پیشنهاد شما (اختیاری)
                </label>
                <textarea
                  value={suggestedValue}
                  onChange={(e) => setSuggestedValue(e.target.value)}
                  placeholder="مثلاً عنوان درست یا خلاصه پیشنهادی"
                  rows={3}
                  className="w-full px-3 py-2 text-xs border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
                />
              </div>

              {/* Reason */}
              <div>
                <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                  توضیح
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="چرا باید این تغییر انجام شود؟"
                  rows={2}
                  className="w-full px-3 py-2 text-xs border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
                />
              </div>

              {/* Rater name */}
              <div>
                <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                  نام شما (اختیاری)
                </label>
                <input
                  type="text"
                  value={raterName}
                  onChange={(e) => setRaterName(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full flex items-center justify-center gap-2 py-2.5 text-xs font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
                {submitting ? "در حال ارسال..." : "ارسال پیشنهاد"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
