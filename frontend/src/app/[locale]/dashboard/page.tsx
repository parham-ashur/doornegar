"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Activity, AlertTriangle, CheckCircle, Circle, CreditCard,
  Database, ListChecks, MessageSquare, Newspaper, RefreshCw,
  Settings, Wrench, XCircle, BarChart3,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Diagnostics {
  articles: {
    total: number;
    no_title_fa: number;
    no_title_original: number;
    translatable_now: number;
    unprocessed: number;
    clustered_into_story: number;
    has_content_or_summary: number;
  };
  bias: {
    total_articles: number;
    eligible_for_scoring: number;
    already_scored: number;
    remaining_to_score: number;
    coverage_of_eligible_pct: number;
  };
  llm_keys: { openai_set: boolean; anthropic_set: boolean };
  notes: string[];
}

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
  const [adminToken, setAdminToken] = useState("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      if (localStorage.getItem("doornegar_admin") === "true") {
        setAuthed(true);
      }
      const token = localStorage.getItem("doornegar_admin_token");
      if (token) setAdminToken(token);
    }
  }, []);

  const authHeaders = useCallback((): Record<string, string> => {
    return adminToken ? { Authorization: `Bearer ${adminToken}` } : {};
  }, [adminToken]);

  const fetchDashboard = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/v1/admin/dashboard`, { headers: authHeaders() });
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          throw new Error("Admin token required or invalid. Paste your ADMIN_TOKEN below and click Load.");
        }
        throw new Error(`HTTP ${res.status}`);
      }
      setDashboard(await res.json());
    } catch (e: any) {
      setError(e.message || "Unknown error");
    }
    setLoading(false);
  }, [authHeaders, authed]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  // Diagnostics
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);

  const fetchDiagnostics = useCallback(async () => {
    setDiagLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/diagnostics`, { headers: authHeaders() });
      if (res.ok) setDiagnostics(await res.json());
    } catch {}
    setDiagLoading(false);
  }, [authHeaders]);

  // Recently re-summarized stories (to verify new LLM model output)
  const [recentSummaries, setRecentSummaries] = useState<any[] | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);

  const fetchRecentSummaries = useCallback(async () => {
    setRecentLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/recently-summarized?limit=15`, { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setRecentSummaries(data.items || []);
      }
    } catch {}
    setRecentLoading(false);
  }, [authHeaders]);

  // Data repair actions
  const [repairRunning, setRepairRunning] = useState<string | null>(null);

  const reEmbedAll = useCallback(async () => {
    const ok = confirm(
      "Re-embed ALL articles with OpenAI text-embedding-3-small.\n\n" +
      "Replaces old TF-IDF/sentence-transformer embeddings with high-quality\n" +
      "multilingual vectors. Used by the clustering pre-filter.\n\n" +
      "Cost: ~$0.01 for ~2500 articles. Takes ~30 seconds."
    );
    if (!ok) return;
    setRepairRunning("reembed");
    try {
      const res = await fetch(`${API}/api/v1/admin/re-embed-all?limit=2500`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      alert(`Re-embedded ${data.embedded ?? 0} / ${data.total ?? 0} articles.`);
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
    setRepairRunning(null);
  }, [authHeaders]);

  const nullifyLocalhostImages = useCallback(async () => {
    const ok = confirm(
      "Null every article.image_url pointing to http://localhost (broken dev URLs).\n\n" +
      "Safe operation — affects only broken URLs that are guaranteed not in R2.\n" +
      "Next maintenance run will re-fetch og:images from article sources."
    );
    if (!ok) return;
    setRepairRunning("nullify");
    try {
      const res = await fetch(`${API}/api/v1/admin/nullify-localhost-images`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      alert(`${data.nullified ?? 0} article image URLs nulled.`);
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
    setRepairRunning(null);
  }, [authHeaders]);

  const unclaimStoryArticles = useCallback(async () => {
    const storyId = prompt(
      "Story ID to unclaim (all articles detached, story hidden):\n\n" +
      "This is destructive — use it to blow away a badly-clustered story so\n" +
      "its articles redistribute on the next clustering run."
    );
    if (!storyId || !storyId.trim()) return;
    const ok = confirm(
      `Detach all articles from story ${storyId.trim().slice(0, 8)}... and hide it?\n\n` +
      "The story row is kept but marked priority = -100 and article_count = 0."
    );
    if (!ok) return;
    setRepairRunning("unclaim");
    try {
      const res = await fetch(
        `${API}/api/v1/admin/stories/${storyId.trim()}/unclaim-articles`,
        { method: "POST", headers: authHeaders() }
      );
      const data = await res.json();
      alert(
        data.status === "ok"
          ? `${data.articles_unclaimed} articles detached. Story hidden.\n\nRun maintenance to re-cluster them.`
          : `Error: ${data.error || "unknown"}`
      );
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
    setRepairRunning(null);
  }, [authHeaders]);

  // Force re-summarize N stories with the current model
  const [forceRunning, setForceRunning] = useState(false);
  const forceResummarize = useCallback(async (limit: number) => {
    const ok = confirm(
      `Force re-summarize ${limit} most-recent stories using ${limit} LLM calls now?\n\n` +
      `Cost: roughly $${(limit * 0.03).toFixed(2)}-$${(limit * 0.06).toFixed(2)} on gpt-5-mini.\n` +
      `Time: ~${Math.ceil(limit * 15 / 60)} minutes.`
    );
    if (!ok) return;
    setForceRunning(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/force-resummarize?limit=${limit}&mode=immediate&order=trending`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      alert(
        `${data.message}\n\nRegenerated: ${data.regenerated}\nFailed: ${data.failed || 0}\n\n` +
        `Click "Reload" in the 'Recently re-summarized stories' card to see the updated output.`
      );
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
    setForceRunning(false);
  }, [authHeaders]);

  // Progress tracking for maintenance runs
  const [maintStart, setMaintStart] = useState<number | null>(null);
  const [maintElapsed, setMaintElapsed] = useState(0);
  const [maintResult, setMaintResult] = useState<any>(null);
  // Live per-step status from the backend, updated by the polling effect
  const [maintLive, setMaintLive] = useState<any>(null);

  // Tick elapsed time every second while running
  useEffect(() => {
    if (!maintStart) return;
    const interval = setInterval(() => {
      setMaintElapsed(Math.floor((Date.now() - maintStart) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [maintStart]);

  // Refresh dashboard every 5 seconds while maintenance is running
  useEffect(() => {
    if (running !== "maintenance") return;
    const interval = setInterval(() => { fetchDashboard(); }, 5000);
    return () => clearInterval(interval);
  }, [running, fetchDashboard]);

  // Poll maintenance status every 3s while running (fire-and-forget pattern)
  useEffect(() => {
    if (running !== "maintenance") return;
    // Track how long we've been polling; if the backend reports "idle"
    // for >15s AFTER we've already seen a "running" state, the background
    // task died (most likely a backend restart killed it).
    let sawRunning = false;
    let firstIdleTs: number | null = null;
    const poll = async () => {
      try {
        const res = await fetch(`${API}/api/v1/admin/maintenance/status`, { headers: authHeaders() });
        if (!res.ok) return;
        const state = await res.json();
        setMaintLive(state);
        if (state.status === "running") {
          sawRunning = true;
          firstIdleTs = null;
        }
        if (state.status === "success" || state.status === "error") {
          setMaintResult(state);
          setRunning(null);
          fetchDashboard();
          return;
        }
        // Idle-after-running = backend restarted, task died
        if (state.status === "idle" && sawRunning) {
          if (firstIdleTs === null) firstIdleTs = Date.now();
          else if (Date.now() - firstIdleTs > 15000) {
            setMaintResult({
              status: "error",
              error: "Backend reports idle after a run was in progress. Most likely the backend was restarted (deploy, timeout, or crash) and the asyncio task was killed. Any work that completed before the kill is already saved to the database — just start a new run to continue.",
            });
            setRunning(null);
            fetchDashboard();
          }
        }
      } catch {}
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [running, authHeaders, fetchDashboard]);

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

  async function triggerPipeline(step: string) {
    if (step === "maintenance") {
      setMaintStart(Date.now());
      setMaintElapsed(0);
      setMaintResult(null);
      setMaintLive(null);
      setRunning("maintenance");
      try {
        const res = await fetch(`${API}/api/v1/admin/maintenance/run`, { method: "POST", headers: authHeaders() });
        const data = await res.json();
        if (data.status === "already_running") {
          // A previous run is still going — just attach to it
          // (polling effect picks up status)
        } else if (data.status !== "started") {
          setMaintResult({ status: "error", error: data.error || "Unknown error starting maintenance" });
          setRunning(null);
        }
      } catch (e: any) {
        setMaintResult({ status: "error", error: e.message });
        setRunning(null);
      }
      return;
    }

    setRunning(step);
    try {
      const res = await fetch(`${API}/api/v1/admin/${step}/trigger`, { method: "POST", headers: authHeaders() });
      const data = await res.json();
      alert(JSON.stringify(data, null, 2));
      fetchDashboard();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
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
      <div className="mx-auto max-w-xl px-4 py-8">
        <div className="border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/10 p-5 text-red-700 dark:text-red-400 mb-4">
          <p className="font-semibold">Connection error</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
        <div className="border border-slate-200 dark:border-slate-800 p-5">
          <label className="block text-sm font-semibold text-slate-900 dark:text-white mb-2">
            Admin Token
          </label>
          <p className="text-xs text-slate-500 mb-3">
            Paste your <code className="text-[11px] bg-slate-100 dark:bg-slate-800 px-1">ADMIN_TOKEN</code> from Railway environment variables.
            It's saved in your browser for this device.
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={adminToken}
              onChange={(e) => {
                setAdminToken(e.target.value);
                if (typeof window !== "undefined") localStorage.setItem("doornegar_admin_token", e.target.value);
              }}
              placeholder="Paste ADMIN_TOKEN"
              className="flex-1 px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={fetchDashboard}
              className="px-4 py-2 text-sm bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90"
            >
              Load
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!dashboard) return null;
  const d = dashboard.data;

  // Progress modal shown while maintenance is running or just finished
  const maintModal = (running === "maintenance" || maintResult) && (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-sm">
      <div className="w-full max-w-xl bg-white dark:bg-[#0a0e1a] border border-slate-200 dark:border-slate-800 shadow-2xl">
        <div className="px-6 py-5 border-b border-slate-200 dark:border-slate-800">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            {running === "maintenance" ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin text-blue-600" />
                Running maintenance...
              </>
            ) : maintResult?.error ? (
              <>
                <XCircle className="h-4 w-4 text-red-500" />
                Maintenance failed
              </>
            ) : (
              <>
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                Maintenance complete
              </>
            )}
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Elapsed: <span className="font-mono">{Math.floor(maintElapsed / 60)}:{String(maintElapsed % 60).padStart(2, "0")}</span>
            {running === "maintenance" && " · full run with backlog can take 30-60 min (gpt-5-mini is slow but accurate)"}
          </p>
        </div>

        <div className="px-6 py-5 space-y-4">
          {running === "maintenance" && maintLive && (
            <>
              {/* Progress bar based on # completed steps */}
              {(() => {
                const TOTAL = 23; // matches pipeline length in auto_maintenance.run_maintenance
                const done = (maintLive.steps || []).length;
                const pct = Math.min(100, Math.round((done / TOTAL) * 100));
                return (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[10px] text-slate-500">
                      <span>Step {done + 1} of {TOTAL}</span>
                      <span>{pct}%</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                      <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })()}

              {/* Currently running step */}
              {maintLive.current_step && (
                <div className="flex items-center gap-2 text-xs text-slate-900 dark:text-white py-2 px-3 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/50">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-600 dark:text-blue-400 shrink-0" />
                  <span className="font-semibold flex-1">{maintLive.current_step}</span>
                  {maintLive.current_step_elapsed_s !== undefined && (
                    <span className="font-mono text-[10px] text-slate-500">
                      {maintLive.current_step_elapsed_s}s
                    </span>
                  )}
                </div>
              )}

              {/* Scrollable list of steps completed so far (most recent first) */}
              {(maintLive.steps || []).length > 0 && (
                <div className="border border-slate-200 dark:border-slate-800 max-h-64 overflow-y-auto" dir="ltr">
                  {[...maintLive.steps].reverse().map((step: any, idx: number) => {
                    const isError = step.status !== "ok";
                    const errorMsg = isError && step.stats && typeof step.stats === "object"
                      ? (step.stats.error as string | undefined)
                      : null;
                    return (
                      <div
                        key={`${step.name}-${idx}`}
                        className={`px-3 py-1.5 text-[11px] border-b border-slate-100 dark:border-slate-800/50 last:border-b-0 ${
                          isError ? "bg-red-50 dark:bg-red-950/20" : ""
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          {step.status === "ok" ? (
                            <CheckCircle className="h-3 w-3 mt-0.5 shrink-0 text-emerald-500" />
                          ) : (
                            <XCircle className="h-3 w-3 mt-0.5 shrink-0 text-red-500" />
                          )}
                          <span className="flex-1 text-slate-700 dark:text-slate-300">{step.name}</span>
                          <span className="font-mono text-slate-400 text-[10px]">{step.elapsed_s}s</span>
                          {!isError && step.stats && typeof step.stats === "object" && (
                            <span className="text-slate-500 text-[10px] max-w-[50%] truncate">
                              {Object.entries(step.stats as Record<string, any>)
                                .filter(([k, v]) => typeof v === "number" && v > 0 && k !== "error")
                                .slice(0, 3)
                                .map(([k, v]) => `${k}:${v}`)
                                .join(" ") || ""}
                            </span>
                          )}
                        </div>
                        {/* Show error message for failed steps */}
                        {errorMsg && (
                          <div className="mt-1 pl-5 text-[10px] font-mono text-red-600 dark:text-red-400 break-all">
                            {errorMsg}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* Before the first status poll lands */}
          {running === "maintenance" && !maintLive && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <RefreshCw className="h-3 w-3 animate-spin" />
              Starting maintenance…
            </div>
          )}

          {/* Live counters — refreshes every 5s while running */}
          {dashboard && (
            <div className="grid grid-cols-3 gap-3 pt-2 border-t border-slate-200 dark:border-slate-800">
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Articles</p>
                <p className="text-base font-bold text-slate-900 dark:text-white">
                  {dashboard.data.articles.total.toLocaleString()}
                </p>
                <p className="text-[10px] text-slate-500">{dashboard.data.articles.last_24h} in 24h</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Missing Farsi title</p>
                <p className="text-base font-bold text-slate-900 dark:text-white">
                  {dashboard.data.articles.without_farsi_title.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Bias coverage</p>
                <p className="text-base font-bold text-slate-900 dark:text-white">
                  {dashboard.data.bias_scores.coverage_pct}%
                </p>
              </div>
            </div>
          )}

          {/* Final result */}
          {maintResult && !maintResult.error && (
            <div className="pt-3 border-t border-slate-200 dark:border-slate-800">
              <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 mb-2">Result summary</p>
              <pre className="text-[10px] bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 p-3 overflow-auto max-h-48 text-slate-700 dark:text-slate-300" dir="ltr">
                {JSON.stringify(maintResult, null, 2)}
              </pre>
            </div>
          )}
          {maintResult?.error && (
            <div className="pt-3 border-t border-slate-200 dark:border-slate-800">
              <p className="text-xs font-semibold text-red-600 dark:text-red-400 mb-2">Error</p>
              <p className="text-xs text-slate-700 dark:text-slate-300">{maintResult.error}</p>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 flex justify-end gap-2">
          {running === "maintenance" ? (
            <p className="text-xs text-slate-500 italic">
              You can close this tab — the run continues on the server.
            </p>
          ) : (
            <button
              onClick={() => { setMaintResult(null); setMaintStart(null); setMaintLive(null); }}
              className="px-4 py-2 text-xs font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:opacity-90"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {maintModal}
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

      {/* Diagnostics */}
      <div className="mb-6 border border-slate-200 dark:border-slate-800 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Activity className="h-4 w-4 text-purple-500" /> Diagnostics
          </h2>
          <button
            onClick={fetchDiagnostics}
            disabled={diagLoading}
            className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${diagLoading ? "animate-spin" : ""}`} />
            {diagnostics ? "Refresh" : "Run diagnostics"}
          </button>
        </div>

        {!diagnostics && !diagLoading && (
          <p className="text-xs text-slate-500">
            Click "Run diagnostics" to see why backfills aren't catching up (broken articles, missing LLM keys, clustering gaps).
          </p>
        )}

        {diagnostics && (
          <div className="space-y-4">
            {/* LLM keys */}
            <div className="flex items-center gap-3 text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">LLM keys:</span>
              <span className={`px-2 py-0.5 border ${diagnostics.llm_keys.openai_set ? "border-emerald-400 text-emerald-600" : "border-red-400 text-red-500"}`}>
                OPENAI {diagnostics.llm_keys.openai_set ? "set" : "MISSING"}
              </span>
              <span className={`px-2 py-0.5 border ${diagnostics.llm_keys.anthropic_set ? "border-emerald-400 text-emerald-600" : "border-slate-300 text-slate-500"}`}>
                ANTHROPIC {diagnostics.llm_keys.anthropic_set ? "set" : "not set"}
              </span>
            </div>

            {/* Articles breakdown */}
            <div>
              <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wide mb-2">Articles</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Total</p>
                  <p className="text-lg font-bold text-slate-900 dark:text-white">{diagnostics.articles.total.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">No Farsi title</p>
                  <p className="text-lg font-bold text-amber-600 dark:text-amber-400">{diagnostics.articles.no_title_fa.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">No original title (broken)</p>
                  <p className="text-lg font-bold text-red-600 dark:text-red-400">{diagnostics.articles.no_title_original.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Translatable now</p>
                  <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{diagnostics.articles.translatable_now.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Unprocessed</p>
                  <p className="text-base font-bold text-slate-900 dark:text-white">{diagnostics.articles.unprocessed.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Clustered into story</p>
                  <p className="text-base font-bold text-slate-900 dark:text-white">{diagnostics.articles.clustered_into_story.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Has content/summary</p>
                  <p className="text-base font-bold text-slate-900 dark:text-white">{diagnostics.articles.has_content_or_summary.toLocaleString()}</p>
                </div>
              </div>
            </div>

            {/* Bias scoring breakdown */}
            <div>
              <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wide mb-2">Bias scoring</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Eligible</p>
                  <p className="text-lg font-bold text-slate-900 dark:text-white">{diagnostics.bias.eligible_for_scoring.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Already scored</p>
                  <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{diagnostics.bias.already_scored.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Remaining</p>
                  <p className="text-lg font-bold text-amber-600 dark:text-amber-400">{diagnostics.bias.remaining_to_score.toLocaleString()}</p>
                </div>
                <div className="border border-slate-200 dark:border-slate-800 p-3">
                  <p className="text-[10px] text-slate-400 uppercase">Eligible coverage</p>
                  <p className="text-lg font-bold text-slate-900 dark:text-white">{diagnostics.bias.coverage_of_eligible_pct}%</p>
                </div>
              </div>
            </div>

            {/* Interpretation */}
            <div className="border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/20 p-3 text-xs text-slate-700 dark:text-slate-300 space-y-1">
              <p className="font-bold text-slate-900 dark:text-white">What this means</p>
              {!diagnostics.llm_keys.openai_set && !diagnostics.llm_keys.anthropic_set && (
                <p className="text-red-600 dark:text-red-400">
                  ⚠ No LLM key is set. Add <code>OPENAI_API_KEY</code> or <code>ANTHROPIC_API_KEY</code> to Railway backend Variables. Title translation and bias scoring won't work without one.
                </p>
              )}
              {diagnostics.articles.no_title_original > 50 && (
                <p>
                  <strong>{diagnostics.articles.no_title_original}</strong> articles have no original title at all — ingestion saved them as ghosts. These can never be translated. Consider filtering them out of the UI or deleting them.
                </p>
              )}
              {diagnostics.articles.translatable_now > 0 && diagnostics.llm_keys.openai_set && (
                <p>
                  <strong>{diagnostics.articles.translatable_now}</strong> articles are ready to translate. Click "Run Maintenance" — each run processes up to 300.
                </p>
              )}
              {diagnostics.bias.coverage_of_eligible_pct >= 95 && (
                <p>
                  Bias scoring is essentially complete for eligible articles ({diagnostics.bias.coverage_of_eligible_pct}% of {diagnostics.bias.eligible_for_scoring}). The dashboard's "5%" is misleading — it's measuring against ALL articles including unclusterd ones.
                </p>
              )}
              {diagnostics.articles.clustered_into_story < diagnostics.articles.total * 0.5 && (
                <p>
                  Only <strong>{diagnostics.articles.clustered_into_story}</strong> / {diagnostics.articles.total} articles are clustered into stories. The rest aren't eligible for bias scoring because they never joined a story.
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Recently re-summarized stories */}
      <div className="mb-6 border border-slate-200 dark:border-slate-800 p-5">
        <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Newspaper className="h-4 w-4 text-indigo-500" /> Recently re-summarized stories
            <span className="text-xs font-normal text-slate-400">(verify new LLM output)</span>
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => forceResummarize(5)}
              disabled={forceRunning || recentLoading}
              title="Regenerate summaries on the 5 top trending stories with the current model"
              className="flex items-center gap-1 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/10 px-3 py-1.5 text-xs text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/20 disabled:opacity-50"
            >
              {forceRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : null}
              Test: refresh 5
            </button>
            <button
              onClick={() => forceResummarize(16)}
              disabled={forceRunning || recentLoading}
              title="Regenerate summaries on the 16 homepage-visible stories with premium model + analyst factors"
              className="flex items-center gap-1 border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/10 px-3 py-1.5 text-xs text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/20 disabled:opacity-50"
            >
              Refresh 16
            </button>
            <button
              onClick={fetchRecentSummaries}
              disabled={recentLoading}
              className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${recentLoading ? "animate-spin" : ""}`} />
              {recentSummaries ? "Reload" : "Load"}
            </button>
          </div>
        </div>

        {!recentSummaries && !recentLoading && (
          <p className="text-xs text-slate-500 leading-6">
            Click Load to see the 15 stories with the most recent <code>updated_at</code>. These are the ones freshly summarized by the pipeline. Look for <strong>guillemets « »</strong> around quoted terms and explicit tone labels (هشداردهنده، پیروزمندانه، سوگوار) in <code>bias_explanation_fa</code> — those are signatures of the new gpt-5-mini prompt.
          </p>
        )}

        {recentSummaries && recentSummaries.length === 0 && (
          <p className="text-xs text-slate-500">No summarized stories found.</p>
        )}

        {recentSummaries && recentSummaries.length > 0 && (
          <div className="space-y-3">
            {recentSummaries.map((s: any) => {
              const updatedAt = s.updated_at ? new Date(s.updated_at) : null;
              const minutesAgo = updatedAt ? Math.floor((Date.now() - updatedAt.getTime()) / 60000) : null;
              const isRecent = minutesAgo !== null && minutesAgo < 120;
              const hasGuillemets = s.bias_explanation_fa && /[«»]/.test(s.bias_explanation_fa);
              return (
                <div
                  key={s.id}
                  className={`border p-3 ${isRecent ? "border-emerald-300 dark:border-emerald-800 bg-emerald-50/30 dark:bg-emerald-950/10" : "border-slate-200 dark:border-slate-800"}`}
                  dir="rtl"
                >
                  <div className="flex items-start justify-between gap-3 mb-1">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white flex-1">{s.title_fa}</h3>
                    <div className="flex items-center gap-2 shrink-0 text-[10px] text-slate-500" dir="ltr">
                      {hasGuillemets && (
                        <span className="px-1.5 py-0.5 border border-emerald-400 text-emerald-600">« » new prompt</span>
                      )}
                      {minutesAgo !== null && (
                        <span className={isRecent ? "font-semibold text-emerald-600" : ""}>
                          {minutesAgo < 60 ? `${minutesAgo}m ago` : `${Math.floor(minutesAgo / 60)}h ago`}
                        </span>
                      )}
                      <span>· {s.article_count} articles</span>
                    </div>
                  </div>
                  {s.bias_explanation_fa && (
                    <p className="text-[11px] leading-6 text-slate-700 dark:text-slate-300 mt-2 pr-2 border-r-2 border-slate-200 dark:border-slate-800">
                      <span className="text-slate-400 text-[10px] font-mono" dir="ltr">bias_explanation_fa:</span><br />
                      {s.bias_explanation_fa}
                    </p>
                  )}
                  <div className="flex items-center gap-3 mt-2 text-[10px]" dir="ltr">
                    <a
                      href={`/fa/stories/${s.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      View story →
                    </a>
                    <span className="text-slate-400">{s.id.slice(0, 8)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Data Repair — destructive one-shot actions */}
      <div className="mb-6 border border-red-200 dark:border-red-900/50 bg-red-50/30 dark:bg-red-950/10 p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-500" /> Data Repair
          <span className="text-xs font-normal text-slate-500">(one-shot admin actions)</span>
        </h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={reEmbedAll}
            disabled={repairRunning !== null}
            title="Re-embed all articles with OpenAI text-embedding-3-small. Replaces old TF-IDF vectors with high-quality multilingual embeddings. ~$0.01, ~30 seconds."
            className="flex items-center gap-2 border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/10 px-4 py-2 text-sm text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/20 disabled:opacity-50"
          >
            {repairRunning === "reembed" && <RefreshCw className="h-3 w-3 animate-spin" />}
            Re-embed all articles
          </button>

          <button
            onClick={nullifyLocalhostImages}
            disabled={repairRunning !== null}
            title="Null every article.image_url starting with http://localhost — these are dev-only URLs never migrated to R2. Next maintenance run will re-fetch og:images."
            className="flex items-center gap-2 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/10 px-4 py-2 text-sm text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/20 disabled:opacity-50"
          >
            {repairRunning === "nullify" && <RefreshCw className="h-3 w-3 animate-spin" />}
            Null localhost image URLs
          </button>

          <button
            onClick={unclaimStoryArticles}
            disabled={repairRunning !== null}
            title="Detach all articles from a specific story and hide it. Use this to blow away a badly-clustered story — articles redistribute on the next clustering run."
            className="flex items-center gap-2 border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/10 px-4 py-2 text-sm text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/20 disabled:opacity-50"
          >
            {repairRunning === "unclaim" && <RefreshCw className="h-3 w-3 animate-spin" />}
            Unclaim story articles…
          </button>
        </div>
        <p className="text-[11px] text-slate-500 leading-5 mt-3">
          <strong>Re-embed all articles</strong> — replaces old TF-IDF vectors with OpenAI text-embedding-3-small. Run once after switching embedding models, then new articles get embedded automatically. ~$0.01 total.
          {" "}<strong>Null localhost URLs</strong> — clears broken dev-only image paths.
          {" "}<strong>Unclaim story articles</strong> — detaches all articles from a story and hides it.
        </p>
      </div>

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
