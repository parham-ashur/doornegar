"use client";

// /dashboard/content-filter — what the ingest classifier kept vs dropped.
// Pulls /api/v1/admin/content-type/stats. Window is 7 days by default,
// adjustable to 1 / 7 / 30. Per-source rows show kept/dropped split so
// outlets that skew heavily non-news (khabaronline.ir is the canonical
// example) become visible at a glance.

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ByLabel = {
  news: number;
  opinion: number;
  discussion: number;
  aggregation: number;
  other: number;
};

type SourceRow = {
  id: string;
  slug: string;
  name_fa: string;
  name_en: string;
  state_alignment: string;
  allowed: string[];
  total: number;
  kept: number;
  dropped: number;
  unclassified: number;
  by_label: ByLabel;
};

type StatsResponse = {
  window_days: number | null;
  window_hours: number | null;
  generated_at: string;
  rollup: { total: number; kept: number; dropped: number; unclassified: number };
  by_label: ByLabel;
  labels: string[];
  sources: SourceRow[];
};

// Window selector value: "Nh" for hours, "Nd" for days.
type WindowValue = "1h" | "1d" | "7d" | "30d";

const LABEL_COLORS: Record<string, string> = {
  news: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  opinion: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  discussion: "bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  aggregation: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  other: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

function pct(n: number, d: number): string {
  if (d <= 0) return "0%";
  return `${Math.round((100 * n) / d)}%`;
}

export default function ContentFilterDashboardPage() {
  const [authed, setAuthed] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [windowValue, setWindowValue] = useState<WindowValue>("7d");
  const [data, setData] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const qs = windowValue.endsWith("h")
        ? `hours=${parseInt(windowValue, 10)}`
        : `days=${parseInt(windowValue, 10)}`;
      const res = await fetch(
        `${API}/api/v1/admin/content-type/stats?${qs}`,
        { headers: adminHeaders(), cache: "no-store" },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: StatsResponse = await res.json();
      setData(json);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Error");
    } finally {
      setLoading(false);
    }
  }, [windowValue]);

  useEffect(() => {
    if (authed) fetchStats();
  }, [authed, fetchStats]);

  if (!authed) {
    return (
      <div className="p-8 max-w-md mx-auto">
        <h1 className="text-xl font-bold mb-4">Admin login</h1>
        <input
          type="password"
          className="w-full border border-slate-300 dark:border-slate-700 px-3 py-2 bg-transparent"
          placeholder="admin token"
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
        />
        <button
          className="mt-3 px-4 py-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900"
          onClick={() => {
            localStorage.setItem("doornegar_admin_token", tokenInput.trim());
            setAuthed(true);
          }}
        >
          Sign in
        </button>
      </div>
    );
  }

  const rollup = data?.rollup;
  const byLabel = data?.by_label;
  const sources = data?.sources ?? [];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Content filter</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Articles and Telegram posts the ingest classifier kept (news) versus dropped (opinion / discussion / aggregation / other).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={windowValue}
            onChange={(e) => setWindowValue(e.target.value as WindowValue)}
            className="border border-slate-300 dark:border-slate-700 px-2 py-1.5 text-sm bg-transparent"
          >
            <option value="1h">Last hour</option>
            <option value="1d">Last 24h</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <button
            onClick={fetchStats}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-300 dark:border-slate-700 text-sm hover:bg-slate-50 dark:hover:bg-slate-900"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {err && <p className="text-sm text-red-500 mb-3">{err}</p>}

      {rollup && byLabel && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <Card label="Total ingested" value={rollup.total} sub="all rows in window" />
            <Card
              label="Kept (news)"
              value={rollup.kept}
              sub={pct(rollup.kept, rollup.total) + " of total"}
              tone="emerald"
            />
            <Card
              label="Dropped"
              value={rollup.dropped}
              sub={pct(rollup.dropped, rollup.total) + " of total"}
              tone="amber"
            />
            <Card
              label="Unclassified"
              value={rollup.unclassified}
              sub={pct(rollup.unclassified, rollup.total) + " · pending classifier"}
              tone="slate"
            />
          </div>

          <div className="border border-slate-200 dark:border-slate-800 mb-6">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 text-sm font-bold">
              By label
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-0 divide-x divide-slate-200 dark:divide-slate-800">
              {(Object.keys(byLabel) as Array<keyof ByLabel>).map((k) => (
                <div key={k} className="p-4">
                  <div className={`inline-block text-[11px] uppercase tracking-wide px-1.5 py-0.5 ${LABEL_COLORS[k]}`}>
                    {k}
                  </div>
                  <div className="text-2xl font-bold mt-2">{byLabel[k]}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {pct(byLabel[k], rollup.total)} of total
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="border border-slate-200 dark:border-slate-800">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 text-sm font-bold">
          Per source ({sources.length})
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-[11px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium text-right">Total</th>
                <th className="px-3 py-2 font-medium text-right">Kept</th>
                <th className="px-3 py-2 font-medium text-right">Dropped</th>
                <th className="px-3 py-2 font-medium">Drop breakdown</th>
                <th className="px-3 py-2 font-medium">Allowed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {sources.map((s) => {
                const dropPct = s.total > 0 ? Math.round((100 * s.dropped) / s.total) : 0;
                return (
                  <tr key={s.id}>
                    <td className="px-3 py-2">
                      <div className="font-medium">{s.name_en || s.slug}</div>
                      <div className="text-[11px] text-slate-500">{s.slug} · {s.state_alignment}</div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.total}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-emerald-700 dark:text-emerald-400">{s.kept}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <span className={dropPct >= 30 ? "text-amber-700 dark:text-amber-400 font-bold" : ""}>
                        {s.dropped} <span className="text-[11px] text-slate-500">({dropPct}%)</span>
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(["opinion", "discussion", "aggregation", "other"] as const).map((k) =>
                          s.by_label[k] > 0 ? (
                            <span key={k} className={`text-[11px] px-1.5 py-0.5 ${LABEL_COLORS[k]}`}>
                              {k} {s.by_label[k]}
                            </span>
                          ) : null,
                        )}
                        {s.unclassified > 0 && (
                          <span className="text-[11px] px-1.5 py-0.5 bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                            unclassified {s.unclassified}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-[11px] text-slate-500">
                      {s.allowed.join(", ")}
                    </td>
                  </tr>
                );
              })}
              {sources.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                    No data yet — the classifier hasn&apos;t produced labels for this window.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {data?.generated_at && (
        <p className="text-xs text-slate-500 mt-4">
          Generated {new Date(data.generated_at).toLocaleString()} · window{" "}
          {data.window_hours ? `${data.window_hours}h` : `${data.window_days}d`}
        </p>
      )}
    </div>
  );
}

function Card({
  label,
  value,
  sub,
  tone = "slate",
}: {
  label: string;
  value: number;
  sub?: string;
  tone?: "emerald" | "amber" | "slate";
}) {
  const toneClass =
    tone === "emerald"
      ? "text-emerald-700 dark:text-emerald-400"
      : tone === "amber"
        ? "text-amber-700 dark:text-amber-400"
        : "text-slate-900 dark:text-white";
  return (
    <div className="border border-slate-200 dark:border-slate-800 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${toneClass}`}>{value.toLocaleString()}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}
