"use client";

import { useEffect, useState } from "react";
import { X, Send } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "source_dimension" | "layout" | "homepage" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request"
  | "priority_higher" | "priority_lower" | "merge_stories" | "other";

interface Props {
  open: boolean;
  onClose: () => void;
  targetType: TargetType;
  targetId?: string;
  targetUrl?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
  /** For image feedback — show the actual image inside the modal */
  imageUrl?: string | null;
}

// Quick-preset reasons by target type (tap to fill the reason field)
const REASON_PRESETS: Partial<Record<TargetType, string[]>> = {
  story_image: [
    "کیفیت پایین",
    "تصویر نامرتبط",
    "تصویر اشتباه",
    "بهتر است بدون تصویر باشد",
    "تصویر بی‌ربط به موضوع",
  ],
  story_title: [
    "عنوان گمراه‌کننده",
    "عنوان خیلی طولانی",
    "عنوان ناقص",
    "غلط املایی",
  ],
  story_summary: [
    "خلاصه ناقص",
    "اشتباه واقعی در خلاصه",
    "نیاز به بازنویسی",
    "طرف یکی را پنهان کرده",
  ],
  story: [
    "مقاله‌های نامرتبط در یک خبر",
    "خبر باید تقسیم شود",
    "مقاله‌ای جا مانده",
  ],
};

// ─── Form schemas — context-aware field sets per target type ─────
interface FormSchema {
  title: string;
  description: string;
  issueOptions: { value: IssueType; label: string }[];
  showCurrentValue: boolean;
  showSuggestedValue: boolean;
  suggestedLabel: string;
  suggestedPlaceholder: string;
  reasonLabel: string;
  reasonPlaceholder: string;
}

