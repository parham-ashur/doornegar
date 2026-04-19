"use client";

import { useState } from "react";
import { Image as ImageIcon, CheckCircle2, AlertCircle, X } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Public-facing "suggest a better image for this story" control. Posts
// to /api/v1/improvements with issue_type=bad_image + suggested_value
// set to the new URL. Admin sees it in the improvement feedback queue
// and can one-click pin via the HITL channel dashboard (or the backend
// pin-image endpoint) if the URL checks out.
export default function ImageSuggestionButton({
  storyId,
  storyTitle,
}: {
  storyId: string;
  storyTitle: string;
}) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const submit = async () => {
    if (!url.trim()) return;
    setSubmitting(true);
    setResult(null);
    try {
      const res = await fetch(`${API}/api/v1/improvements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "story_image",
          target_id: storyId,
          issue_type: "bad_image",
          suggested_value: url.trim(),
          reason: reason.trim() || undefined,
          target_url: typeof window !== "undefined" ? window.location.href : undefined,
        }),
      });
      if (res.ok) {
        setResult({ ok: true, message: "متشکریم — پیشنهاد شما ثبت شد." });
        setUrl("");
        setReason("");
        setTimeout(() => setOpen(false), 1500);
      } else {
        const err = await res.json().catch(() => ({}));
        setResult({ ok: false, message: err.detail || "خطا در ارسال" });
      }
    } catch {
      setResult({ ok: false, message: "خطا در اتصال" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 px-2 py-1 text-[12px] text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 border border-slate-200 dark:border-slate-700 hover:border-blue-400 transition-colors"
        title="پیشنهاد تصویر بهتر برای این خبر"
      >
        <ImageIcon className="h-3.5 w-3.5" />
        پیشنهاد تصویر
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}
        >
          <div
            dir="rtl"
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 max-w-lg w-full p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-[14px] font-black text-slate-900 dark:text-white">
                  پیشنهاد تصویر جدید برای خبر
                </h3>
                <p className="text-[12px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-1">
                  {storyTitle}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-1">
                  لینک تصویر پیشنهادی <span className="text-red-500">*</span>
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://…/image.jpg"
                  dir="ltr"
                  className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 focus:border-blue-500 outline-none"
                />
                <p className="text-[12px] text-slate-400 mt-1">
                  لینک مستقیم تصویر (نه صفحه‌ای که شامل تصویر است).
                </p>
              </div>
              <div>
                <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-1">
                  چرا این تصویر بهتر است؟ (اختیاری)
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={2}
                  placeholder="مثلاً: تصویر فعلی نامرتبط است، یا تصویر پیشنهادی کیفیت بهتری دارد"
                  className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 focus:border-blue-500 outline-none"
                />
              </div>

              {result && (
                <div
                  className={`flex items-center gap-2 text-[13px] ${
                    result.ok
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-red-600 dark:text-red-400"
                  }`}
                >
                  {result.ok ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <AlertCircle className="h-4 w-4" />
                  )}
                  {result.message}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="px-4 py-1.5 text-[13px] text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700"
                >
                  انصراف
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={submitting || !url.trim()}
                  className="px-4 py-1.5 text-[13px] bg-blue-600 text-white disabled:opacity-50"
                >
                  {submitting ? "..." : "ارسال پیشنهاد"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
