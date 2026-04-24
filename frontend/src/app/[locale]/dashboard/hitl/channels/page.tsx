"use client";

import { useEffect, useState, useCallback } from "react";
import { adminHeaders, hasAdminToken } from "../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ChannelItem {
  id: string;
  username: string | null;
  title: string | null;
  channel_type: string | null;
  political_leaning: string | null;
  is_active: boolean;
  post_count: number;
  sample_posts: string[];
}

const CHANNEL_TYPES = [
  "news",
  "commentary",
  "aggregator",
  "activist",
  "political_party",
  "citizen",
];

export default function ChannelsPage() {
  const [authed, setAuthed] = useState(false);
  const [token, setToken] = useState("");
  const [items, setItems] = useState<ChannelItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const load = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/hitl/channels?limit=200`, {
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

  const update = async (id: string, patch: Partial<ChannelItem>) => {
    setSaving(id);
    try {
      await fetch(`${API}/api/v1/admin/hitl/channels/${id}`, {
        method: "PATCH",
        headers: { ...adminHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      setItems((prev) =>
        prev.map((c) => (c.id === id ? { ...c, ...patch } : c))
      );
    } finally {
      setSaving(null);
    }
  };

  if (!authed) {
    return (
      <div>
        <h1 className="text-xl font-black mb-4">Channel classification</h1>
        <p className="text-[13px] mb-3">Admin token:</p>
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
            Save
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-4">
        Telegram channel classification
      </h1>
      <p className="text-[13px] text-slate-500 mb-6 leading-6">
        Review three recent posts per channel and set the right type. The
        change hits the analysis pool immediately. Channel types:{" "}
        <span dir="ltr" className="font-mono">news</span> /{" "}
        <span dir="ltr" className="font-mono">commentary</span> /{" "}
        <span dir="ltr" className="font-mono">aggregator</span> /{" "}
        <span dir="ltr" className="font-mono">activist</span> /{" "}
        <span dir="ltr" className="font-mono">political_party</span> /{" "}
        <span dir="ltr" className="font-mono">citizen</span>.
      </p>

      {loading && <p className="text-[13px]">Loading…</p>}

      <div className="space-y-4">
        {items.map((ch) => (
          <div
            key={ch.id}
            className="border border-slate-200 dark:border-slate-800 p-4 bg-white dark:bg-slate-900"
          >
            <div className="flex items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="text-[13px] font-bold text-slate-900 dark:text-white">
                  {ch.title || ch.username || ch.id.slice(0, 8)}
                </h3>
                {ch.username && (
                  <span className="text-[12px] text-slate-500" dir="ltr">
                    @{ch.username} · {ch.post_count} post{ch.post_count === 1 ? "" : "s"}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={ch.channel_type || ""}
                  onChange={(e) => update(ch.id, { channel_type: e.target.value })}
                  disabled={saving === ch.id}
                  className="px-2 py-1 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  dir="ltr"
                >
                  <option value="">(unset)</option>
                  {CHANNEL_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-1 text-[12px]">
                  <input
                    type="checkbox"
                    checked={ch.is_active}
                    onChange={(e) => update(ch.id, { is_active: e.target.checked })}
                  />
                  Active
                </label>
              </div>
            </div>
            {ch.sample_posts.length === 0 && (
              <p className="text-[12px] text-slate-400">(no recent posts)</p>
            )}
            <div className="space-y-1">
              {ch.sample_posts.map((s, i) => (
                <p
                  key={i}
                  className="text-[12px] text-slate-600 dark:text-slate-400 border-r-2 border-slate-200 dark:border-slate-800 pr-2 leading-5"
                >
                  {s}
                </p>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
