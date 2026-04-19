"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SubmissionType = "article" | "telegram_post" | "instagram_post" | "news" | "other";

interface StoryOption {
  id: string;
  title_fa: string;
  title_en: string | null;
}

const TYPE_LABELS: Record<SubmissionType, string> = {
  article: "مقالهٔ خبری",
  telegram_post: "پست تلگرام",
  instagram_post: "پست اینستاگرام",
  news: "خبر از منبع دیگر",
  other: "سایر",
};

export default function SubmitPage() {
  const [type, setType] = useState<SubmissionType>("article");
  const [storyOptions, setStoryOptions] = useState<StoryOption[]>([]);
  const [suggestedStoryId, setSuggestedStoryId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [channelUsername, setChannelUsername] = useState("");
  const [isAnalyst, setIsAnalyst] = useState<"yes" | "no" | "unsure">("unsure");
  const [language, setLanguage] = useState<"fa" | "en">("fa");
  const [imageUrl, setImageUrl] = useState("");
  const [publishedAt, setPublishedAt] = useState("");
  const [submitterNote, setSubmitterNote] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Load the top trending stories once so the submitter can optionally
  // link their submission to one. Limit to 30 — if their story isn't in
  // the top 30 they can leave this blank and Niloofar will attach it.
  useEffect(() => {
    fetch(`${API}/api/v1/stories/trending?limit=30`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setStoryOptions(Array.isArray(data) ? data : []))
      .catch(() => setStoryOptions([]));
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);

    const payload: Record<string, unknown> = {
      submission_type: type,
      content: content.trim(),
      language,
    };
    if (suggestedStoryId) payload.suggested_story_id = suggestedStoryId;
    if (title.trim()) payload.title = title.trim();
    if (sourceName.trim()) payload.source_name = sourceName.trim();
    if (sourceUrl.trim()) payload.source_url = sourceUrl.trim();
    if (imageUrl.trim()) payload.image_url = imageUrl.trim();
    if (publishedAt.trim()) payload.published_at = publishedAt.trim();
    if (submitterNote.trim()) payload.submitter_note = submitterNote.trim();

    if (type === "telegram_post") {
      payload.channel_username = channelUsername.trim().replace(/^@/, "");
      if (isAnalyst !== "unsure") payload.is_analyst = isAnalyst === "yes";
    }

    try {
      const res = await fetch(`${API}/api/v1/submissions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok && data.status === "duplicate") {
        // Friendly duplicate message — not an error, just informational.
        setResult({ ok: false, message: data.message || "این مورد قبلاً ارسال شده است." });
      } else if (res.ok) {
        setResult({ ok: true, message: data.message || "ارسال شد" });
        // Reset everything except submitter identity
        setTitle(""); setContent(""); setSourceName(""); setSourceUrl("");
        setChannelUsername(""); setIsAnalyst("unsure");
        setSuggestedStoryId(""); setSubmitterNote("");
        setImageUrl(""); setPublishedAt("");
      } else {
        setResult({ ok: false, message: data.detail || "خطا در ارسال" });
      }
    } catch {
      setResult({ ok: false, message: "خطا در اتصال به سرور" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div dir="rtl" className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-black text-slate-900 dark:text-white mb-2">
        ارسال محتوای جدید
      </h1>
      <p className="text-[14px] text-slate-500 dark:text-slate-400 leading-6 mb-6">
        اگر مقاله، پست تلگرام، یا محتوایی از اینستاگرام/منابع دیگر می‌شناسید که باید به یکی از خبرهای دورنگر اضافه شود، آن را اینجا بفرستید.
        اگر مطمئن نیستید به کدام خبر مربوط می‌شود، خالی بگذارید — تیم بررسی خودش آن را به دسته مناسب متصل می‌کند.
      </p>

      <form onSubmit={onSubmit} className="space-y-5">
        {/* Type */}
        <div>
          <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
            نوع محتوا
          </label>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(TYPE_LABELS) as SubmissionType[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setType(t)}
                className={`px-3 py-1.5 text-[13px] border transition-colors ${
                  type === t
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:border-blue-400"
                }`}
              >
                {TYPE_LABELS[t]}
              </button>
            ))}
          </div>
        </div>

        {/* Story link */}
        <div>
          <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
            به کدام خبر مربوط است؟ (اختیاری)
          </label>
          <select
            value={suggestedStoryId}
            onChange={(e) => setSuggestedStoryId(e.target.value)}
            className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
          >
            <option value="">— نمی‌دانم، تیم متصل کند —</option>
            {storyOptions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title_fa}
              </option>
            ))}
          </select>
        </div>

        {/* Title */}
        <div>
          <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
            عنوان {type === "article" ? "مقاله" : "محتوا"} (اختیاری)
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
          />
        </div>

        {/* Content */}
        <div>
          <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
            متن کامل محتوا <span className="text-red-500">*</span>
          </label>
          <textarea
            required
            minLength={10}
            maxLength={20000}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={8}
            className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
            placeholder="متن کامل مقاله، پست تلگرام، یا محتوای دیگر را اینجا بچسبانید..."
          />
        </div>

        {/* Source */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
              نام منبع
            </label>
            <input
              type="text"
              value={sourceName}
              onChange={(e) => setSourceName(e.target.value)}
              placeholder={type === "telegram_post" ? "مثل: کانال مصاف" : "مثل: بی‌بی‌سی فارسی"}
              className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
              لینک منبع (اختیاری)
            </label>
            <input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://..."
              dir="ltr"
              className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
            />
          </div>
        </div>

        {/* Telegram-specific */}
        {type === "telegram_post" && (
          <div className="border border-blue-200 dark:border-blue-900/40 bg-blue-50/50 dark:bg-blue-950/20 p-4 space-y-4">
            <div>
              <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
                نام کاربری کانال <span className="text-red-500">*</span>
              </label>
              <input
                required
                type="text"
                value={channelUsername}
                onChange={(e) => setChannelUsername(e.target.value)}
                placeholder="@ManotoTV یا ManotoTV"
                dir="ltr"
                className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
                آیا این کانال تحلیلگر است یا خبری؟
              </label>
              <div className="flex gap-2">
                {[
                  { v: "yes", l: "تحلیلگر/نظر" },
                  { v: "no", l: "خبری صرف" },
                  { v: "unsure", l: "مطمئن نیستم" },
                ].map(({ v, l }) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setIsAnalyst(v as typeof isAnalyst)}
                    className={`px-3 py-1.5 text-[13px] border ${
                      isAnalyst === v
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700"
                    }`}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Image + published date — both optional, high-signal */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
              لینک تصویر (اختیاری)
            </label>
            <input
              type="url"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://…/image.jpg"
              dir="ltr"
              className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
            />
            <p className="text-[12px] text-slate-400 mt-1">
              اگر این محتوا تصویر دارد، لینک آن را بگذارید تا در صفحه خبر استفاده شود.
            </p>
          </div>
          <div>
            <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
              تاریخ انتشار (اختیاری)
            </label>
            <input
              type="datetime-local"
              value={publishedAt}
              onChange={(e) => setPublishedAt(e.target.value)}
              dir="ltr"
              className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
            />
          </div>
        </div>

        {/* Language */}
        <div>
          <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
            زبان محتوا
          </label>
          <div className="flex gap-2">
            {(["fa", "en"] as const).map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => setLanguage(l)}
                className={`px-3 py-1.5 text-[13px] border ${
                  language === l
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700"
                }`}
              >
                {l === "fa" ? "فارسی" : "انگلیسی"}
              </button>
            ))}
          </div>
        </div>

        {/* Note */}
        <div>
          <label className="block text-[13px] font-bold text-slate-700 dark:text-slate-300 mb-2">
            یادداشت برای تیم بررسی (اختیاری)
          </label>
          <textarea
            value={submitterNote}
            onChange={(e) => setSubmitterNote(e.target.value)}
            rows={2}
            placeholder="چرا این محتوا مهم است؟ کجا پیدا کردید؟ اگر یک پست تلگرام است، منبع اصلی کیست؟"
            className="w-full px-3 py-2 text-[13px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:border-blue-500 outline-none"
          />
        </div>

        {/* Submit */}
        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={submitting || content.trim().length < 10}
            className="px-6 py-2 text-[13px] font-bold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "در حال ارسال..." : "ارسال"}
          </button>
          {result && (
            <div
              className={`flex items-center gap-2 text-[13px] ${
                result.ok
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
              }`}
            >
              {result.ok ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
              {result.message}
            </div>
          )}
        </div>
      </form>
    </div>
  );
}
