"use client";

import { useState } from "react";
import { CheckCircle2, AlertCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SuggestionType = "media" | "telegram" | "x_twitter" | "youtube" | "instagram" | "website" | "other";
type Category = "state" | "semi_state" | "independent" | "diaspora" | "not_sure";

export default function SuggestPage() {
  const [form, setForm] = useState({
    suggestion_type: "media" as SuggestionType,
    name: "",
    url: "",
    language: "fa",
    suggested_category: "not_sure" as Category,
    description: "",
    submitter_name: "",
    submitter_contact: "",
    submitter_notes: "",
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
        submitter_name: form.submitter_name || null,
        submitter_contact: form.submitter_contact || null,
        submitter_notes: form.submitter_notes || null,
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
          submitter_name: "",
          submitter_contact: "",
          submitter_notes: "",
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
      <p className="text-[14px] text-slate-500 dark:text-slate-400 leading-7 mb-8">
        اگر رسانه، کانال تلگرام، حساب اکس (توییتر) یا منبع دیگری می‌شناسید که
        باید پوشش داده شود، فرم زیر را پر کنید. همه پیشنهادها توسط تیم
        بررسی می‌شوند و در صورت تأیید، به منابع افزوده خواهند شد.
      </p>

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
              <option value="state">حکومتی</option>
              <option value="semi_state">نیمه‌حکومتی</option>
              <option value="independent">مستقل</option>
              <option value="diaspora">برون‌مرزی</option>
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

        {/* Optional submitter info */}
        <div className="pt-4 mt-4 border-t border-slate-200 dark:border-slate-800">
          <p className="text-[12px] text-slate-500 dark:text-slate-400 mb-4 leading-6">
            اطلاعات زیر اختیاری است — اگر مایل هستید، می‌توانیم در صورت نیاز با شما
            تماس بگیریم.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
                نام شما
              </label>
              <input
                type="text"
                value={form.submitter_name}
                onChange={(e) => update("submitter_name", e.target.value)}
                className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white"
              />
            </div>
            <div>
              <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
                راه تماس
              </label>
              <input
                type="text"
                dir="ltr"
                value={form.submitter_contact}
                onChange={(e) => update("submitter_contact", e.target.value)}
                placeholder="ایمیل یا تلگرام"
                className="w-full px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-slate-900 dark:focus:border-white text-left"
              />
            </div>
          </div>
        </div>

        {/* Notes */}
        <div>
          <label className="block text-[13px] font-bold text-slate-900 dark:text-white mb-1.5">
            یادداشت‌های تکمیلی
          </label>
          <textarea
            value={form.submitter_notes}
            onChange={(e) => update("submitter_notes", e.target.value)}
            placeholder="هر اطلاعات دیگری که فکر می‌کنید مفید است"
            rows={2}
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
          پیشنهادها توسط تیم به‌صورت دستی بررسی می‌شوند. اطلاعات تماس شما فقط برای
          پیگیری پیشنهاد استفاده می‌شود و با هیچ شخص ثالثی به اشتراک گذاشته
          نمی‌شود.
        </p>
      </div>
    </div>
  );
}