const SCHEMAS: Record<TargetType, FormSchema> = {
  story_title: {
    title: "بازخورد درباره عنوان خبر",
    description: "عنوان این خبر نادرست، گمراه‌کننده یا قابل بهبود است؟",
    issueOptions: [
      { value: "wrong_title", label: "عنوان نادرست یا گمراه‌کننده" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: true,
    showSuggestedValue: true,
    suggestedLabel: "عنوان پیشنهادی",
    suggestedPlaceholder: "عنوانی که به‌نظر شما درست‌تر است",
    reasonLabel: "توضیح",
    reasonPlaceholder: "چرا این عنوان نامناسب است؟",
  },
  story_image: {
    title: "بازخورد درباره تصویر خبر",
    description: "تصویر این خبر نامناسب، بی‌کیفیت یا نامرتبط است؟",
    issueOptions: [
      { value: "bad_image", label: "تصویر نامناسب" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: false,
    suggestedLabel: "",
    suggestedPlaceholder: "",
    reasonLabel: "توضیح",
    reasonPlaceholder: "چه مشکلی با این تصویر دارد؟ مثلاً: غیر مرتبط، کیفیت پایین، ترجیحاً بدون تصویر، ...",
  },
  story_summary: {
    title: "بازخورد درباره خلاصه / تحلیل",
    description: "خلاصه این خبر یا تحلیل آن نیاز به اصلاح دارد؟",
    issueOptions: [
      { value: "bad_summary", label: "خلاصه نادرست یا ناقص" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: true,
    showSuggestedValue: true,
    suggestedLabel: "پیشنهاد شما",
    suggestedPlaceholder: "خلاصه یا اصلاح پیشنهادی",
    reasonLabel: "توضیح",
    reasonPlaceholder: "چه چیزی اشتباه یا ناقص است؟",
  },
  story: {
    title: "بازخورد درباره این موضوع",
    description: "مقاله‌ها نامرتبط هستند، یا این موضوع باید با موضوع دیگری ادغام شود؟",
    issueOptions: [
      { value: "wrong_clustering", label: "مقاله‌ها به هم مرتبط نیستند" },
      { value: "merge_stories", label: "ادغام با موضوع دیگر" },
      { value: "priority_higher", label: "این موضوع مهم‌تر است (بالاتر نمایش بده)" },
      { value: "priority_lower", label: "این موضوع کم‌اهمیت‌تر است" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: true,
    suggestedLabel: "شناسه موضوع مقصد (برای ادغام)",
    suggestedPlaceholder: "اگر ادغام پیشنهاد می‌دهید، عنوان یا شناسه موضوع دوم را بنویسید",
    reasonLabel: "توضیح",
    reasonPlaceholder: "توضیح بیشتر: چرا باید ادغام شود، یا چرا اولویت باید تغییر کند؟",
  },
  article: {
    title: "بازخورد درباره یک مقاله",
    description: "یک مقاله خاص در این خبر مشکل دارد؟",
    issueOptions: [
      { value: "wrong_clustering", label: "این مقاله به این خبر ربط ندارد" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: false,
    suggestedLabel: "",
    suggestedPlaceholder: "",
    reasonLabel: "توضیح",
    reasonPlaceholder: "کدام مقاله و چرا مشکل دارد؟",
  },
  source: {
    title: "بازخورد درباره دسته‌بندی رسانه",
    description: "یک رسانه در دسته‌بندی نادرست قرار گرفته است؟",
    issueOptions: [
      { value: "wrong_source_class", label: "دسته‌بندی رسانه نادرست است" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: true,
    suggestedLabel: "دسته‌بندی پیشنهادی",
    suggestedPlaceholder: "مثلاً: حکومتی، مستقل، برون‌مرزی",
    reasonLabel: "توضیح",
    reasonPlaceholder: "کدام رسانه و چرا؟",
  },
  source_dimension: {
    title: "بازخورد درباره ابعاد رسانه‌ای",
    description: "امتیاز یک رسانه در یکی از ابعاد نیاز به بازنگری دارد؟",
    issueOptions: [
      { value: "other", label: "امتیاز ابعاد نیاز به بازنگری" },
    ],
    showCurrentValue: false,
    showSuggestedValue: true,
    suggestedLabel: "پیشنهاد شما",
    suggestedPlaceholder: "کدام رسانه، کدام بُعد، چه امتیاز پیشنهادی (۱ تا ۵)",
    reasonLabel: "توضیح",
    reasonPlaceholder: "چرا این امتیاز نیاز به تغییر دارد؟",
  },
  layout: {
    title: "بازخورد درباره چیدمان",
    description: "مشکلی در نحوه نمایش یا طراحی این صفحه می‌بینید؟",
    issueOptions: [
      { value: "layout_issue", label: "مشکل چیدمان یا طراحی" },
      { value: "bug", label: "باگ / خطا" },
      { value: "feature_request", label: "پیشنهاد ویژگی جدید" },
    ],
    showCurrentValue: false,
    showSuggestedValue: false,
    suggestedLabel: "",
    suggestedPlaceholder: "",
    reasonLabel: "توضیح",
    reasonPlaceholder: "چه چیزی بهتر است تغییر کند؟",
  },
  homepage: {
    title: "بازخورد درباره صفحه اصلی",
    description: "پیشنهادی درباره ساختار یا چیدمان صفحه اصلی دارید؟",
    issueOptions: [
      { value: "layout_issue", label: "چیدمان / طراحی" },
      { value: "feature_request", label: "پیشنهاد ویژگی جدید" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: false,
    suggestedLabel: "",
    suggestedPlaceholder: "",
    reasonLabel: "توضیح",
    reasonPlaceholder: "چه چیزی در صفحه اصلی می‌توانست بهتر باشد؟",
  },
  other: {
    title: "پیشنهاد کلی",
    description: "هر نظر یا پیشنهاد دیگر",
    issueOptions: [
      { value: "feature_request", label: "پیشنهاد ویژگی جدید" },
      { value: "bug", label: "باگ / خطا" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: true,
    suggestedLabel: "پیشنهاد (اختیاری)",
    suggestedPlaceholder: "پیشنهاد مشخص شما",
    reasonLabel: "توضیح",
    reasonPlaceholder: "پیام خود را اینجا بنویسید",
  },
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
  imageUrl,
}: Props) {
  const schema = SCHEMAS[targetType] || SCHEMAS.other;
  const [issueType, setIssueType] = useState<IssueType>(defaultIssueType);
  const [suggestedValue, setSuggestedValue] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [lastSubmittedId, setLastSubmittedId] = useState<string | null>(null);
  const [similarCount, setSimilarCount] = useState(0);
  const [undoCountdown, setUndoCountdown] = useState(0);

  // Reset state when the modal opens with a new target
  useEffect(() => {
    if (open) {
      setIssueType(defaultIssueType);
      setSuggestedValue("");
      setReason("");
      setSuccess(false);
      setLastSubmittedId(null);
      setSimilarCount(0);
      setUndoCountdown(0);
    }
  }, [open, defaultIssueType, targetType]);

  // Undo countdown tick
  useEffect(() => {
    if (undoCountdown <= 0) return;
    const t = setTimeout(() => setUndoCountdown((c) => Math.max(0, c - 1)), 1000);
    return () => clearTimeout(t);
  }, [undoCountdown]);

  if (!open) return null;

  const undo = async () => {
    if (!lastSubmittedId) return;
    try {
      await fetch(`${API}/api/v1/improvements/self/${lastSubmittedId}`, { method: "DELETE" });
      // Remove from local history
      if (typeof window !== "undefined") {
        try {
          const raw = localStorage.getItem("doornegar_my_feedback") || "[]";
          const arr = JSON.parse(raw) as { id: string }[];
          const next = arr.filter((x) => x.id !== lastSubmittedId);
          localStorage.setItem("doornegar_my_feedback", JSON.stringify(next));
        } catch {}
      }
      setLastSubmittedId(null);
      setUndoCountdown(0);
      setSuccess(false);
      onClose();
    } catch {
      // Ignore errors — deletion may have timed out
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim() && !suggestedValue.trim()) {
      alert("لطفاً حداقل توضیح یا پیشنهاد خود را بنویسید");
      return;
    }
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
          // Auto-capture device context so admins can reproduce mobile-specific bugs
          device_info: typeof window !== "undefined"
            ? `${window.innerWidth <= 768 ? "mobile" : "desktop"} ${window.innerWidth}×${window.innerHeight} ${navigator.userAgent.slice(0, 150)}`
            : null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSuccess(true);
        setLastSubmittedId(data.id);
        setSimilarCount(data.similar_count || 0);
        setUndoCountdown(10);
        // Save to local history
        if (typeof window !== "undefined") {
          try {
            const raw = localStorage.getItem("doornegar_my_feedback") || "[]";
            const arr = JSON.parse(raw) as unknown[];
            arr.unshift({
              id: data.id,
              target_type: targetType,
              target_id: targetId || null,
              issue_type: issueType,
              reason: reason || suggestedValue || "",
              context_label: contextLabel || "",
              created_at: new Date().toISOString(),
            });
            // Keep only last 50
            localStorage.setItem("doornegar_my_feedback", JSON.stringify(arr.slice(0, 50)));
          } catch {}
        }
      } else {
        alert("ارسال ناموفق بود. دوباره تلاش کنید.");
      }
    } catch {
      alert("خطای ارتباطی");
    }
    setSubmitting(false);
  };

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
          className="absolute top-3 left-3 p-2 text-slate-400 hover:text-slate-900 dark:hover:text-white z-10"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="px-6 py-6 md:px-8 md:py-8">
          <h2 className="text-xl font-black text-slate-900 dark:text-white mb-1 pr-8">
            {schema.title}
          </h2>
          <p className="text-xs text-slate-500 mb-1">{schema.description}</p>
          {contextLabel && (
            <p className="text-xs text-slate-500 mb-6 line-clamp-2 pt-1 border-t border-slate-100 dark:border-slate-800/50 mt-2">
              درباره: <span className="font-medium text-slate-700 dark:text-slate-300">{contextLabel}</span>
            </p>
          )}

          {success ? (
            <div className="py-8 text-center space-y-4">
              <p className="text-emerald-600 dark:text-emerald-400 font-bold">
                متشکریم. پیشنهاد شما ثبت شد.
              </p>
              {similarCount > 0 && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {similarCount === 1
                    ? "۱ نفر دیگر هم این مورد را گزارش داده است"
                    : `${similarCount} نفر دیگر هم این مورد را گزارش داده‌اند`}
                </p>
              )}
              {undoCountdown > 0 && (
                <button
                  type="button"
                  onClick={undo}
                  className="text-xs text-red-500 hover:text-red-600 underline"
                >
                  بازگرداندن ({undoCountdown})
                </button>
              )}
              <div>
                <button
                  type="button"
                  onClick={onClose}
                  className="text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white"
                >
                  بستن
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              {/* Image preview for image feedback */}
              {targetType === "story_image" && imageUrl && (
                <div>
                  <p className="text-[10px] text-slate-400 mb-1.5">تصویر مورد نظر</p>
                  <div className="aspect-video w-full max-w-xs mx-auto overflow-hidden bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
                    <img
                      src={imageUrl.startsWith("/images/") ? `${API}${imageUrl}` : imageUrl}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  </div>
                </div>
              )}

              {/* Issue type — only if more than one option */}
              {schema.issueOptions.length > 1 && (
                <div>
                  <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                    نوع مشکل
                  </label>
                  <select
                    value={issueType}
                    onChange={(e) => setIssueType(e.target.value as IssueType)}
                    className="w-full px-3 py-2 text-xs border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
                  >
                    {schema.issueOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Current value */}
              {schema.showCurrentValue && currentValue && (
                <div className="p-2 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800">
                  <p className="text-[10px] text-slate-400 mb-1">مقدار فعلی</p>
                  <p className="text-xs text-slate-700 dark:text-slate-300 line-clamp-4">
                    {currentValue}
                  </p>
                </div>
              )}

              {/* Suggested value */}
              {schema.showSuggestedValue && (
                <div>
                  <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                    {schema.suggestedLabel}
                  </label>
                  <textarea
                    value={suggestedValue}
                    onChange={(e) => setSuggestedValue(e.target.value)}
                    placeholder={schema.suggestedPlaceholder}
                    rows={3}
                    className="w-full px-3 py-2 text-xs border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
                  />
                </div>
              )}

              {/* Reason */}
              <div>
                <label className="block text-xs font-bold text-slate-900 dark:text-white mb-1.5">
                  {schema.reasonLabel}
                </label>
                {/* Quick-preset chips */}
                {REASON_PRESETS[targetType] && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {REASON_PRESETS[targetType]!.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setReason(preset)}
                        className="px-2 py-1 text-[11px] border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-900 dark:hover:border-white hover:bg-slate-50 dark:hover:bg-slate-800"
                      >
                        {preset}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={schema.reasonPlaceholder}
                  rows={3}
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
