"use client";

import { Fragment, useEffect, useState, useCallback } from "react";
import { DollarSign, RefreshCw, AlertTriangle } from "lucide-react";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Summary = {
  window: string;
  totals: { total_cost: number; input_cost: number; cached_cost: number; output_cost: number; input_tokens: number; output_tokens: number; cached_input_tokens: number; calls: number };
  today: { cost: number; calls: number };
  yesterday: { cost: number; calls: number };
  by_model: Array<{ model: string; calls: number; cost: number; input_tokens: number; output_tokens: number }>;
  by_purpose: Array<{ purpose: string; calls: number; cost: number; input_tokens: number; output_tokens: number }>;
  daily: Array<{ day: string; purpose: string; cost: number }>;
  unpriced_count: number;
};

type Call = {
  id: string;
  timestamp: string;
  model: string;
  purpose: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  total_cost: number;
  priced: boolean;
  story_id: string | null;
  article_id: string | null;
};

type TopStory = {
  story_id: string;
  title_fa: string | null;
  article_count: number | null;
  calls: number;
  cost: number;
  by_purpose?: Array<{ purpose: string; calls: number; cost: number }>;
};

const WINDOWS: { key: string; label: string }[] = [
  { key: "24h", label: "24 ساعت" },
  { key: "7d", label: "۷ روز" },
  { key: "30d", label: "۳۰ روز" },
  { key: "90d", label: "۹۰ روز" },
];

