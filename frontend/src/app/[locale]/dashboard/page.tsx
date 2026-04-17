"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Activity, AlertTriangle, ArrowRight, CheckCircle, Circle, Clock, CreditCard,
  Database, Inbox, ListChecks, MessageSquare, Newspaper, RefreshCw,
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

interface FeedbackItem {
  id: string;
  target_type: string;
  target_id: string;
  issue_type: string;
  current_value?: string;
  suggested_value?: string;
  reason?: string;
  status: string;
  created_at: string;
  device_info?: any;
  context_label?: string;
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

export default function DashboardPage() {
  const [authed, setAuthed] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authChecking, setAuthChecking] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [adminToken, setAdminToken] = useState("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("doornegar_admin_token");
      if (token) {
        setAdminToken(token);
        setAuthed(true);
      }
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
    const interval = setInterval(() => { fetchDashboard(); }, 30000); // 30s not 5s — saves Neon transfer
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
    const interval = setInterval(poll, 4000); // 4s for responsive progress display
    return () => clearInterval(interval);
  }, [running, authHeaders, fetchDashboard]);

  // Niloofar audit
  const [niloofarRunning, setNiloofarRunning] = useState(false);
  const [niloofarResult, setNiloofarResult] = useState<any>(null);
  const [niloofarOpen, setNiloofarOpen] = useState(false);

  const [niloofarApplying, setNiloofarApplying] = useState<Record<number, string>>({});

  const triggerNiloofarAudit = useCallback(async () => {
    setNiloofarRunning(true);
    setNiloofarResult(null);
    setNiloofarApplying({});
    setNiloofarOpen(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/niloofar/audit`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      setNiloofarResult(data);
    } catch (e: any) {
      setNiloofarResult({ error: e.message || "Unknown error" });
    }
    setNiloofarRunning(false);
  }, [authHeaders]);

  const applyNiloofarFix = useCallback(async (findingIndex: number) => {
    setNiloofarApplying(prev => ({ ...prev, [findingIndex]: "applying" }));
    try {
      const res = await fetch(`${API}/api/v1/admin/niloofar/apply-fix?fix_index=${findingIndex}`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      setNiloofarApplying(prev => ({ ...prev, [findingIndex]: data.status === "ok" ? "done" : "error" }));
    } catch {
      setNiloofarApplying(prev => ({ ...prev, [findingIndex]: "error" }));
    }
  }, [authHeaders]);

  const applyAllNiloofarFixes = useCallback(async () => {
    setNiloofarRunning(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/niloofar/audit?apply=true`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      setNiloofarResult(data);
      // Mark all as done
      const allDone: Record<number, string> = {};
      (data?.report?.findings || []).forEach((_: any, i: number) => { allDone[i] = "done"; });
      setNiloofarApplying(allDone);
    } catch (e: any) {
      setNiloofarResult({ error: e.message });
    }
    setNiloofarRunning(false);
  }, [authHeaders]);

  // Feedback & Suggestions
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackCounts, setFeedbackCounts] = useState<{ total: number; open: number; in_progress: number; done: number }>({ total: 0, open: 0, in_progress: 0, done: 0 });

  const fetchFeedback = useCallback(async () => {
    if (!authed) return;
    setFeedbackLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/improvements/admin`, { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        const items: FeedbackItem[] = Array.isArray(data) ? data : (data.items || []);
        setFeedback(items);
        const total = items.length;
        const open = items.filter((i: FeedbackItem) => i.status === "open").length;
        const in_progress = items.filter((i: FeedbackItem) => i.status === "in_progress").length;
        const done = items.filter((i: FeedbackItem) => i.status === "done").length;
        setFeedbackCounts({ total, open, in_progress, done });
      }
    } catch {}
    setFeedbackLoading(false);
  }, [authed, authHeaders]);

  useEffect(() => { fetchFeedback(); }, [fetchFeedback]);

  // Persona info tooltip
  const [activePersona, setActivePersona] = useState<string | null>(null);

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Admin Dashboard</h1>
        <p className="text-sm text-slate-500 mb-4">Paste the backend <code>ADMIN_TOKEN</code> (from Railway env).</p>
        <form onSubmit={async (e) => {
          e.preventDefault();
          const candidate = tokenInput.trim();
          if (!candidate) return;
          setAuthChecking(true);
          setAuthError(null);
          try {
            const res = await fetch(`${API}/api/v1/admin/dashboard`, {
              headers: { Authorization: `Bearer ${candidate}` },
            });
            if (res.ok) {
              localStorage.setItem("doornegar_admin_token", candidate);
              setAdminToken(candidate);
              setAuthed(true);
            } else if (res.status === 401 || res.status === 403) {
              setAuthError("Invalid token");
            } else {
              setAuthError(`Unexpected response: HTTP ${res.status}`);
            }
          } catch (err: any) {
            setAuthError(err?.message || "Network error");
          }
          setAuthChecking(false);
        }}>
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="ADMIN_TOKEN"
            autoComplete="off"
            className="w-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white px-3 py-2 text-sm mb-3 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={authChecking || !tokenInput.trim()}
            className="w-full bg-slate-900 dark:bg-white text-white dark:text-slate-900 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {authChecking ? "Verifying…" : "Access Dashboard"}
          </button>
          {authError && (
            <p className="mt-3 text-sm text-red-500">{authError}</p>
          )}
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
                const total = maintLive.total_steps || 14;
                const done = (maintLive.steps || []).length;
                const pct = Math.min(100, Math.round((done / total) * 100));
                const currentStepTime = maintLive.current_step_elapsed_s || 0;
                return (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[10px] text-slate-500">
                      <span>Step {done + 1} of {total}</span>
                      <span>{pct}%</span>
                    </div>
                    <div className="h-2 w-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                      <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${pct}%` }} />
                    </div>
                    {currentStepTime > 60 && (
                      <p className="text-[10px] text-amber-600 dark:text-amber-400">
                        Current step running for {Math.floor(currentStepTime / 60)}min — long steps (ingest, cluster, summarize) can take 10-30 min each
                      </p>
                    )}
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

      {/* Feedback & Suggestions Overview */}
      <div className="mb-6 border border-slate-200 dark:border-slate-800 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Inbox className="h-4 w-4 text-purple-500" /> Feedback & Suggestions
          </h2>
          <button
            onClick={fetchFeedback}
            disabled={feedbackLoading}
            className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${feedbackLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {/* Summary counts */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="border border-slate-200 dark:border-slate-800 p-3">
            <p className="text-[10px] text-slate-400 uppercase">Total</p>
            <p className="text-lg font-bold text-slate-900 dark:text-white">{feedbackCounts.total}</p>
          </div>
          <div className="border border-amber-200 dark:border-amber-900/50 bg-amber-50/30 dark:bg-amber-950/10 p-3">
            <p className="text-[10px] text-amber-600 dark:text-amber-400 uppercase">Open</p>
            <p className="text-lg font-bold text-amber-600 dark:text-amber-400">{feedbackCounts.open}</p>
          </div>
          <div className="border border-blue-200 dark:border-blue-900/50 bg-blue-50/30 dark:bg-blue-950/10 p-3">
            <p className="text-[10px] text-blue-600 dark:text-blue-400 uppercase">In Progress</p>
            <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{feedbackCounts.in_progress}</p>
          </div>
          <div className="border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/10 p-3">
            <p className="text-[10px] text-emerald-600 dark:text-emerald-400 uppercase">Done</p>
            <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{feedbackCounts.done}</p>
          </div>
        </div>

        {/* Recent open/in_progress items */}
        {(() => {
          const activeItems = feedback
            .filter((item) => item.status === "open" || item.status === "in_progress")
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
            .slice(0, 5);

          if (activeItems.length === 0) {
            return (
              <p className="text-xs text-slate-500">
                {feedbackCounts.total === 0 ? "No feedback submitted yet." : "All feedback items are resolved."}
              </p>
            );
          }

          const issueTypeBadge = (type: string) => {
            const map: Record<string, { label: string; color: string }> = {
              wrong_title: { label: "Wrong title", color: "border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/10" },
              bad_image: { label: "Bad image", color: "border-amber-300 dark:border-amber-700 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/10" },
              merge_stories: { label: "Merge stories", color: "border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/10" },
              priority_higher: { label: "Priority higher", color: "border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/10" },
              priority_lower: { label: "Priority lower", color: "border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/10" },
              wrong_summary: { label: "Wrong summary", color: "border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/10" },
              wrong_bias: { label: "Wrong bias", color: "border-amber-300 dark:border-amber-700 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/10" },
              other: { label: "Other", color: "border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/10" },
            };
            const info = map[type] || { label: type.replace(/_/g, " "), color: "border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/10" };
            return (
              <span className={`px-1.5 py-0.5 text-[10px] border ${info.color} whitespace-nowrap`}>
                {info.label}
              </span>
            );
          };

          const targetBadge = (type: string) => {
            return (
              <span className="px-1.5 py-0.5 text-[10px] border border-slate-200 dark:border-slate-700 text-slate-500 whitespace-nowrap">
                {type.replace(/_/g, " ")}
              </span>
            );
          };

          const relativeTime = (iso: string) => {
            try {
              const diff = Date.now() - new Date(iso).getTime();
              const mins = Math.floor(diff / 60000);
              if (mins < 60) return `${mins}m ago`;
              const hours = Math.floor(mins / 60);
              if (hours < 24) return `${hours}h ago`;
              const days = Math.floor(hours / 24);
              return `${days}d ago`;
            } catch {
              return "";
            }
          };

          return (
            <div className="space-y-0 border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800/50">
              {activeItems.map((item) => (
                <div key={item.id} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="flex items-center gap-2 shrink-0">
                    {issueTypeBadge(item.issue_type)}
                    {targetBadge(item.target_type)}
                  </div>
                  <p className="flex-1 text-xs text-slate-700 dark:text-slate-300 truncate min-w-0">
                    {item.context_label || item.reason || item.suggested_value || "—"}
                  </p>
                  <div className="flex items-center gap-2 shrink-0">
                    {item.status === "in_progress" && (
                      <span className="px-1.5 py-0.5 text-[10px] border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/10">
                        in progress
                      </span>
                    )}
                    <span className="text-[10px] text-slate-400 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {relativeTime(item.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          );
        })()}

        {/* Link to full improvements page */}
        <div className="mt-3 flex justify-end">
          <a
            href="./dashboard/improvements"
            className="flex items-center gap-1 text-xs text-purple-600 dark:text-purple-400 hover:underline"
          >
            View all feedback <ArrowRight className="h-3 w-3" />
          </a>
        </div>
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

      {/* Niloofar Editor Audit */}
      <div className="mb-6 border border-violet-200 dark:border-violet-900/50 bg-violet-50/30 dark:bg-violet-950/10 p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Activity className="h-4 w-4 text-violet-500" /> Niloofar Editor Audit
            <span className="text-xs font-normal text-slate-500" dir="rtl">نیلوفر — ویراستار</span>
          </h2>
          <button
            onClick={triggerNiloofarAudit}
            disabled={niloofarRunning}
            className="flex items-center gap-2 border border-violet-300 dark:border-violet-700 bg-violet-100 dark:bg-violet-900/20 px-4 py-2 text-sm font-medium text-violet-700 dark:text-violet-300 hover:bg-violet-200 dark:hover:bg-violet-900/30 disabled:opacity-50"
          >
            {niloofarRunning && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
            {niloofarRunning ? "در حال بررسی..." : "Run Audit"}
          </button>
        </div>

        {niloofarOpen && (
          <div className="mt-3">
            {niloofarRunning && !niloofarResult && (
              <div className="flex items-center gap-2 text-xs text-slate-500 py-4">
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                <span dir="rtl">نیلوفر در حال بررسی محتوا...</span>
              </div>
            )}
            {niloofarResult && niloofarResult.error && (
              <div className="border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/10 p-3 text-xs text-red-700 dark:text-red-400">
                Error: {niloofarResult.error}
              </div>
            )}
            {niloofarResult?.report && (
              <div dir="rtl">
                {/* Grade + summary */}
                <div className="flex items-center gap-3 mb-3">
                  <span className={`text-2xl font-black ${
                    niloofarResult.report.overall_grade === "A" ? "text-emerald-500" :
                    niloofarResult.report.overall_grade === "B" ? "text-blue-500" :
                    niloofarResult.report.overall_grade === "C" ? "text-amber-500" : "text-red-500"
                  }`}>{niloofarResult.report.overall_grade}</span>
                  <p className="text-[12px] text-slate-600 dark:text-slate-400 leading-5">{niloofarResult.report.summary}</p>
                </div>

                {/* Apply all button */}
                <button
                  onClick={applyAllNiloofarFixes}
                  disabled={niloofarRunning}
                  className="mb-4 flex items-center gap-2 border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-4 py-2 text-sm font-medium text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 disabled:opacity-50"
                >
                  {niloofarRunning ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5" />}
                  اعمال همه اصلاحات
                </button>

                {/* Findings list */}
                <div className="space-y-3">
                  {(niloofarResult.report.findings || []).map((f: any, i: number) => {
                    const sevColor = f.severity === "critical" ? "border-red-400 bg-red-50/50 dark:bg-red-900/10" :
                      f.severity === "high" ? "border-orange-400 bg-orange-50/50 dark:bg-orange-900/10" :
                      f.severity === "medium" ? "border-amber-300 bg-amber-50/50 dark:bg-amber-900/10" :
                      "border-slate-200 bg-slate-50/50 dark:bg-slate-800/30";
                    const applyState = niloofarApplying[i];
                    return (
                      <div key={i} className={`border-r-4 ${sevColor} p-3`}>
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <p className="text-[12px] font-bold text-slate-800 dark:text-slate-200 mb-1">
                              {f.type === "bad_title" ? "عنوان نادرست" :
                               f.type === "irrelevant_article" ? "مقاله نامرتبط" :
                               f.type === "merge_stories" ? "ادغام موضوعات" :
                               f.type === "bad_summary" ? "خلاصه ضعیف" :
                               f.type === "stale_story" ? "موضوع کهنه" :
                               f.type === "source_silence" ? "سکوت منابع" :
                               f.type === "pipeline_suggestion" ? "پیشنهاد سیستمی" :
                               f.type || "سایر"}
                            </p>
                            <p className="text-[11px] text-slate-500 mb-1 truncate">{f.story_title}</p>
                            <p className="text-[12px] text-slate-700 dark:text-slate-300 leading-5">{f.description_fa}</p>
                            <p className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-1">← {f.proposed_fix}</p>
                          </div>
                          <div className="shrink-0">
                            {applyState === "done" ? (
                              <span className="text-[11px] text-emerald-500 font-medium flex items-center gap-1">
                                <CheckCircle className="h-3.5 w-3.5" /> اعمال شد
                              </span>
                            ) : applyState === "applying" ? (
                              <RefreshCw className="h-3.5 w-3.5 text-blue-500 animate-spin" />
                            ) : applyState === "error" ? (
                              <span className="text-[11px] text-red-500">خطا</span>
                            ) : f.fix_type !== "pipeline_change" ? (
                              <button
                                onClick={() => applyNiloofarFix(i)}
                                className="text-[11px] border border-violet-300 dark:border-violet-700 px-3 py-1 text-violet-600 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-900/20"
                              >
                                اعمال
                              </button>
                            ) : (
                              <span className="text-[10px] text-slate-400">سیستمی</span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Applied results */}
                {niloofarResult.applied && (
                  <div className="mt-3 border-t border-slate-200 dark:border-slate-800 pt-3">
                    <p className="text-[11px] font-bold text-slate-500 mb-2">نتایج اعمال:</p>
                    {niloofarResult.applied.map((r: string, i: number) => (
                      <p key={i} className="text-[11px] text-slate-600 dark:text-slate-400">{r}</p>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => { setNiloofarOpen(false); setNiloofarResult(null); setNiloofarApplying({}); }}
                  className="mt-3 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                >
                  بستن
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Claude Persona Audits */}
      <div className="mb-6 border border-slate-200 dark:border-slate-800 p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-slate-400" /> Claude Persona Audits
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {([
            { key: "dariush", name: "Dariush", nameFa: "داریوش", role: "Data Health Check",
              desc: "Checks pipeline data quality, missing fields, stale articles, and embedding coverage.",
              border: "border-emerald-200 dark:border-emerald-900/50", bg: "bg-emerald-50/30 dark:bg-emerald-950/10",
              accent: "text-emerald-600 dark:text-emerald-400",
              btnClass: "border-emerald-300 dark:border-emerald-700 bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-200 dark:hover:bg-emerald-900/30" },
            { key: "sara", name: "Sara", nameFa: "سارا", role: "UX Review",
              desc: "Reviews frontend usability, layout issues, RTL bugs, and mobile responsiveness.",
              border: "border-pink-200 dark:border-pink-900/50", bg: "bg-pink-50/30 dark:bg-pink-950/10",
              accent: "text-pink-600 dark:text-pink-400",
              btnClass: "border-pink-300 dark:border-pink-700 bg-pink-100 dark:bg-pink-900/20 text-pink-700 dark:text-pink-300 hover:bg-pink-200 dark:hover:bg-pink-900/30" },
            { key: "kamran", name: "Kamran", nameFa: "کامران", role: "Geopolitical Analysis",
              desc: "Validates geopolitical framing, factional labels, and source classification accuracy.",
              border: "border-sky-200 dark:border-sky-900/50", bg: "bg-sky-50/30 dark:bg-sky-950/10",
              accent: "text-sky-600 dark:text-sky-400",
              btnClass: "border-sky-300 dark:border-sky-700 bg-sky-100 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 hover:bg-sky-200 dark:hover:bg-sky-900/30" },
            { key: "mina", name: "Mina", nameFa: "مینا", role: "Translation Check",
              desc: "Audits Persian-English translations, title quality, and bilingual consistency.",
              border: "border-amber-200 dark:border-amber-900/50", bg: "bg-amber-50/30 dark:bg-amber-950/10",
              accent: "text-amber-600 dark:text-amber-400",
              btnClass: "border-amber-300 dark:border-amber-700 bg-amber-100 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/30" },
            { key: "reza", name: "Reza", nameFa: "رضا", role: "Bias Self-Audit",
              desc: "Reviews bias scores, LLM prompt fairness, and checks for systematic scoring drift.",
              border: "border-red-200 dark:border-red-900/50", bg: "bg-red-50/30 dark:bg-red-950/10",
              accent: "text-red-600 dark:text-red-400",
              btnClass: "border-red-300 dark:border-red-700 bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/30" },
          ] as const).map(p => (
              <div key={p.key} className={`border ${p.border} ${p.bg} p-4 flex flex-col`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-sm font-bold ${p.accent}`}>{p.name}</span>
                  <span className="text-xs text-slate-500" dir="rtl">{p.nameFa}</span>
                </div>
                <p className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">{p.role}</p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-4 mb-3 flex-1">{p.desc}</p>
                <button
                  onClick={() => setActivePersona(activePersona === p.key ? null : p.key)}
                  className={`flex items-center justify-center gap-1.5 border px-3 py-1.5 text-xs font-medium transition-colors ${p.btnClass}`}
                >
                  <MessageSquare className="h-3 w-3" />
                  {activePersona === p.key ? "Got it" : "How to Run"}
                </button>
                {activePersona === p.key && (
                  <p className="mt-2 text-[11px] text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/50 p-2 leading-4">
                    Run this persona in Claude chat by saying: <span className="font-mono font-bold">&quot;Run {p.name} audit&quot;</span>
                  </p>
                )}
              </div>
          ))}
        </div>
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
            { label: "Conservative", count: d.sources.state, color: "bg-red-500" },
            { label: "Opposition", count: d.sources.diaspora, color: "bg-blue-500" },
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

      {/* Fetch stats link */}
      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Fetch stats</h2>
          <p className="text-xs text-slate-500 mt-1">Per-source article counts and per-channel Telegram post counts — drill down to see the latest items</p>
        </div>
        <a href="./dashboard/fetch-stats" className="border border-cyan-300 dark:border-cyan-700 bg-cyan-50 dark:bg-cyan-900/10 px-4 py-2 text-sm text-cyan-700 dark:text-cyan-300 hover:bg-cyan-100 dark:hover:bg-cyan-900/20">
          View Fetch Stats →
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

      {/* Edit stories link — hand-edit titles and narratives */}
      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Edit Stories</h2>
          <p className="text-xs text-slate-500 mt-1">
            Hand-edit titles, narratives, and bias comparison for the top 15 trending stories. Edits are preserved against nightly regeneration.
          </p>
        </div>
        <a href="./dashboard/edit-stories" className="border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/10 px-4 py-2 text-sm text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/20">
          Open Editor →
        </a>
      </div>
    </div>
  );
}
