"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Activity, AlertTriangle, CheckCircle, Circle, CreditCard,
  Database, ListChecks, MessageSquare, Newspaper, RefreshCw,
  Settings, Wrench, XCircle, BarChart3,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DashboardData {
  data: {
    articles: { total: number; last_24h: number; with_farsi_title: number; without_farsi_title: number };
    stories: { total: number; visible: number; with_summary: number; hidden: number };
    telegram: { channels: number; active: number; total_posts: number; posts_24h: number };
    sources: { total: number; state: number; diaspora: number; independent: number; other: number };
    bias_scores: { total: number; coverage_pct: number };
  };
  maintenance: { last_run: string | null; last_result: string; next_run_approx: string | null };
  api_costs: { note: string; estimated_monthly: string; clustering_per_run: string; summary_per_story: string };
  issues: { severity: string; message: string }[];
  actions_needed: string[];
  freshness_hours: number | null;
}

function freshnessColor(h: number | null) {
  if (h === null) return "bg-red-500";
  if (h <= 6) return "bg-emerald-500";
  if (h <= 24) return "bg-amber-500";
  return "bg-red-500";
}

function freshnessLabel(h: number | null) {
  if (h === null) return "No data";
  if (h <= 1) return "Up to date";
  return `${h.toFixed(0)}h ago`;
}

function severityIcon(s: string) {
  if (s === "error") return <XCircle className="h-4 w-4 shrink-0 text-red-500" />;
  if (s === "warning") return <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />;
  return <Circle className="h-4 w-4 shrink-0 text-blue-500" />;
}

