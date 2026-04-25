"use client";

import { useState } from "react";
import { MessageSquare, X } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Props {
  pagePath?: string;
  storyId?: string;
}

/**
 * Small floating button in the bottom-left (RTL) corner of any page.
 * Any visitor can send a short comment about the page. Posts to the
 * existing improvements API so entries show up in the admin's
 * "Improvement Feedback" queue.
 *
 * Intentionally minimal: one text field, one submit. No name/email
 * required — per Parham's preference that the submit surface stay
 * low-friction.
 */
export default function PublicFeedbackButton({ pagePath, storyId }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const submit = async () => {
    if (!text.trim() || status === "sending") return;
    setStatus("sending");
    try {
      const { antiSpamHeaders } = await import("@/lib/antiSpamToken");
      const res = await fetch(`${API}/api/v1/improvements`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...antiSpamHeaders() },
        body: JSON.stringify({
          target_type: storyId ? "story" : "other",
          target_id: storyId || null,
          target_url:
            pagePath ||
            (typeof window !== "undefined" ? window.location.href : null),
          issue_type: "other",
          reason: text.trim(),
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setStatus("sent");
      setText("");
      setTimeout(() => {
        setOpen(false);
        setStatus("idle");
      }, 1800);
    } catch {
      setStatus("error");
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="ارسال بازخورد"
        className="fixed bottom-5 left-5 z-40 flex items-center gap-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-3 py-2 text-[13px] font-bold shadow-lg hover:bg-slate-700 dark:hover:bg-slate-200 transition-colors"
      >
        <MessageSquare className="h-4 w-4" />
        بازخورد
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-4 bg-slate-900/60"
          onClick={() => setOpen(false)}
          dir="rtl"
        >
          <div
            className="w-full max-w-md bg-white dark:bg-[#0a0e1a] border border-slate-200 dark:border-slate-800 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800">
              <h3 className="text-[14px] font-black text-slate-900 dark:text-white">
                بازخورد شما
              </h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="بستن"
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400">
                هر چیزی دربارهٔ این صفحه به نظرتان می‌رسد بنویسید — خطا، پیشنهاد،
                انتقاد. ما می‌خوانیم.
              </p>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                placeholder="بازخورد خود را اینجا بنویسید…"
                className="w-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-[13px] px-3 py-2 resize-none"
                disabled={status === "sending" || status === "sent"}
              />
              {status === "sent" && (
                <p className="text-[13px] text-emerald-600 dark:text-emerald-400">
                  ✓ بازخورد شما ثبت شد. ممنون.
                </p>
              )}
              {status === "error" && (
                <p className="text-[13px] text-rose-600 dark:text-rose-400">
                  خطا در ارسال. دوباره تلاش کنید.
                </p>
              )}
              <div className="flex items-center justify-between">
                <p className="text-[11px] text-slate-400 dark:text-slate-500">
                  بدون نیاز به نام یا ایمیل.
                </p>
                <button
                  type="button"
                  onClick={submit}
                  disabled={!text.trim() || status === "sending" || status === "sent"}
                  className="text-[13px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
                >
                  {status === "sending" ? "…" : "ارسال"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
