"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminHeaders, hasAdminToken } from "../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ArcChapter {
  story_id: string;
  title_fa: string | null;
  image_url: string | null;
  first_published_at: string | null;
  article_count: number;
  order: number;
}

interface ArcSuggestion {
  chapters: ArcChapter[];
  already_in_arc_ids: string[];
  suggested_title_fa: string | null;
}

interface Arc {
  id: string;
  title_fa: string;
  title_en: string | null;
  slug: string;
  description_fa: string | null;
  chapters: ArcChapter[];
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("fa-IR", { month: "short", day: "numeric" });
}

export default function ArcsHitlPage() {
  const [authed, setAuthed] = useState(false);
  const [suggestions, setSuggestions] = useState<ArcSuggestion[] | null>(null);
  const [existing, setExisting] = useState<Arc[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, { title: string; chapterIds: string[] }>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sug, ex] = await Promise.all([
        fetch(`${API}/api/v1/admin/hitl/arcs/suggestions`, { headers: adminHeaders() }),
        fetch(`${API}/api/v1/admin/hitl/arcs`, { headers: adminHeaders() }),
      ]);
      if (!sug.ok) throw new Error(`suggestions ${sug.status}`);
      if (!ex.ok) throw new Error(`arcs ${ex.status}`);
      const sugData: ArcSuggestion[] = await sug.json();
      const exData: Arc[] = await ex.json();
      setSuggestions(sugData);
      setExisting(exData);
      // Seed draft titles from suggested_title_fa
      const ds: Record<number, { title: string; chapterIds: string[] }> = {};
      sugData.forEach((s, i) => {
        ds[i] = {
          title: s.suggested_title_fa || "",
          chapterIds: s.chapters.map(c => c.story_id),
        };
      });
      setDrafts(ds);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authed) load();
  }, [authed]);

  const createArc = async (idx: number, s: ArcSuggestion) => {
    const draft = drafts[idx];
    if (!draft || !draft.title.trim()) {
      setMsg("عنوان قوس را وارد کنید");
      return;
    }
    if (draft.chapterIds.length < 2) {
      setMsg("حداقل دو چپتر لازم است");
      return;
    }
    setPending(`sug-${idx}`);
    setMsg(null);
    try {
      const res = await fetch(`${API}/api/v1/admin/hitl/arcs`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...adminHeaders() },
        body: JSON.stringify({
          title_fa: draft.title.trim(),
          story_ids: draft.chapterIds,
        }),
      });
      if (!res.ok) throw new Error(`create ${res.status}`);
      setMsg("قوس ساخته شد");
      await load();
    } catch (e) {
      setMsg(`خطا: ${e}`);
    } finally {
      setPending(null);
    }
  };

  const toggleChapter = (idx: number, storyId: string) => {
    setDrafts(prev => {
      const d = prev[idx] || { title: "", chapterIds: [] };
      const has = d.chapterIds.includes(storyId);
      return {
        ...prev,
        [idx]: {
          ...d,
          chapterIds: has
            ? d.chapterIds.filter(id => id !== storyId)
            : [...d.chapterIds, storyId],
        },
      };
    });
  };

  const deleteArc = async (arcId: string) => {
    if (!confirm("حذف این قوس؟ مقاله‌ها دست‌نخورده می‌مانند، فقط برچسبِ قوس برداشته می‌شود.")) return;
    setPending(`del-${arcId}`);
    try {
      const res = await fetch(`${API}/api/v1/admin/hitl/arcs/${arcId}`, {
        method: "DELETE",
        headers: adminHeaders(),
      });
      if (!res.ok) throw new Error(`delete ${res.status}`);
      setMsg("قوس حذف شد");
      await load();
    } catch (e) {
      setMsg(`خطا: ${e}`);
    } finally {
      setPending(null);
    }
  };

  if (!authed) {
    return (
      <div dir="rtl" className="p-6">
        <p className="text-sm text-slate-500">
          برای دیدن این صفحه، از صفحهٔ{" "}
          <Link href="/fa/dashboard" className="text-blue-600 hover:underline">
            داشبورد
          </Link>{" "}
          وارد شوید.
        </p>
      </div>
    );
  }

  return (
    <div dir="rtl">
      <div className="mb-6">
        <h1 className="text-xl font-black text-slate-900 dark:text-white">
          قوس‌های روایت — پیشنهادها و موجودی
        </h1>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mt-1 leading-6">
          گروه‌هایی از خبرهای مرتبط که به‌صورت زمان‌بندی‌شده روی یک قوس روایتی قرار می‌گیرند.
          با فاصلهٔ شباهت مرکزِ خبر ≥ ۰.۵۵ پیشنهاد می‌شوند. کرایو خود انتخاب می‌کنید که کدام‌ها
          یک قوس واقعی‌اند.
        </p>
      </div>

      {msg && (
        <div className="mb-4 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 p-3 text-[13px] text-blue-700 dark:text-blue-300">
          {msg}
        </div>
      )}
      {error && (
        <div className="mb-4 border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-900/20 p-3 text-[13px] text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Existing arcs */}
      <section className="mb-8">
        <h2 className="text-[14px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
          قوس‌های موجود ({existing?.length ?? 0})
        </h2>
        {loading && <p className="text-[13px] text-slate-400">بارگذاری…</p>}
        {existing && existing.length === 0 && (
          <p className="text-[13px] text-slate-400">
            هنوز هیچ قوسی ساخته نشده. از بخش پیشنهادها یکی را بسازید.
          </p>
        )}
        {existing && existing.length > 0 && (
          <div className="space-y-3">
            {existing.map(arc => (
              <div key={arc.id} className="border border-slate-200 dark:border-slate-800 p-3">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="text-[14px] font-black text-slate-900 dark:text-white">
                      {arc.title_fa}
                    </h3>
                    {arc.description_fa && (
                      <p className="text-[13px] text-slate-500 mt-0.5">{arc.description_fa}</p>
                    )}
                    <p className="text-[12px] text-slate-400 mt-0.5 font-mono" dir="ltr">
                      /{arc.slug}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteArc(arc.id)}
                    disabled={pending === `del-${arc.id}`}
                    className="text-[13px] text-rose-500 hover:text-rose-700 disabled:opacity-40"
                  >
                    حذف
                  </button>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {arc.chapters.map((c, i) => (
                    <Link
                      key={c.story_id}
                      href={`/fa/stories/${c.story_id}`}
                      target="_blank"
                      className="flex items-center gap-2 border border-slate-200 dark:border-slate-800 px-2 py-1 text-[12px] hover:border-blue-400"
                    >
                      <span className="text-slate-400 font-mono">{i + 1}</span>
                      <span className="text-slate-700 dark:text-slate-300 line-clamp-1 max-w-[260px]">
                        {c.title_fa || c.story_id.slice(0, 8)}
                      </span>
                      <span className="text-slate-400 text-[11px]">
                        {formatDate(c.first_published_at)}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Suggestions */}
      <section>
        <h2 className="text-[14px] font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
          پیشنهاد قوس‌های جدید ({suggestions?.length ?? 0})
        </h2>
        {loading && <p className="text-[13px] text-slate-400">بارگذاری…</p>}
        {suggestions && suggestions.length === 0 && (
          <p className="text-[13px] text-slate-400">
            هیچ گروهی از ≥ ۳ خبر با شباهت کافی یافت نشد.
          </p>
        )}
        {suggestions && suggestions.map((s, i) => {
          const draft = drafts[i] || { title: "", chapterIds: [] };
          const isOpen = expanded === i;
          return (
            <div key={i} className="border border-slate-200 dark:border-slate-800 mb-3">
              <button
                onClick={() => setExpanded(isOpen ? null : i)}
                className="flex w-full items-center justify-between p-3 text-right hover:bg-slate-50 dark:hover:bg-slate-900/30"
              >
                <div className="flex-1 min-w-0">
                  <h3 className="text-[13px] font-bold text-slate-900 dark:text-white line-clamp-1">
                    {s.suggested_title_fa || `گروه ${i + 1}`}
                  </h3>
                  <p className="text-[12px] text-slate-400 mt-0.5">
                    {s.chapters.length} چپتر
                    {s.already_in_arc_ids.length > 0 && (
                      <span className="mr-2 text-amber-500">
                        · {s.already_in_arc_ids.length} در قوس دیگر
                      </span>
                    )}
                  </p>
                </div>
                <span className="text-slate-400 text-[11px] shrink-0 mr-2">
                  {isOpen ? "▲" : "▼"}
                </span>
              </button>
              {isOpen && (
                <div className="p-3 border-t border-slate-200 dark:border-slate-800 space-y-3">
                  <div>
                    <label className="block text-[12px] font-bold text-slate-600 dark:text-slate-400 mb-1">
                      عنوان قوس
                    </label>
                    <input
                      type="text"
                      value={draft.title}
                      onChange={e =>
                        setDrafts(prev => ({
                          ...prev,
                          [i]: { ...draft, title: e.target.value },
                        }))
                      }
                      className="w-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-[13px] px-2 py-1.5"
                      placeholder="مثلاً: بحران تنگهٔ هرمز"
                    />
                  </div>

                  <div>
                    <label className="block text-[12px] font-bold text-slate-600 dark:text-slate-400 mb-1">
                      چپترهای قوس (تیک بزنید تا شامل شود)
                    </label>
                    <div className="space-y-1.5">
                      {s.chapters.map(c => {
                        const included = draft.chapterIds.includes(c.story_id);
                        const inAnotherArc = s.already_in_arc_ids.includes(c.story_id);
                        return (
                          <label
                            key={c.story_id}
                            className="flex items-start gap-2 p-2 border border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-900/30"
                          >
                            <input
                              type="checkbox"
                              checked={included}
                              onChange={() => toggleChapter(i, c.story_id)}
                              className="mt-1"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] text-slate-400 font-mono">
                                  {formatDate(c.first_published_at)}
                                </span>
                                {inAnotherArc && (
                                  <span className="text-[10px] bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-1 py-0.5 border border-amber-200 dark:border-amber-800">
                                    در قوس دیگر
                                  </span>
                                )}
                              </div>
                              <p className="text-[13px] text-slate-700 dark:text-slate-300 line-clamp-2">
                                {c.title_fa || c.story_id.slice(0, 8)}
                              </p>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {c.article_count} مقاله
                              </p>
                            </div>
                            <Link
                              href={`/fa/stories/${c.story_id}`}
                              target="_blank"
                              className="text-[11px] text-blue-500 hover:underline shrink-0"
                              onClick={e => e.stopPropagation()}
                            >
                              مشاهده
                            </Link>
                          </label>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => createArc(i, s)}
                      disabled={pending === `sug-${i}` || !draft.title.trim() || draft.chapterIds.length < 2}
                      className="text-[13px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
                    >
                      {pending === `sug-${i}` ? "در حال ساخت…" : "ساخت قوس"}
                    </button>
                    <button
                      onClick={() => setExpanded(null)}
                      className="text-[13px] px-3 py-1.5 border border-slate-300 dark:border-slate-700"
                    >
                      نادیده
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
