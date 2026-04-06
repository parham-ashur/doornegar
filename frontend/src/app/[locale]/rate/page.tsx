"use client";

import { useState, useEffect } from "react";
import { useLocale } from "next-intl";
import {
  Eye, EyeOff, LogIn, Send, ChevronRight, CheckCircle,
  AlertTriangle, Gauge,
} from "lucide-react";
import FactCheckBarometer from "@/components/common/FactCheckBarometer";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FRAMING_OPTIONS = [
  { value: "conflict", fa: "تعارض", en: "Conflict" },
  { value: "human_interest", fa: "داستان انسانی", en: "Human Interest" },
  { value: "economic_impact", fa: "تأثیر اقتصادی", en: "Economic Impact" },
  { value: "security", fa: "امنیت", en: "Security" },
  { value: "victimization", fa: "قربانی‌سازی", en: "Victimization" },
  { value: "resistance", fa: "مقاومت", en: "Resistance" },
  { value: "sovereignty", fa: "حاکمیت", en: "Sovereignty" },
  { value: "western_interference", fa: "دخالت غرب", en: "Western Interference" },
  { value: "human_rights", fa: "حقوق بشر", en: "Human Rights" },
  { value: "reform", fa: "اصلاحات", en: "Reform" },
  { value: "national_pride", fa: "غرور ملی", en: "National Pride" },
  { value: "corruption", fa: "فساد", en: "Corruption" },
];

