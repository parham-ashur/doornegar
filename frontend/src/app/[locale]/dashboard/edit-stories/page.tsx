"use client";

import { useCallback, useEffect, useState } from "react";
import type { StoryAnalysis, StoryBrief } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type StoryWithAnalysis = StoryBrief & {
  _analysis?: Partial<StoryAnalysis> | null;
  _isEdited?: boolean;
};

type Draft = {
  title_fa: string;
  title_en: string;
  state_summary_fa: string;
  diaspora_summary_fa: string;
  bias_explanation_fa: string;
};

const EMPTY_DRAFT: Draft = {
  title_fa: "",
  title_en: "",
  state_summary_fa: "",
  diaspora_summary_fa: "",
  bias_explanation_fa: "",
};

export default function EditStoriesPage() {
  const [authed, setAuthed] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [stories, setStories] = useState<StoryWithAnalysis[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [statusMap, setStatusMap] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [fetchLimit, setFetchLimit] = useState(50);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("doornegar_admin_token");
      if (token) {
        setAdminToken(token);
        setAuthed(true);
      }
    }
  }, []);

  const loadStories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/stories/trending?limit=${fetchLimit}`);
      if (!res.ok) {
        setStatusMap({ _global: `خطا در بارگذاری داستان‌ها (${res.status})` });
        return;
      }
      const data: StoryBrief[] = await res.json();
      // Fetch analysis + is_edited for each story in parallel
      const enriched: StoryWithAnalysis[] = await Promise.all(
        data.map(async (s) => {
          try {
            const aRes = await fetch(`${API}/api/v1/stories/${s.id}/analysis`);
            const analysis = aRes.ok ? await aRes.json() : null;
            return { ...s, _analysis: analysis };
          } catch {
            return { ...s, _analysis: null };
          }
        }),
      );
      setStories(enriched);
      // Seed drafts with current values
      const seeded: Record<string, Draft> = {};
      enriched.forEach((s) => {
        const a = s._analysis ?? {};
        seeded[s.id] = {
          title_fa: s.title_fa ?? "",
          title_en: s.title_en ?? "",
          state_summary_fa: (a.state_summary_fa as string) ?? "",
          diaspora_summary_fa: (a.diaspora_summary_fa as string) ?? "",
          bias_explanation_fa: (a.bias_explanation_fa as string) ?? "",
        };
      });
      setDrafts(seeded);
      setStatusMap({});
    } catch (e) {
      setStatusMap({ _global: `خطا: ${String(e).slice(0, 120)}` });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) loadStories();
  }, [authed, loadStories]);

  // Filter stories client-side by the search query (matches fa + en titles).
  // Persian-insensitive: we normalise zero-width chars and lower-case en.
  const normalise = (s: string) =>
    (s || "")
      .replace(/[\u200c\u200d\u200e\u200f]/g, "")
      .replace(/ی/g, "ي")
      .replace(/ک/g, "ك")
      .toLowerCase()
      .trim();
  const query = normalise(search);
  const filteredStories = query
    ? stories.filter((s) => {
        const t = normalise(`${s.title_fa} ${s.title_en ?? ""}`);
        return t.includes(query);
      })
    : stories;

  const updateDraft = (id: string, field: keyof Draft, value: string) => {
    setDrafts((prev) => ({
      ...prev,
      [id]: { ...(prev[id] ?? EMPTY_DRAFT), [field]: value },
    }));
  };

  const saveStory = async (id: string) => {
    const draft = drafts[id];
    if (!draft) return;
    if (!adminToken) {
      setStatusMap((p) => ({ ...p, [id]: "نخست توکن مدیریت را وارد کنید" }));
      return;
    }
    setSavingId(id);
    setStatusMap((p) => ({ ...p, [id]: "در حال ذخیره..." }));
    try {
      const res = await fetch(`${API}/api/v1/admin/stories/${id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${adminToken}`,
        },
        body: JSON.stringify({
          title_fa: draft.title_fa,
          title_en: draft.title_en,
          state_summary_fa: draft.state_summary_fa,
          diaspora_summary_fa: draft.diaspora_summary_fa,
          bias_explanation_fa: draft.bias_explanation_fa,
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        setStatusMap((p) => ({ ...p, [id]: `خطا (${res.status}): ${err.slice(0, 200)}` }));
        return;
      }
      setStatusMap((p) => ({ ...p, [id]: "ذخیره شد ✓" }));
      // Reflect the updated title in the list
      setStories((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, title_fa: draft.title_fa, title_en: draft.title_en, _isEdited: true }
            : s,
        ),
      );
    } catch (e) {
      setStatusMap((p) => ({ ...p, [id]: `خطا: ${String(e).slice(0, 120)}` }));
    } finally {
      setSavingId(null);
    }
  };

  // Login gate — requires backend ADMIN_TOKEN
  if (!authed) {
    return (
      <div dir="rtl" className="mx-auto max-w-md p-6">
        <h1 className="mb-4 text-2xl font-bold text-slate-900 dark:text-white">
          ویرایش داستان‌ها
        </h1>
        <p className="mb-4 text-sm text-slate-500">
          برای دسترسی به داشبورد ابتدا از صفحه{" "}
          <a href="./" className="underline">اصلی داشبورد</a>{" "}
          توکن مدیریت را وارد کنید.
        </p>
      </div>
    );
  }

  return (
    <div dir="rtl" className="mx-auto max-w-4xl p-6">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            ویرایش داستان‌ها
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            عنوان، روایت‌ها و توضیح سوگیری داستان‌ها. ویرایش دستی از بازتولید
            خودکار در خط‌لوله شبانه مصون می‌ماند.
          </p>
        </div>
        <button
          onClick={loadStories}
          className="shrink-0 rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          بارگذاری مجدد
        </button>
      </div>

      {/* Search + load-more controls */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجو در عنوان فارسی یا انگلیسی..."
          className="flex-1 rounded border border-slate-300 bg-white p-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
          dir="rtl"
        />
        <select
          value={fetchLimit}
          onChange={(e) => setFetchLimit(Number(e.target.value))}
          className="shrink-0 rounded border border-slate-300 bg-white p-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
        >
          <option value={15}>۱۵ داستان</option>
          <option value={30}>۳۰ داستان</option>
          <option value={50}>۵۰ داستان</option>
          <option value={100}>۱۰۰ داستان</option>
          <option value={200}>۲۰۰ داستان</option>
        </select>
      </div>

      {/* Result count */}
      {!loading && (
        <p className="mb-3 text-xs text-slate-500">
          {query
            ? `${filteredStories.length} از ${stories.length} داستان با «${search}» مطابقت دارد`
            : `نمایش ${stories.length} داستان`}
        </p>
      )}

      {/* Admin token input */}
      <div className="mb-6 rounded border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900">
        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500">
          توکن مدیریت (ADMIN_TOKEN)
        </label>
        <input
          type="password"
          value={adminToken}
          onChange={(e) => {
            setAdminToken(e.target.value);
            localStorage.setItem("doornegar_admin_token", e.target.value);
          }}
          className="mt-2 w-full rounded border border-slate-300 bg-white p-2 font-mono text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          placeholder="Paste ADMIN_TOKEN"
        />
      </div>

      {statusMap._global && (
        <p className="mb-4 rounded bg-rose-100 p-3 text-sm text-rose-900">
          {statusMap._global}
        </p>
      )}

      {loading && (
        <p className="text-sm text-slate-500">در حال بارگذاری داستان‌ها...</p>
      )}

      <div className="space-y-3">
        {filteredStories.map((s, idx) => {
          const isOpen = expandedId === s.id;
          const draft = drafts[s.id] ?? EMPTY_DRAFT;
          const statusMsg = statusMap[s.id];
          return (
            <div
              key={s.id}
              className="rounded border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
            >
              <button
                type="button"
                className="flex w-full items-start justify-between gap-3 p-4 text-right"
                onClick={() => setExpandedId(isOpen ? null : s.id)}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-slate-400">
                    #{idx + 1} · {s.article_count} مقاله · {s.source_count} منبع
                    {s._isEdited && (
                      <span className="mr-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-900">
                        ویرایش دستی
                      </span>
                    )}
                  </div>
                  <div className="mt-1 truncate text-base font-bold text-slate-900 dark:text-white">
                    {s.title_fa}
                  </div>
                </div>
                <span className="shrink-0 text-slate-400">{isOpen ? "▲" : "▼"}</span>
              </button>

              {isOpen && (
                <div className="border-t border-slate-200 p-4 space-y-4 dark:border-slate-800">
                  <Field
                    label="عنوان فارسی"
                    value={draft.title_fa}
                    onChange={(v) => updateDraft(s.id, "title_fa", v)}
                  />
                  <Field
                    label="Title (English)"
                    value={draft.title_en}
                    onChange={(v) => updateDraft(s.id, "title_en", v)}
                    ltr
                  />
                  <Field
                    label="روایت درون‌مرزی"
                    value={draft.state_summary_fa}
                    onChange={(v) => updateDraft(s.id, "state_summary_fa", v)}
                    multiline
                  />
                  <Field
                    label="روایت برون‌مرزی"
                    value={draft.diaspora_summary_fa}
                    onChange={(v) => updateDraft(s.id, "diaspora_summary_fa", v)}
                    multiline
                  />
                  <Field
                    label="مقایسه سوگیری"
                    value={draft.bias_explanation_fa}
                    onChange={(v) => updateDraft(s.id, "bias_explanation_fa", v)}
                    multiline
                  />

                  <div className="flex items-center justify-between pt-2">
                    {statusMsg ? (
                      <span
                        className={`text-sm ${
                          statusMsg.includes("✓")
                            ? "text-emerald-600"
                            : statusMsg.includes("خطا")
                              ? "text-rose-600"
                              : "text-slate-500"
                        }`}
                      >
                        {statusMsg}
                      </span>
                    ) : (
                      <span />
                    )}
                    <button
                      type="button"
                      disabled={savingId === s.id}
                      onClick={() => saveStory(s.id)}
                      className="rounded bg-slate-900 px-5 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-white dark:text-slate-900"
                    >
                      {savingId === s.id ? "در حال ذخیره..." : "ذخیره"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {!loading && stories.length === 0 && (
        <p className="mt-6 text-center text-sm text-slate-500">داستانی یافت نشد.</p>
      )}
      {!loading && stories.length > 0 && filteredStories.length === 0 && (
        <p className="mt-6 text-center text-sm text-slate-500">
          نتیجه‌ای برای «{search}» پیدا نشد.
        </p>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  multiline,
  ltr,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  ltr?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">
        {label}
      </label>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          dir={ltr ? "ltr" : "rtl"}
          className="w-full rounded border border-slate-300 bg-white p-3 text-sm leading-7 text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          dir={ltr ? "ltr" : "rtl"}
          className="w-full rounded border border-slate-300 bg-white p-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      )}
    </div>
  );
}