function formatDate(iso: string | null) {
  if (!iso) return "Unknown";
  try { return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

function resultLabel(r: string) {
  return { success: "Success", partial_success: "Partial", in_progress_or_incomplete: "In progress", unknown: "Unknown" }[r] || r;
}

function resultColor(r: string) {
  if (r === "success") return "text-emerald-600 dark:text-emerald-400";
  if (r === "partial_success") return "text-amber-600 dark:text-amber-400";
  return "text-slate-500";
}

function StatCard({ icon, label, value, sub, iconBg }: { icon: React.ReactNode; label: string; value: string | number; sub?: string; iconBg: string }) {
  return (
    <div className="border border-slate-200 dark:border-slate-800 p-5 flex items-center gap-3">
      <div className={`p-2 ${iconBg}`}>{icon}</div>
      <div>
        <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
        <p className="text-xs text-slate-500">{label}</p>
        {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

const ADMIN_PASS = "doornegar2026";

export default function DashboardPage() {
  const [authed, setAuthed] = useState(false);
  const [passInput, setPassInput] = useState("");
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem("doornegar_admin") === "true") {
      setAuthed(true);
    }
  }, []);

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Admin Dashboard</h1>
        <p className="text-sm text-slate-500 mb-4">Enter admin password to access the dashboard.</p>
        <form onSubmit={(e) => {
          e.preventDefault();
          if (passInput === ADMIN_PASS) {
            localStorage.setItem("doornegar_admin", "true");
            setAuthed(true);
          } else {
            alert("Wrong password");
          }
        }}>
          <input
            type="password"
            value={passInput}
            onChange={(e) => setPassInput(e.target.value)}
            placeholder="Password"
            className="w-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white px-3 py-2 text-sm mb-3 focus:outline-none focus:border-blue-500"
          />
          <button type="submit" className="w-full bg-slate-900 dark:bg-white text-white dark:text-slate-900 py-2 text-sm font-medium hover:opacity-90">
            Access Dashboard
          </button>
        </form>
      </div>
    );
  }

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/v1/admin/dashboard`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDashboard(await res.json());
    } catch (e: any) {
      setError(e.message || "Unknown error");
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  async function triggerPipeline(step: string) {
    setRunning(step);
    try {
      const url = step === "maintenance" ? `${API}/api/v1/admin/maintenance/run` : `${API}/api/v1/admin/${step}/trigger`;
      const res = await fetch(url, { method: "POST" });
      const data = await res.json();
      alert(JSON.stringify(data, null, 2));
      fetchDashboard();
    } catch (e: any) { alert(`Error: ${e.message}`); }
    setRunning(null);
  }

  if (loading && !dashboard) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="flex items-center gap-3 text-slate-500">
          <RefreshCw className="h-5 w-5 animate-spin" />
          Loading dashboard...
        </div>
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/10 p-5 text-red-700 dark:text-red-400">
          <p className="font-semibold">Connection error</p>
          <p className="text-sm mt-1">{error}</p>
          <button onClick={fetchDashboard} className="mt-3 border border-red-300 dark:border-red-700 px-4 py-1.5 text-sm hover:bg-red-100 dark:hover:bg-red-900/20">
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!dashboard) return null;
  const d = dashboard.data;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-white">
            <Activity className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            Admin Dashboard
          </h1>
          <p className="mt-1 text-sm text-slate-500 flex items-center gap-2">
            System status & maintenance
            <span className="inline-flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${freshnessColor(dashboard.freshness_hours)}`} />
              <span className="text-xs">{freshnessLabel(dashboard.freshness_hours)}</span>
            </span>
          </p>
        </div>
        <button onClick={fetchDashboard} className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-4 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Stat Cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={<Newspaper className="h-5 w-5 text-blue-600 dark:text-blue-400" />} iconBg="bg-blue-100 dark:bg-blue-900/20" label="Total Articles" value={d.articles.total.toLocaleString()} sub={`${d.articles.last_24h} in last 24h`} />
        <StatCard icon={<Database className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />} iconBg="bg-emerald-100 dark:bg-emerald-900/20" label="Visible Stories" value={d.stories.visible} sub={`${d.stories.total} total (${d.stories.hidden} hidden)`} />
        <StatCard icon={<MessageSquare className="h-5 w-5 text-purple-600 dark:text-purple-400" />} iconBg="bg-purple-100 dark:bg-purple-900/20" label="Telegram Posts" value={d.telegram.total_posts.toLocaleString()} sub={`${d.telegram.posts_24h} in 24h · ${d.telegram.active} active channels`} />
        <StatCard icon={<BarChart3 className="h-5 w-5 text-amber-600 dark:text-amber-400" />} iconBg="bg-amber-100 dark:bg-amber-900/20" label="Bias Scores" value={d.bias_scores.total} sub={`${d.bias_scores.coverage_pct}% coverage`} />
      </div>

      {/* Maintenance + Costs */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <div className="border border-slate-200 dark:border-slate-800 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Wrench className="h-4 w-4 text-slate-400" /> Last Maintenance
          </h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">Last run</span><span className="text-slate-900 dark:text-slate-200">{formatDate(dashboard.maintenance.last_run)}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Result</span><span className={resultColor(dashboard.maintenance.last_result)}>{resultLabel(dashboard.maintenance.last_result)}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Next run (approx)</span><span className="text-slate-900 dark:text-slate-200">{formatDate(dashboard.maintenance.next_run_approx)}</span></div>
          </div>
        </div>

        <div className="border border-slate-200 dark:border-slate-800 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <CreditCard className="h-4 w-4 text-slate-400" /> API Costs
          </h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">Est. monthly</span><span className="font-mono text-slate-900 dark:text-slate-200">{dashboard.api_costs.estimated_monthly}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Per clustering run</span><span className="font-mono text-slate-900 dark:text-slate-200">{dashboard.api_costs.clustering_per_run}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Per story summary</span><span className="font-mono text-slate-900 dark:text-slate-200">{dashboard.api_costs.summary_per_story}</span></div>
            <p className="text-xs text-slate-400 pt-1 border-t border-slate-200 dark:border-slate-800">{dashboard.api_costs.note}</p>
          </div>
        </div>
      </div>

      {/* Issues */}
      {dashboard.issues.length > 0 && (
        <div className="mb-6 border border-slate-200 dark:border-slate-800 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" /> Issues & Warnings
          </h2>
          <div className="space-y-2">
            {dashboard.issues.map((issue, i) => (
              <div key={i} className="flex items-center gap-3 p-3 text-sm border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                {severityIcon(issue.severity)}
                <span className="text-slate-700 dark:text-slate-300">{issue.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      {dashboard.actions_needed.length > 0 && (
        <div className="mb-6 border border-slate-200 dark:border-slate-800 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-blue-500" /> Actions Needed
          </h2>
          <ul className="space-y-2">
            {dashboard.actions_needed.map((action, i) => (
              <li key={i} className="flex items-start gap-3 text-sm">
                <CheckCircle className="h-4 w-4 shrink-0 text-slate-400 mt-0.5" />
                <span className="text-slate-600 dark:text-slate-400 font-mono text-xs">{action}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Pipeline Controls */}
      <div className="border border-slate-200 dark:border-slate-800 p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <Settings className="h-4 w-4 text-slate-400" /> Pipeline Controls
        </h2>
        <div className="flex flex-wrap gap-3">
          {[
            { key: "ingest", label: "Ingest" },
            { key: "nlp", label: "NLP Process" },
            { key: "cluster", label: "Cluster" },
            { key: "bias", label: "Bias Score" },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => triggerPipeline(key)} disabled={running !== null}
              className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-4 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50">
              {label} {running === key && <RefreshCw className="h-3 w-3 animate-spin" />}
            </button>
          ))}
          <button onClick={() => triggerPipeline("maintenance")} disabled={running !== null}
            className="flex items-center gap-2 border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/10 px-4 py-2 text-sm text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/20 disabled:opacity-50">
            <Wrench className="h-4 w-4" /> Run Maintenance {running === "maintenance" && <RefreshCw className="h-3 w-3 animate-spin" />}
          </button>
        </div>
      </div>

      {/* Sources */}
      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Source Distribution</h2>
        <div className="flex flex-wrap gap-4 text-sm">
          {[
            { label: "State", count: d.sources.state, color: "bg-red-500" },
            { label: "Diaspora", count: d.sources.diaspora, color: "bg-blue-500" },
            { label: "Independent", count: d.sources.independent, color: "bg-emerald-500" },
            { label: "Other", count: d.sources.other, color: "bg-slate-400" },
          ].map(({ label, count, color }) => (
            <div key={label} className="flex items-center gap-2">
              <span className={`inline-block h-3 w-3 rounded-full ${color}`} />
              <span className="text-slate-500">{label}:</span>
              <span className="font-bold text-slate-900 dark:text-white">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Architecture link */}
      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">System Architecture</h2>
          <p className="text-xs text-slate-500 mt-1">Interactive map of all components, files, and data flows</p>
        </div>
        <a href="./dashboard/architecture" className="border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/10 px-4 py-2 text-sm text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/20">
          View Architecture →
        </a>
      </div>

      {/* Source Suggestions link */}
      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Source Suggestions</h2>
          <p className="text-xs text-slate-500 mt-1">Review suggestions submitted by visitors via the public form</p>
        </div>
        <a href="./dashboard/suggestions" className="border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/10 px-4 py-2 text-sm text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/20">
          Review Suggestions →
        </a>
      </div>

      {/* Improvement Feedback link */}
      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Improvement Feedback</h2>
          <p className="text-xs text-slate-500 mt-1">Todo list of content/design suggestions from raters</p>
        </div>
        <a href="./dashboard/improvements" className="border border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-900/10 px-4 py-2 text-sm text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/20">
          View Todo List →
        </a>
      </div>
    </div>
  );
}