export default function RatePage() {
  const locale = useLocale();
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [article, setArticle] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [totalRated, setTotalRated] = useState(0);
  const [startTime, setStartTime] = useState<number>(0);

  // Rating state
  const [politicalAlignment, setPoliticalAlignment] = useState(0);
  const [factuality, setFactuality] = useState(3);
  const [tone, setTone] = useState(0);
  const [emotionalLanguage, setEmotionalLanguage] = useState(3);
  const [framingLabels, setFramingLabels] = useState<string[]>([]);
  const [notes, setNotes] = useState("");

  // Check for saved token
  useEffect(() => {
    const saved = localStorage.getItem("doornegar_token");
    if (saved) setToken(saved);
  }, []);

  async function handleLogin() {
    setLoginError("");
    try {
      const res = await fetch(`${API}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json();
        setLoginError(data.detail || "Login failed");
        return;
      }
      const data = await res.json();
      setToken(data.access_token);
      localStorage.setItem("doornegar_token", data.access_token);
      loadNextArticle(data.access_token);
    } catch {
      setLoginError("Connection error");
    }
  }

  async function loadNextArticle(t?: string) {
    const authToken = t || token;
    if (!authToken) return;
    setLoading(true);
    setSubmitted(false);
    resetRating();
    try {
      const res = await fetch(`${API}/api/v1/rate/next`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await res.json();
      if (data.status === "ok") {
        setArticle(data.article);
        setStartTime(Date.now());
      } else {
        setArticle(null);
      }
    } catch {
      setArticle(null);
    }
    setLoading(false);
  }

  function resetRating() {
    setPoliticalAlignment(0);
    setFactuality(3);
    setTone(0);
    setEmotionalLanguage(3);
    setFramingLabels([]);
    setNotes("");
  }

  async function submitRating() {
    if (!token || !article) return;
    setLoading(true);
    try {
      const timeSpent = Math.round((Date.now() - startTime) / 1000);
      const res = await fetch(`${API}/api/v1/rate/${article.id}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          political_alignment_rating: politicalAlignment,
          factuality_rating: factuality,
          tone_rating: tone,
          emotional_language_rating: emotionalLanguage,
          framing_labels: framingLabels,
          notes: notes || null,
          was_blind: true,
          time_spent_seconds: timeSpent,
        }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        setSubmitted(true);
        setTotalRated(data.total_ratings);
      }
    } catch (e) {
      alert("خطا در ارسال امتیاز");
    }
    setLoading(false);
  }

  function toggleFraming(value: string) {
    setFramingLabels((prev) =>
      prev.includes(value) ? prev.filter((f) => f !== value) : [...prev, value]
    );
  }

  function handleLogout() {
    setToken(null);
    setArticle(null);
    localStorage.removeItem("doornegar_token");
  }

  // Login screen
  if (!token) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card">
          <div className="mb-6 text-center">
            <EyeOff className="mx-auto mb-3 h-10 w-10 text-diaspora" />
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">
              ورود ارزیابان
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              فقط ارزیابان دعوت‌شده می‌توانند وارد شوند
            </p>
          </div>

          {loginError && (
            <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
              {loginError}
            </div>
          )}

          <div className="space-y-4">
            <input
              type="text"
              placeholder="نام کاربری"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm dark:border-slate-600 dark:bg-slate-800"
              dir="ltr"
            />
            <input
              type="password"
              placeholder="رمز عبور"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm dark:border-slate-600 dark:bg-slate-800"
              dir="ltr"
            />
            <button
              onClick={handleLogin}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-diaspora px-4 py-2.5 text-sm font-semibold text-white hover:bg-diaspora-dark"
            >
              <LogIn className="h-4 w-4" />
              ورود
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Submitted screen
  if (submitted) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card text-center">
          <CheckCircle className="mx-auto mb-4 h-12 w-12 text-emerald-500" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            امتیاز ثبت شد!
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            تعداد ارزیابی‌های شما: {totalRated}
          </p>
          <button
            onClick={() => loadNextArticle()}
            className="mt-6 flex items-center justify-center gap-2 mx-auto rounded-lg bg-diaspora px-6 py-2.5 text-sm font-semibold text-white hover:bg-diaspora-dark"
          >
            مقاله بعدی
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    );
  }

  // No more articles
  if (!article && !loading) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="card text-center">
          <CheckCircle className="mx-auto mb-4 h-10 w-10 text-emerald-500" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            همه مقالات ارزیابی شدند!
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            در حال حاضر مقاله جدیدی برای ارزیابی وجود ندارد
          </p>
        </div>
      </div>
    );
  }

  // Rating interface
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <EyeOff className="h-5 w-5 text-amber-500" />
          <h1 className="text-lg font-bold text-slate-900 dark:text-white">
            ارزیابی کور
          </h1>
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            منبع مخفی
          </span>
        </div>
        <button onClick={handleLogout} className="text-xs text-slate-400 hover:text-red-500">
          خروج
        </button>
      </div>

      {loading ? (
        <div className="card text-center text-slate-500 py-12">در حال بارگذاری...</div>
      ) : article ? (
        <div className="space-y-6">
          {/* Article (blind — no source shown) */}
          <div className="card">
            <h2 className="text-lg font-bold leading-relaxed text-slate-900 dark:text-white">
              {article.title}
            </h2>
            {article.summary && (
              <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {article.summary}
              </p>
            )}
            {article.content_text && (
              <div className="mt-4 max-h-60 overflow-y-auto rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {article.content_text.slice(0, 2000)}
                {article.content_text.length > 2000 && "..."}
              </div>
            )}
          </div>

          {/* Rating Form */}
          <div className="card space-y-6">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">ارزیابی شما</h3>

            {/* 1. Political Alignment */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                گرایش سیاسی
              </label>
              <input
                type="range" min={-2} max={2} step={0.5}
                value={politicalAlignment}
                onChange={(e) => setPoliticalAlignment(parseFloat(e.target.value))}
                className="w-full accent-diaspora"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>حکومتی</span>
                <span>میانه</span>
                <span>اپوزیسیون</span>
              </div>
            </div>

            {/* 2. Factuality */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                واقعیت‌محوری
              </label>
              <input
                type="range" min={1} max={5} step={1}
                value={factuality}
                onChange={(e) => setFactuality(parseInt(e.target.value))}
                className="w-full accent-diaspora"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>نظر محض</span>
                <span>ترکیبی</span>
                <span>کاملاً مستند</span>
              </div>
            </div>

            {/* 3. Tone */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                لحن
              </label>
              <input
                type="range" min={-2} max={2} step={0.5}
                value={tone}
                onChange={(e) => setTone(parseFloat(e.target.value))}
                className="w-full accent-diaspora"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>بسیار منفی</span>
                <span>خنثی</span>
                <span>بسیار مثبت</span>
              </div>
            </div>

            {/* 4. Emotional Language */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                زبان احساسی
              </label>
              <input
                type="range" min={1} max={5} step={1}
                value={emotionalLanguage}
                onChange={(e) => setEmotionalLanguage(parseInt(e.target.value))}
                className="w-full accent-diaspora"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>بدون احساس</span>
                <span>متوسط</span>
                <span>بسیار احساسی</span>
              </div>
            </div>

            {/* 5. Framing Labels */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                چارچوب‌بندی (چند گزینه)
              </label>
              <div className="flex flex-wrap gap-2">
                {FRAMING_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => toggleFraming(opt.value)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      framingLabels.includes(opt.value)
                        ? "bg-diaspora text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-400"
                    }`}
                  >
                    {opt.fa}
                  </button>
                ))}
              </div>
            </div>

            {/* Notes */}
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">
                یادداشت (اختیاری)
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm dark:border-slate-600 dark:bg-slate-800"
                placeholder="توضیحات اضافی..."
              />
            </div>

            {/* Submit */}
            <button
              onClick={submitRating}
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
              ثبت ارزیابی
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
