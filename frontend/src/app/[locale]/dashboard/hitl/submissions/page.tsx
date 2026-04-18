"use client";

import { useEffect, useState, useCallback } from "react";
import { adminHeaders, hasAdminToken } from "../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Submission {
  id: string;
  submission_type: string;
  suggested_story_id: string | null;
  title: string | null;
  content: string;
  source_name: string | null;
  source_url: string | null;
  channel_username: string | null;
  is_analyst: boolean | null;
  image_url: string | null;
  published_at: string | null;
  submitter_note: string | null;
  status: string;
  admin_notes: string | null;
  created_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  pending: "در انتظار",
  accepted_article: "پذیرفته (مقاله)",
  accepted_post: "پذیرفته (پست)",
  rejected: "رد",
  duplicate: "تکراری",
};

export default function SubmissionsPage() {
  const [token, setToken] = useState("");
  const [authed, setAuthed] = useState(false);
  const [items, setItems] = useState<Submission[]>([]);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const load = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API}/api/v1/submissions?status=${statusFilter}&limit=100`,
        { headers: adminHeaders() }
      );
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      setItems(data.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [authed, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (id: string, status: string) => {
    if (!confirm(`مطمئنید؟ وضعیت → ${STATUS_LABELS[status]}`)) return;
    const res = await fetch(`${API}/api/v1/submissions/${id}`, {
      method: "PATCH",
      headers: { ...adminHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (res.ok) {
      load();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(`خطا: ${err.detail || res.statusText}`);
    }
  };

  if (!authed) {
    return (
      <div>
        <h1 className="text-xl font-black mb-4">ارسال‌ها</h1>
        <p className="text-[13px] mb-3">توکن ادمین را وارد کنید:</p>
        <div className="flex gap-2">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            dir="ltr"
            className="px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 w-96"
          />
          <button
            type="button"
            onClick={() => {
              localStorage.setItem("doornegar_admin_token", token);
              setAuthed(true);
            }}
            className="px-4 py-2 text-[13px] bg-blue-600 text-white"
          >
            ذخیره
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-black text-slate-900 dark:text-white">
          ارسال‌های کاربران
        </h1>
        <div className="flex gap-2">
          {Object.keys(STATUS_LABELS).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 text-[13px] border ${
                statusFilter === s
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700"
              }`}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="text-[13px] text-slate-500">در حال بارگذاری...</p>}
      {!loading && items.length === 0 && (
        <p className="text-[13px] text-slate-500">موردی یافت نشد.</p>
      )}

      <div className="space-y-4">
        {items.map((it) => (
          <div
            key={it.id}
            className="border border-slate-200 dark:border-slate-800 p-4 bg-white dark:bg-slate-900"
          >
            <div className="flex items-start justify-between gap-4 mb-2">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[12px] font-bold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 px-2 py-0.5">
                    {it.submission_type}
                  </span>
                  {it.channel_username && (
                    <span className="text-[12px] text-slate-500" dir="ltr">
                      @{it.channel_username}
                    </span>
                  )}
                  {it.is_analyst === true && (
                    <span className="text-[12px] text-emerald-600">تحلیلگر</span>
                  )}
                  <span className="text-[12px] text-slate-400">
                    {new Date(it.created_at).toLocaleString("fa-IR")}
                  </span>
                </div>
                {it.title && (
                  <h3 className="text-[13px] font-bold text-slate-900 dark:text-white">
                    {it.title}
                  </h3>
                )}
              </div>
              {it.status === "pending" && (
                <div className="flex gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() =>
                      act(
                        it.id,
                        it.submission_type === "telegram_post"
                          ? "accepted_post"
                          : "accepted_article"
                      )
                    }
                    className="px-3 py-1 text-[12px] bg-emerald-600 text-white"
                  >
                    پذیرش
                  </button>
                  <button
                    type="button"
                    onClick={() => act(it.id, "rejected")}
                    className="px-3 py-1 text-[12px] bg-red-600 text-white"
                  >
                    رد
                  </button>
                  <button
                    type="button"
                    onClick={() => act(it.id, "duplicate")}
                    className="px-3 py-1 text-[12px] bg-slate-500 text-white"
                  >
                    تکراری
                  </button>
                </div>
              )}
            </div>
            <p className="text-[13px] text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-6">
              {it.content.length > 400 ? it.content.slice(0, 400) + "…" : it.content}
            </p>
            {it.image_url && (
              <a href={it.image_url} target="_blank" rel="noreferrer" className="text-[12px] text-blue-500 mt-2 block" dir="ltr">
                📷 {it.image_url}
              </a>
            )}
            {it.source_url && (
              <a href={it.source_url} target="_blank" rel="noreferrer" className="text-[12px] text-blue-500 block" dir="ltr">
                🔗 {it.source_url}
              </a>
            )}
            {it.submitter_note && (
              <p className="text-[12px] text-slate-500 mt-2 italic">
                یادداشت فرستنده: {it.submitter_note}
              </p>
            )}
            {it.suggested_story_id && (
              <a
                href={`/fa/stories/${it.suggested_story_id}`}
                target="_blank"
                rel="noreferrer"
                className="text-[12px] text-blue-500 mt-1 block"
              >
                ← پیشنهاد اتصال به خبر
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
