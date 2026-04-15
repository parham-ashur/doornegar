"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SuggestionType = "media" | "telegram" | "x_twitter" | "youtube" | "instagram" | "website" | "other";
type Category = "state" | "semi_state" | "independent" | "diaspora" | "not_sure";

interface TrackedSource {
  name_fa: string;
  name_en: string;
  slug: string;
  website_url: string;
  state_alignment: string;
  language: string;
}

interface TrackedChannel {
  username: string;
  title: string;
}

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  state: { label: "محافظه‌کار", color: "text-red-600 dark:text-red-400 border-red-200 dark:border-red-900/50" },
  semi_state: { label: "نیمه‌محافظه‌کار", color: "text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-900/50" },
  independent: { label: "مستقل", color: "text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-900/50" },
  diaspora: { label: "اپوزیسیون", color: "text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-900/50" },
};

export default function SuggestPage() {
  const [sources, setSources] = useState<TrackedSource[]>([]);
  const [channels, setChannels] = useState<TrackedChannel[]>([]);
  const [trackedOpen, setTrackedOpen] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/v1/sources`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.sources) setSources(d.sources); })
      .catch(() => {});
    fetch(`${API}/api/v1/social/channels`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (Array.isArray(d)) setChannels(d); })
      .catch(() => {});
  }, []);

  // Group sources by state_alignment
  const grouped: Record<string, TrackedSource[]> = {};
  for (const s of sources) {
    const key = s.state_alignment || "other";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(s);
  }
  const groupOrder = ["state", "semi_state", "independent", "diaspora"];

  const [form, setForm] = useState({
    suggestion_type: "media" as SuggestionType,
    name: "",
    url: "",
    language: "fa",
    suggested_category: "not_sure" as Category,
    description: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ type: "success" | "error" | "duplicate"; message: string } | null>(null);

  const update = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);

    try {
      const payload = {
        ...form,
        description: form.description || null,
      };
      const res = await fetch(`${API}/api/v1/suggestions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (res.status === 429) {
        setResult({
          type: "error",
          message: "تعداد پیشنهادهای شما در این ساعت به حد مجاز رسیده است. لطفاً بعداً دوباره تلاش کنید.",
        });
      } else if (!res.ok) {
        setResult({
          type: "error",
          message: "ارسال پیشنهاد ناموفق بود. لطفاً دوباره تلاش کنید.",
        });
      } else if (data.status === "duplicate") {
        setResult({ type: "duplicate", message: data.message });
      } else {
        setResult({ type: "success", message: data.message });
        // Reset form on success
        setForm({
          suggestion_type: "media",
          name: "",
          url: "",
          language: "fa",
          suggested_category: "not_sure",
          description: "",
        });
      }
    } catch (err) {
      setResult({ type: "error", message: "خطای ارتباطی. اتصال اینترنت را بررسی کنید." });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div dir="rtl" className="mx-auto max-w-2xl px-4 py-10 md:py-16">
      <h1 className="text-[26px] md:text-[32px] font-black leading-snug text-slate-900 dark:text-white mb-2">
        پیشنهاد منبع جدید
      </h1>
      <p className="text-[14px] text-slate-500 dark:text-slate-400 leading-7 mb-6">
        اگر رسانه، کانال تلگرام، حساب اکس (توییتر) یا منبع دیگری می‌شناسید که
        باید پوشش داده شود، فرم زیر را پر کنید. همه پیشنهادها توسط تیم
        بررسی می‌شوند و در صورت تأیید، به منابع افزوده خواهند شد.
      </p>

      {/* Currently tracked sources — collapsible */}
      {(sources.length > 0 || channels.length > 0) && (
        <div className="mb-8 border border-slate-200 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setTrackedOpen(!trackedOpen)}
            className="w-full flex items-center justify-between px-4 py-3 text-[13px] hover:bg-slate-50 dark:hover:bg-slate-900/50"
          >
            <span className="font-bold text-slate-900 dark:text-white">
              منابعی که در حال حاضر پوشش می‌دهیم
              <span className="font-normal text-slate-400 mr-2">
                ({sources.length} رسانه · {channels.length} کانال تلگرام)
              </span>
            </span>
            {trackedOpen ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
          </button>

          {trackedOpen && (
            <div className="border-t border-slate-200 dark:border-slate-800 px-4 py-4 space-y-5">
              <p className="text-[11px] leading-6 text-slate-500 dark:text-slate-400">
                قبل از پیشنهاد، بررسی کنید که منبع موردنظر در این فهرست نباشد.
              </p>

              {/* Media sources — flat list, no category grouping */}
              {sources.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300">
                      رسانه‌ها
                    </span>
                    <span className="text-[10px] text-slate-400">({sources.length})</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {sources.map((s) => (
                      <a
                        key={s.slug}
                        href={s.website_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={s.name_en}
                        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 text-slate-700 dark:text-slate-300"
                      >
                        {s.name_fa || s.name_en}
                        <ExternalLink className="h-2.5 w-2.5 opacity-50" />
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* Telegram channels */}
              {channels.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300">
                      کانال‌های تلگرام
                    </span>
                    <span className="text-[10px] text-slate-400">({channels.length})</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {channels.map((c) => (
                      <a
                        key={c.username}
                        href={`https://t.me/${c.username.replace(/^@/, "")}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        dir="ltr"
                        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 text-slate-700 dark:text-slate-300"
                      >
                        @{c.username.replace(/^@/, "")}
                        <ExternalLink className="h-2.5 w-2.5 opacity-50" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {result && (
        <div
          className={`mb-6 p-4 border flex items-start gap-3 ${
            result.type === "success"
              ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-200"
              : result.type === "duplicate"
              ? "border-amber-500 bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200"
              : "border-red-500 bg-red-50 dark:bg-red-950/30 text-red-900 dark:text-red-200"
          }`}
        >
          {result.type === "success" ? (
            <CheckCircle2 className="h-5 w-5 shrink-0 mt-0.5" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          )}
          <p className="text-[13px] leading-6">{result.message}</p>
        </div>
      )}

      <form onSubmit={submit} className="space-y-5">
        {/* Type */}
        <div>
          <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
            نوع منبع <span className="text-red-500">*</span>
          </label>
          <select
            value={form.suggestion_type}
            onChange={(e) => update("suggestion_type", e.target.value as SuggestionType)}
            className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
          >
            <option value="media">رسانه (سایت خبری)</option>
            <option value="telegram">کانال تلگرام</option>
            <option value="x_twitter">حساب اکس / توییتر</option>
            <option value="youtube">کانال یوتیوب</option>
            <option value="instagram">حساب اینستاگرام</option>
            <option value="website">وب‌سایت دیگر</option>
            <option value="other">سایر</option>
          </select>
        </div>

        {/* Name */}
        <div>
          <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
            نام منبع <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            required
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            placeholder="مثلاً: ایران‌وایر، بی‌بی‌سی فارسی، خبرگزاری فارس"
            className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
          />
        </div>

        {/* URL */}
        <div>
          <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
            آدرس یا نام کاربری <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            required
            dir="ltr"
            value={form.url}
            onChange={(e) => update("url", e.target.value)}
            placeholder="https://example.com یا @channelname"
            className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white text-left"
          />
        </div>

        {/* Language + Category in two columns */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
              زبان
            </label>
            <select
              value={form.language}
              onChange={(e) => update("language", e.target.value)}
              className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
            >
              <option value="fa">فارسی</option>
              <option value="en">انگلیسی</option>
              <option value="ar">عربی</option>
              <option value="ku">کردی</option>
              <option value="az">آذری</option>
              <option value="fr">فرانسوی</option>
              <option value="other">سایر</option>
            </select>
          </div>
          <div>
            <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
              دسته‌بندی پیشنهادی
            </label>
            <select
              value={form.suggested_category}
              onChange={(e) => update("suggested_category", e.target.value as Category)}
              className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
            >
              <option value="not_sure">نمی‌دانم</option>
              <option value="state">محافظه‌کار</option>
              <option value="semi_state">نیمه‌محافظه‌کار</option>
              <option value="independent">مستقل</option>
              <option value="diaspora">اپوزیسیون</option>
            </select>
          </div>
        </div>

        {/* Description */}
        <div>
          <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
            چرا این منبع مهم است؟
          </label>
          <textarea
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            placeholder="یک توضیح کوتاه درباره این منبع و اهمیت آن"
            rows={3}
            className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
          />
        </div>

        {/* Submit */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={submitting || !form.name || !form.url}
            className="px-6 py-2.5 text-[13px] font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "در حال ارسال..." : "ارسال پیشنهاد"}
          </button>
        </div>
      </form>

      {/* Privacy note */}
      <div className="mt-12 pt-6 border-t border-slate-200 dark:border-slate-800">
        <p className="text-[11px] leading-6 text-slate-400 dark:text-slate-500">
          پیشنهادها به‌صورت ناشناس ارسال می‌شوند و توسط تیم دستی بررسی می‌شوند.
          هیچ اطلاعات شخصی جمع‌آوری یا ذخیره نمی‌شود.
        </p>
      </div>
    </div>
  );
}
