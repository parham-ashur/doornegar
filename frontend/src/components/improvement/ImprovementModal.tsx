"use client";

import { useEffect, useState } from "react";
import { X, Send } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "source_dimension" | "layout" | "homepage" | "other";

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
    title: "بازخورد درباره دسته‌بندی خبر",
    description: "مقاله‌های این خبر به هم مرتبط نیستند، یا مقاله‌ای جا مانده است؟",
    issueOptions: [
      { value: "wrong_clustering", label: "مقاله‌ها به هم مرتبط نیستند" },
      { value: "other", label: "سایر" },
    ],
    showCurrentValue: false,
    showSuggestedValue: false,
    suggestedLabel: "",
    suggestedPlaceholder: "",
    reasonLabel: "توضیح",
    reasonPlaceholder: "کدام مقاله‌ها نباید در این خبر باشند، یا کدام مقاله‌ها باید اضافه شوند؟",
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
}: Props) {
  const schema = SCHEMAS[targetType] || SCHEMAS.other;
  const [issueType, setIssueType] = useState<IssueType>(defaultIssueType);
  const [suggestedValue, setSuggestedValue] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  // Reset state when the modal opens with a new target
  useEffect(() => {
    if (open) {
      setIssueType(defaultIssueType);
      setSuggestedValue("");
      setReason("");
      setSuccess(false);
    }
  }, [open, defaultIssueType, targetType]);

  if (!open) return null;

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
        }),
      });
      if (res.ok) {
        setSuccess(true);
        setTimeout(() => {
          setSuccess(false);
          setSuggestedValue("");
          setReason("");
          onClose();
        }, 1500);
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
            <div className="py-8 text-center">
              <p className="text-emerald-600 dark:text-emerald-400 font-bold">
                متشکریم. پیشنهاد شما ثبت شد.
              </p>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
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