function fmt$(n: number | null | undefined): string {
  if (n == null) return "$0.00";
  if (n < 0.01) return "$" + n.toFixed(4);
  return "$" + n.toFixed(2);
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "0";
  return n.toLocaleString("en-US");
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = (Date.now() - then) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export default function CostDashboardPage() {
  const [authed, setAuthed] = useState<boolean>(false);
  const [tokenInput, setTokenInput] = useState("");
  const [window, setWindow] = useState("7d");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [topStories, setTopStories] = useState<TopStory[]>([]);
  const [expandedStory, setExpandedStory] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<{ model?: string; purpose?: string }>({});

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const h = adminHeaders();
      const params = new URLSearchParams({ limit: "100" });
      if (filter.model) params.set("model", filter.model);
      if (filter.purpose) params.set("purpose", filter.purpose);
      const [s, c, t] = await Promise.all([
        fetch(`${API}/api/v1/admin/cost/summary?window=${window}`, { headers: h, cache: "no-store" }).then(r => r.json()),
        fetch(`${API}/api/v1/admin/cost/calls?${params.toString()}`, { headers: h, cache: "no-store" }).then(r => r.json()),
        fetch(`${API}/api/v1/admin/cost/top-stories?days=${window === "24h" ? 1 : window === "7d" ? 7 : window === "30d" ? 30 : 90}&limit=20`, { headers: h, cache: "no-store" }).then(r => r.json()),
      ]);
      setSummary(s);
      setCalls(c.calls || []);
      setTopStories(t.stories || []);
    } catch (e: any) {
      setErr(e?.message || "خطا");
    } finally {
      setLoading(false);
    }
  }, [window, filter]);

  useEffect(() => {
    if (authed) fetchAll();
  }, [authed, fetchAll]);

  if (!authed) {
    return (
      <div className="p-8 max-w-md mx-auto" dir="rtl">
        <h1 className="text-xl font-bold mb-4">ورود ادمین</h1>
        <input
          type="password"
          className="w-full border border-slate-300 dark:border-slate-700 px-3 py-2 bg-transparent"
          placeholder="admin token"
          value={tokenInput}
          onChange={e => setTokenInput(e.target.value)}
        />
        <button
          className="mt-3 px-4 py-2 bg-slate-900 text-white dark:bg-white dark:text-slate-900"
          onClick={() => {
            localStorage.setItem("doornegar_admin_token", tokenInput);
            setAuthed(true);
          }}
        >
          ورود
        </button>
      </div>
    );
  }

  const todayDelta = summary ? summary.today.cost - summary.yesterday.cost : 0;

  return (
    <div dir="rtl" className="p-6 max-w-7xl mx-auto text-slate-900 dark:text-slate-100">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <DollarSign className="w-7 h-7 text-emerald-500" />
          <h1 className="text-2xl font-black">هزینه مدل‌های زبانی</h1>
        </div>
        <div className="flex items-center gap-2">
          {WINDOWS.map(w => (
            <button
              key={w.key}
              onClick={() => setWindow(w.key)}
              className={`px-3 py-1.5 text-sm border ${window === w.key
                ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900 border-slate-900 dark:border-white"
                : "border-slate-300 dark:border-slate-700 text-slate-500 hover:border-slate-500"}`}
            >
              {w.label}
            </button>
          ))}
          <button onClick={fetchAll} className="p-2 border border-slate-300 dark:border-slate-700 hover:border-slate-500" title="تازه‌سازی">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-4 px-4 py-3 border border-red-300 bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-200 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
      )}

      {summary && (
        <>
          {/* Top tile row */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <StatTile label="امروز" value={fmt$(summary.today.cost)} sub={`${fmtNum(summary.today.calls)} فراخوان`} delta={todayDelta} />
            <StatTile label="دیروز" value={fmt$(summary.yesterday.cost)} sub={`${fmtNum(summary.yesterday.calls)} فراخوان`} />
            <StatTile label={`مجموع (${WINDOWS.find(w => w.key === window)?.label})`} value={fmt$(summary.totals.total_cost)} sub={`${fmtNum(summary.totals.calls)} فراخوان`} />
            <StatTile label="توکن‌ها" value={fmtNum(summary.totals.input_tokens + summary.totals.output_tokens)} sub={`${fmtNum(summary.totals.input_tokens)} ورودی · ${fmtNum(summary.totals.output_tokens)} خروجی`} />
          </div>

          {summary.unpriced_count > 0 && (
            <div className="mb-4 px-4 py-2 border border-amber-300 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              {fmtNum(summary.unpriced_count)} فراخوان بدون قیمت‌گذاری — مدل در جدول پایه هزینه وجود ندارد. به llm_pricing.py اضافه کن.
            </div>
          )}

          {/* Two column: by model + by purpose */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <BreakdownTable
              title="بر اساس مدل"
              rows={summary.by_model.map(r => ({ key: r.model, cost: r.cost, calls: r.calls, input: r.input_tokens, output: r.output_tokens }))}
              onRowClick={(key) => setFilter(f => ({ ...f, model: f.model === key ? undefined : key }))}
              activeKey={filter.model}
            />
            <BreakdownTable
              title="بر اساس هدف"
              rows={summary.by_purpose.map(r => ({ key: r.purpose, cost: r.cost, calls: r.calls, input: r.input_tokens, output: r.output_tokens }))}
              onRowClick={(key) => setFilter(f => ({ ...f, purpose: f.purpose === key ? undefined : key }))}
              activeKey={filter.purpose}
            />
          </div>

          {/* Daily trend — simple horizontal bars per day */}
          <DailyTrend data={summary.daily} total={summary.totals.total_cost} />

          {/* Top stories */}
          {topStories.length > 0 && (
            <div className="mb-6">
              <h2 className="text-sm font-black mb-3 border-b border-slate-200 dark:border-slate-800 pb-2">گران‌ترین خبرها</h2>
              <div className="border border-slate-200 dark:border-slate-800">
                <table className="w-full text-sm">
                  <thead className="text-[11px] text-slate-500 bg-slate-50 dark:bg-slate-900/50">
                    <tr>
                      <th className="text-right px-3 py-2">خبر</th>
                      <th className="text-right px-3 py-2 w-24">مقاله‌ها</th>
                      <th className="text-right px-3 py-2 w-24">فراخوان</th>
                      <th className="text-right px-3 py-2 w-24">هزینه</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {topStories.map(s => {
                      const isOpen = expandedStory === s.story_id;
                      return (
                        <Fragment key={s.story_id}>
                          <tr
                            className="hover:bg-slate-50 dark:hover:bg-slate-900/30 cursor-pointer"
                            onClick={() => setExpandedStory(isOpen ? null : s.story_id)}
                          >
                            <td className="px-3 py-2">
                              <span className="text-slate-400 mr-1">{isOpen ? "▾" : "▸"}</span>
                              <a
                                href={`/fa/stories/${s.story_id}`}
                                className="hover:underline text-blue-600 dark:text-blue-400"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {s.title_fa || "(بدون عنوان)"}
                              </a>
                            </td>
                            <td className="px-3 py-2 text-slate-500">{s.article_count ?? "—"}</td>
                            <td className="px-3 py-2 text-slate-500">{fmtNum(s.calls)}</td>
                            <td className="px-3 py-2 font-mono">{fmt$(s.cost)}</td>
                          </tr>
                          {isOpen && s.by_purpose && s.by_purpose.length > 0 && (
                            <tr className="bg-slate-50 dark:bg-slate-900/40">
                              <td colSpan={4} className="px-6 py-3">
                                <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">تفکیک بر اساس هدف</div>
                                <table className="w-full text-xs">
                                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                    {s.by_purpose.map(p => (
                                      <tr key={p.purpose}>
                                        <td className="py-1 font-mono text-slate-600 dark:text-slate-300">{p.purpose}</td>
                                        <td className="py-1 text-left text-slate-500 w-20">{fmtNum(p.calls)} فراخوان</td>
                                        <td className="py-1 text-left font-mono w-24">{fmt$(p.cost)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Recent calls */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-black">فراخوان‌های اخیر {filter.model ? `· ${filter.model}` : ""}{filter.purpose ? ` · ${filter.purpose}` : ""}</h2>
              {(filter.model || filter.purpose) && (
                <button onClick={() => setFilter({})} className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline">پاک‌ کردن فیلتر</button>
              )}
            </div>
            <div className="border border-slate-200 dark:border-slate-800 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-[11px] text-slate-500 bg-slate-50 dark:bg-slate-900/50">
                  <tr>
                    <th className="text-right px-3 py-2 w-16">پیش</th>
                    <th className="text-right px-3 py-2">هدف</th>
                    <th className="text-right px-3 py-2">مدل</th>
                    <th className="text-right px-3 py-2 w-20">ورودی</th>
                    <th className="text-right px-3 py-2 w-20">کش</th>
                    <th className="text-right px-3 py-2 w-20">خروجی</th>
                    <th className="text-right px-3 py-2 w-24">هزینه</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {calls.map(c => (
                    <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-900/30 font-mono">
                      <td className="px-3 py-1.5 text-slate-400">{timeAgo(c.timestamp)}</td>
                      <td className="px-3 py-1.5">{c.purpose}</td>
                      <td className="px-3 py-1.5 text-slate-500">{c.model}</td>
                      <td className="px-3 py-1.5 text-right">{fmtNum(c.input_tokens)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtNum(c.cached_input_tokens)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtNum(c.output_tokens)}</td>
                      <td className={`px-3 py-1.5 text-right ${c.priced ? "" : "text-amber-500"}`}>{fmt$(c.total_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function StatTile({ label, value, sub, delta }: { label: string; value: string; sub?: string; delta?: number }) {
  return (
    <div className="border border-slate-200 dark:border-slate-800 p-4">
      <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">{label}</div>
      <div className="mt-1 text-2xl font-black">{value}</div>
      {sub && <div className="mt-1 text-[11px] text-slate-500">{sub}</div>}
      {delta !== undefined && delta !== 0 && (
        <div className={`mt-1 text-[11px] ${delta > 0 ? "text-red-500" : "text-emerald-500"}`}>
          {delta > 0 ? "↑" : "↓"} {fmt$(Math.abs(delta))} vs دیروز
        </div>
      )}
    </div>
  );
}

function BreakdownTable({ title, rows, onRowClick, activeKey }: {
  title: string;
  rows: Array<{ key: string; cost: number; calls: number; input: number; output: number }>;
  onRowClick: (key: string) => void;
  activeKey?: string;
}) {
  const total = rows.reduce((a, b) => a + b.cost, 0);
  return (
    <div className="border border-slate-200 dark:border-slate-800">
      <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
        {title}
      </div>
      <div className="divide-y divide-slate-200 dark:divide-slate-800">
        {rows.map(r => {
          const pct = total > 0 ? (r.cost / total) * 100 : 0;
          return (
            <button
              key={r.key}
              onClick={() => onRowClick(r.key)}
              className={`w-full text-right px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-900/30 ${activeKey === r.key ? "bg-blue-50 dark:bg-blue-950/30" : ""}`}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono text-slate-500">{r.key}</span>
                <span className="font-mono font-bold">{fmt$(r.cost)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-900 relative">
                  <div className="absolute inset-y-0 right-0 bg-emerald-500" style={{ width: `${pct}%` }} />
                </div>
                <span className="text-[10px] text-slate-400 font-mono w-10 text-right">{pct.toFixed(1)}٪</span>
              </div>
              <div className="mt-1 text-[10px] text-slate-400 font-mono">
                {fmtNum(r.calls)} فراخوان · {fmtNum(r.input + r.output)} توکن
              </div>
            </button>
          );
        })}
        {rows.length === 0 && (
          <div className="px-3 py-4 text-center text-xs text-slate-500">داده‌ای نیست</div>
        )}
      </div>
    </div>
  );
}

function DailyTrend({ data, total }: { data: Array<{ day: string; purpose: string; cost: number }>; total: number }) {
  // Aggregate by day across purposes
  const byDay: Record<string, Record<string, number>> = {};
  for (const r of data) {
    const dayKey = r.day.slice(0, 10);
    byDay[dayKey] = byDay[dayKey] || {};
    byDay[dayKey][r.purpose] = (byDay[dayKey][r.purpose] || 0) + r.cost;
  }
  const days = Object.keys(byDay).sort();
  const maxDay = Math.max(1e-9, ...days.map(d => Object.values(byDay[d]).reduce((a, b) => a + b, 0)));

  // Top 5 purposes get colors; the rest collapse into "other"
  const purposeTotals: Record<string, number> = {};
  for (const r of data) purposeTotals[r.purpose] = (purposeTotals[r.purpose] || 0) + r.cost;
  const topPurposes = Object.entries(purposeTotals).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k]) => k);
  const PURPOSE_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7", "#94a3b8"];

  return (
    <div className="mb-6 border border-slate-200 dark:border-slate-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-black">روند روزانه</div>
        <div className="flex flex-wrap gap-3 text-[10px]">
          {topPurposes.map((p, i) => (
            <span key={p} className="flex items-center gap-1">
              <span className="inline-block w-2 h-2" style={{ backgroundColor: PURPOSE_COLORS[i] }} />
              <span className="text-slate-500">{p}</span>
            </span>
          ))}
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2" style={{ backgroundColor: PURPOSE_COLORS[5] }} />
            <span className="text-slate-500">دیگر</span>
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        {days.map(d => {
          const dayTotal = Object.values(byDay[d]).reduce((a, b) => a + b, 0);
          const width = (dayTotal / maxDay) * 100;
          return (
            <div key={d} className="flex items-center gap-2">
              <span className="text-[11px] text-slate-500 font-mono w-20">{d}</span>
              <div className="flex-1 h-5 bg-slate-100 dark:bg-slate-900 relative flex items-center overflow-hidden" dir="ltr">
                <div className="absolute inset-y-0 left-0 flex" style={{ width: `${width}%` }}>
                  {topPurposes.map((p, i) => {
                    const v = byDay[d][p] || 0;
                    if (!v || !dayTotal) return null;
                    return <div key={p} style={{ width: `${(v / dayTotal) * 100}%`, backgroundColor: PURPOSE_COLORS[i] }} />;
                  })}
                  {(() => {
                    const otherVal = dayTotal - topPurposes.reduce((a, p) => a + (byDay[d][p] || 0), 0);
                    if (otherVal <= 0 || !dayTotal) return null;
                    return <div style={{ width: `${(otherVal / dayTotal) * 100}%`, backgroundColor: PURPOSE_COLORS[5] }} />;
                  })()}
                </div>
              </div>
              <span className="text-[11px] text-slate-700 dark:text-slate-300 font-mono font-bold w-16 text-left" dir="ltr">{fmt$(dayTotal)}</span>
            </div>
          );
        })}
        {days.length === 0 && <div className="text-center text-xs text-slate-500 py-6">هیچ فراخوانی در این بازه ثبت نشده</div>}
      </div>
    </div>
  );
}
