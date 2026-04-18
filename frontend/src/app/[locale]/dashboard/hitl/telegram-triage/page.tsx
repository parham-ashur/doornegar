"use client";

import { useEffect, useState, useCallback } from "react";
import { adminHeaders, hasAdminToken } from "../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Candidate {
  story_id: string;
  title_fa: string | null;
  score: number;
}

interface TriagePost {
  post_id: string;
  channel_title: string | null;
  channel_type: string | null;
  channel_username: string | null;
  text: string;
  posted_at: string | null;
  current_story_id: string | null;
  candidates: Candidate[];
}

export default function TelegramTriagePage() {
  const [authed, setAuthed] = useState(false);
  const [token, setToken] = useState("");
  const [items, setItems] = useState<TriagePost[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const load = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/hitl/telegram-triage?limit=30`, {
        headers: adminHeaders(),
      });
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      setItems(data.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [authed]);

  useEffect(() => {
    load();
  }, [load]);

  const link = async (post_id: string, story_id: string) => {
    const res = await fetch(`${API}/api/v1/admin/hitl/telegram-triage/${post_id}`, {
      method: "POST",
      headers: { ...adminHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ action: "link", story_id }),
    });
    if (res.ok) {
      setItems((prev) => prev.filter((p) => p.post_id !== post_id));
    } else {
      alert("خطا در اتصال");
    }
  };

  const unlink = async (post_id: string) => {
    const res = await fetch(`${API}/api/v1/admin/hitl/telegram-triage/${post_id}`, {
      method: "POST",
      headers: { ...adminHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ action: "unlink" }),
    });
    if (res.ok) {
      setItems((prev) => prev.filter((p) => p.post_id !== post_id));
    } else {
      alert("خطا");
    }
  };

  if (!authed) {
    return (
      <div>
        <h1 className="text-xl font-black mb-4">صف بررسی تلگرام</h1>
        <p className="text-[13px] mb-3">توکن ادمین:</p>
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
          صف بررسی تلگرام
        </h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="px-3 py-1.5 text-[13px] border border-slate-300 dark:border-slate-700"
          >
            {loading ? "در حال بارگذاری..." : "تازه‌سازی"}
          </button>
        </div>
      </div>
      <p className="text-[13px] text-slate-500 mb-4 leading-6">
        پست‌های زیر نمره ۰.۳۰ تا ۰.۴۰ به بهترین خبر گرفته‌اند (مرز تصمیم‌گیری خودکار).
        برای هر پست، بهترین خبر کاندید را انتخاب یا پست را بی‌ارتباط اعلام کنید.
      </p>

      {!loading && items.length === 0 && (
        <p className="text-[13px] text-slate-500">موردی برای بررسی نیست.</p>
      )}

      <div className="space-y-4">
        {items.map((p) => (
          <div
            key={p.post_id}
            className="border border-slate-200 dark:border-slate-800 p-4 bg-white dark:bg-slate-900"
          >
            <div className="flex items-center gap-2 mb-2 text-[12px] text-slate-500">
              <span className="font-bold text-slate-700 dark:text-slate-300">
                {p.channel_title || p.channel_username || "?"}
              </span>
              <span>·</span>
              <span>{p.channel_type}</span>
              {p.posted_at && (
                <>
                  <span>·</span>
                  <span>{new Date(p.posted_at).toLocaleString("fa-IR")}</span>
                </>
              )}
              {p.current_story_id && (
                <>
                  <span>·</span>
                  <a
                    href={`/fa/stories/${p.current_story_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-500"
                  >
                    الان متصل به یک خبر
                  </a>
                </>
              )}
            </div>
            <p className="text-[13px] text-slate-800 dark:text-slate-200 leading-6 mb-3 whitespace-pre-wrap">
              {p.text.length > 600 ? p.text.slice(0, 600) + "…" : p.text}
            </p>
            <div className="space-y-1.5">
              {p.candidates.map((c) => (
                <div key={c.story_id} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => link(p.post_id, c.story_id)}
                    className="px-2 py-1 text-[12px] bg-emerald-600 text-white hover:bg-emerald-700 shrink-0"
                  >
                    اتصال
                  </button>
                  <span className="text-[12px] font-mono text-slate-400 shrink-0 w-12 text-left">
                    {c.score.toFixed(3)}
                  </span>
                  <a
                    href={`/fa/stories/${c.story_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[13px] text-slate-700 dark:text-slate-300 hover:text-blue-600 truncate"
                  >
                    {c.title_fa || c.story_id}
                  </a>
                </div>
              ))}
              {p.current_story_id && (
                <button
                  type="button"
                  onClick={() => unlink(p.post_id)}
                  className="px-2 py-1 text-[12px] bg-red-50 dark:bg-red-950/40 text-red-600 border border-red-200 dark:border-red-900/40 mt-2"
                >
                  قطع اتصال
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
