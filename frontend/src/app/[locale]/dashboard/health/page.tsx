"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";
import { formatRelativeTime } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ─────────────────────────────────────────────────────────────
type Status = "ok" | "warn" | "error";

type CostByRow = { purpose?: string; model?: string; provider?: string; calls?: number; cost: number };

type HiddenCost = { name: string; tracked: boolean; where: string; note: string };

type StepInfo = { name: string; elapsed_s: number };

type RunInfo = {
  run_at: string | null;
  status: string;
  duration_s: number;
  step_count: number;
  fail_count: number;
  fails: string[];
  error: string | null;
  slowest_steps?: StepInfo[];
};

type SilentSource = {
  slug: string;
  name: string | null;
  last_article: string | null;
  days_silent: number | null;
};

type Canary = {
  id: string;
  name: string;
  value: number | string;
  threshold: string;
  status: Status;
  why: string;
};

type HealthData = {
  generated_at: string;
  cache_ttl_seconds: number;
  overall_status: Status;
  alerts: Array<{ severity: Status; section: string; id: string; title: string; detail: string }>;
  cost: {
    today: { cost: number; calls: number };
    yesterday: { cost: number; calls: number };
    last_7d_total: number;
    last_30d_total: number;
    avg_per_day_30d: number;
    avg_per_day_7d: number;
    monthly_projection: number;
    monthly_budget: number;
    today_vs_7d_avg_pct: number;
    by_purpose_7d: CostByRow[];
    by_model_7d: CostByRow[];
    by_provider_7d: CostByRow[];
    unpriced_count_7d: number;
    hidden_costs: HiddenCost[];
  };
  maintenance: {
    current_status: string;
    current_step: string | null;
    started_at: string | null;
    lock_age_seconds: number | null;
    stuck_lock: boolean;
    last_run: RunInfo | null;
    recent_runs: RunInfo[];
  };
  pipeline: {
    embedding: { null_pct_24h: number; zero_pct_24h: number; total_24h: number; alert_threshold_pct: number };
    clustering: { articles_24h: number; new_stories_24h: number; halt_alert: boolean };
    translation: {
      no_title_fa_total: number;
      no_title_en_total: number;
      translatable_now: number;
      stuck_unrecoverable: number;
    };
    bias: { eligible: number; scored: number; coverage_pct: number };
  };
  data_integrity: {
    stories: {
      total: number;
      active: number;
      frozen: number;
      archived: number;
      oversized_active: number;
      oversized_total: number;
      null_first_published: number;
      null_centroid_multiarticle: number;
    };
    articles: {
      total: number;
      orphans: number;
      no_embedding: number;
      no_title_fa: number;
      no_title_en: number;
    };
    frozen_recently_bumped: number;
    max_cluster_size: number;
  };
  freshness: {
    trending_count: number;
    oldest_trending_age_days: number;
    trending_under_7d_count: number;
    trending_under_7d_pct: number;
    last_article_minutes_ago: number | null;
  };
  external: {
    telegram: {
      active_channels: number;
      session_status: string;
      minutes_since_last_activity: number | null;
      last_fetch: string | null;
      last_post: string | null;
    };
    rss: {
      active_sources: number;
      silent_24h_count: number;
      silent_7d_count: number;
      silent_7d: SilentSource[];
      silent_24h: SilentSource[];
    };
  };
  canaries: Canary[];
};

// ─── Helpers ───────────────────────────────────────────────────────────
function fmt$(n: number | null | undefined): string {
  if (n == null) return "$0.00";
  if (Math.abs(n) < 0.01 && n !== 0) return "$" + n.toFixed(4);
  return "$" + n.toFixed(2);
}
function fmtNum(n: number | null | undefined): string {
  if (n == null) return "0";
  return n.toLocaleString("en-US");
}
function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n.toFixed(1)}%`;
}
function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  return formatRelativeTime(iso, "en");
}
function statusColors(s: Status): { text: string; bg: string; border: string } {
  if (s === "error")
    return {
      text: "text-red-700 dark:text-red-300",
      bg: "bg-red-50 dark:bg-red-950/30",
      border: "border-red-300 dark:border-red-800",
    };
  if (s === "warn")
    return {
      text: "text-amber-700 dark:text-amber-300",
      bg: "bg-amber-50 dark:bg-amber-950/30",
      border: "border-amber-300 dark:border-amber-800",
    };
  return {
    text: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-50 dark:bg-emerald-950/30",
    border: "border-emerald-300 dark:border-emerald-800",
  };
}
function StatusIcon({ status, className = "w-4 h-4" }: { status: Status; className?: string }) {
  if (status === "error") return <XCircle className={`${className} text-red-500`} />;
  if (status === "warn") return <AlertTriangle className={`${className} text-amber-500`} />;
  return <CheckCircle2 className={`${className} text-emerald-500`} />;
}

// ─── Page ──────────────────────────────────────────────────────────────
export default function HealthPage() {
  // All hooks above the auth check (dashboard hooks trap)
  const [authed, setAuthed] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [openCanary, setOpenCanary] = useState<string | null>(null);
  const [showAllRss, setShowAllRss] = useState(false);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`${API}/api/v1/admin/health/overview`, {
        headers: adminHeaders(),
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = (await r.json()) as HealthData;
      setData(d);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "fetch error";
      setErr(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) fetchHealth();
  }, [authed, fetchHealth]);

  useEffect(() => {
    if (!authed || !autoRefresh) return;
    const id = setInterval(fetchHealth, 60_000);
    return () => clearInterval(id);
  }, [authed, autoRefresh, fetchHealth]);

  const totalByPurpose7d = useMemo(
    () => (data?.cost.by_purpose_7d ?? []).reduce((a, b) => a + (b.cost || 0), 0),
    [data],
  );
  const totalByProvider7d = useMemo(
    () => (data?.cost.by_provider_7d ?? []).reduce((a, b) => a + (b.cost || 0), 0),
    [data],
  );

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
          className="mt-3 px-4 py-2 bg-slate-900 text-white dark:bg-white dark:text-slate-900"
          onClick={() => {
            localStorage.setItem("doornegar_admin_token", tokenInput);
            setAuthed(true);
          }}
        >
          Sign in
        </button>
      </div>
    );
  }

  if (!data && !err) {
    return (
      <div className="p-8 text-center text-slate-500 text-sm">
        <RefreshCw className="w-5 h-5 animate-spin inline-block mr-2" />
        Loading health snapshot…
      </div>
    );
  }

  if (err && !data) {
    return (
      <div className="p-8 max-w-2xl mx-auto">
        <div className="border border-red-300 bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-800 dark:text-red-200 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
        <button
          onClick={fetchHealth}
          className="mt-4 px-4 py-2 border border-slate-300 dark:border-slate-700 hover:border-slate-500 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const statusBanner = statusColors(data.overall_status);
  const errCount = data.alerts.filter((a) => a.severity === "error").length;
  const warnCount = data.alerts.filter((a) => a.severity === "warn").length;
  const budgetPct = data.cost.monthly_budget
    ? (data.cost.monthly_projection / data.cost.monthly_budget) * 100
    : 0;
  const rssToShow = showAllRss
    ? [...data.external.rss.silent_7d, ...data.external.rss.silent_24h]
    : data.external.rss.silent_7d;

  return (
    <div className="text-slate-900 dark:text-slate-100">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <Activity className="w-6 h-6 text-blue-500" />
          <h1 className="text-2xl font-black">Health</h1>
          <span className="text-[11px] text-slate-400 font-mono">
            updated {timeAgo(data.generated_at)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <input
              type="checkbox"
              className="accent-blue-500"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            auto-refresh 60s
          </label>
          <button
            onClick={fetchHealth}
            className="p-2 border border-slate-300 dark:border-slate-700 hover:border-slate-500"
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Overall status banner */}
      <div className={`mb-5 border ${statusBanner.border} ${statusBanner.bg} px-4 py-3 flex items-center gap-3`}>
        <StatusIcon status={data.overall_status} className="w-5 h-5" />
        <div className="flex-1">
          <div className={`text-sm font-bold ${statusBanner.text}`}>
            {data.overall_status === "ok"
              ? "All systems nominal"
              : data.overall_status === "warn"
              ? "Warnings present"
              : "Errors present"}
          </div>
          <div className="text-[11px] text-slate-500">
            {errCount} error{errCount !== 1 ? "s" : ""} · {warnCount} warning{warnCount !== 1 ? "s" : ""} ·{" "}
            {data.canaries.length} canaries · cache TTL {data.cache_ttl_seconds}s
          </div>
        </div>
      </div>

      {/* Alerts list */}
      {data.alerts.length > 0 && (
        <Section title="Active alerts">
          <div className="border border-slate-200 dark:border-slate-800 divide-y divide-slate-200 dark:divide-slate-800">
            {data.alerts.map((a) => (
              <div key={a.id} className="px-3 py-2 flex items-start gap-2 text-sm">
                <StatusIcon status={a.severity} />
                <div className="flex-1">
                  <button
                    onClick={() => setOpenCanary(openCanary === a.id ? null : a.id)}
                    className="text-left hover:underline font-medium"
                  >
                    {a.title}
                  </button>
                  <span className="ml-2 text-slate-500 font-mono text-[11px]">{a.detail}</span>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* COST */}
      <Section title="Cost">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <Tile
            label="Today"
            value={fmt$(data.cost.today.cost)}
            sub={`${fmtNum(data.cost.today.calls)} calls`}
            delta={data.cost.today.cost - data.cost.yesterday.cost}
          />
          <Tile
            label="Yesterday"
            value={fmt$(data.cost.yesterday.cost)}
            sub={`${fmtNum(data.cost.yesterday.calls)} calls`}
          />
          <Tile
            label="Last 30 days"
            value={fmt$(data.cost.last_30d_total)}
            sub={`avg ${fmt$(data.cost.avg_per_day_30d)}/day`}
          />
          <Tile
            label="Monthly projection"
            value={fmt$(data.cost.monthly_projection)}
            sub={`vs $${data.cost.monthly_budget.toFixed(0)} budget`}
            status={
              budgetPct > 100 ? "error" : budgetPct > 80 ? "warn" : "ok"
            }
            progress={budgetPct}
          />
        </div>

        {data.cost.unpriced_count_7d > 0 && (
          <div className="mb-4 border border-amber-300 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            {fmtNum(data.cost.unpriced_count_7d)} unpriced LLM calls (7d) — model not in
            llm_pricing.py. Real cost is hidden until you add pricing.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <BreakdownPanel
            title="By purpose (7d)"
            rows={data.cost.by_purpose_7d.slice(0, 12).map((r) => ({
              key: r.purpose ?? "—",
              cost: r.cost,
              sub: `${fmtNum(r.calls)} calls`,
            }))}
            total={totalByPurpose7d}
          />
          <BreakdownPanel
            title="By provider (7d)"
            rows={data.cost.by_provider_7d.map((r) => ({
              key: r.provider ?? "—",
              cost: r.cost,
            }))}
            total={totalByProvider7d}
          />
        </div>

        <div className="border border-slate-200 dark:border-slate-800">
          <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 flex items-center justify-between">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Hidden / external costs (not in the numbers above)
            </div>
            <span className="text-[10px] text-slate-400">verify monthly</span>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-800">
            {data.cost.hidden_costs.map((h) => (
              <div key={h.name} className="px-3 py-2 flex items-start gap-3 text-xs">
                <span
                  className={`mt-0.5 inline-block w-2 h-2 ${
                    h.tracked ? "bg-emerald-500" : "bg-slate-400"
                  }`}
                  aria-hidden
                />
                <div className="flex-1">
                  <div className="font-bold">{h.name}</div>
                  <div className="text-slate-500 mt-0.5">{h.note}</div>
                </div>
                <div className="text-slate-400 font-mono whitespace-nowrap">{h.where}</div>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* MAINTENANCE */}
      <Section title="Maintenance">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-slate-200 dark:border-slate-800 p-3">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Current state
            </div>
            <div className="text-sm">
              <div className="flex items-center gap-2">
                <StatusIcon
                  status={
                    data.maintenance.stuck_lock
                      ? "error"
                      : data.maintenance.current_status === "running"
                      ? "warn"
                      : "ok"
                  }
                />
                <span className="font-bold uppercase tracking-wider text-xs">
                  {data.maintenance.current_status}
                </span>
                {data.maintenance.current_step && (
                  <span className="text-slate-500 text-xs">
                    · step: <span className="font-mono">{data.maintenance.current_step}</span>
                  </span>
                )}
              </div>
              {data.maintenance.lock_age_seconds != null && (
                <div className="text-xs text-slate-500 mt-1">
                  running for {Math.floor((data.maintenance.lock_age_seconds || 0) / 60)}m{" "}
                  {Math.floor((data.maintenance.lock_age_seconds || 0) % 60)}s
                  {data.maintenance.stuck_lock && (
                    <span className="ml-2 text-red-600 dark:text-red-400 font-bold">
                      STUCK — call /admin/maintenance/force-release-lock
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="border border-slate-200 dark:border-slate-800 p-3">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Last completed run
            </div>
            {data.maintenance.last_run ? (
              <div className="text-sm space-y-1">
                <div>
                  <span className="font-mono text-xs text-slate-500">
                    {data.maintenance.last_run.run_at
                      ? timeAgo(data.maintenance.last_run.run_at)
                      : "—"}
                  </span>
                  <span className="ml-2 text-xs">
                    · {Math.floor(data.maintenance.last_run.duration_s / 60)}m{" "}
                    {Math.floor(data.maintenance.last_run.duration_s % 60)}s
                  </span>
                  <span className="ml-2 text-xs text-slate-500">
                    · {data.maintenance.last_run.step_count} steps
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <StatusIcon
                    status={data.maintenance.last_run.fail_count > 0 ? "warn" : "ok"}
                  />
                  {data.maintenance.last_run.fail_count > 0
                    ? `${data.maintenance.last_run.fail_count} step failures: ${data.maintenance.last_run.fails.join(", ")}`
                    : "all steps ok"}
                </div>
                {data.maintenance.last_run.slowest_steps && data.maintenance.last_run.slowest_steps.length > 0 && (
                  <div className="text-[11px] text-slate-500 mt-2">
                    Slowest:{" "}
                    {data.maintenance.last_run.slowest_steps.map((s, i) => (
                      <span key={s.name} className="font-mono">
                        {s.name} {s.elapsed_s.toFixed(1)}s{i < (data.maintenance.last_run?.slowest_steps?.length ?? 0) - 1 ? " · " : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-slate-400">no runs yet</div>
            )}
          </div>
        </div>

        {data.maintenance.recent_runs.length > 0 && (
          <div className="mt-4 border border-slate-200 dark:border-slate-800">
            <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Recent runs
            </div>
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase text-slate-400">
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left px-3 py-1.5">When</th>
                  <th className="text-left px-3 py-1.5">Status</th>
                  <th className="text-right px-3 py-1.5">Duration</th>
                  <th className="text-right px-3 py-1.5">Steps</th>
                  <th className="text-right px-3 py-1.5">Fails</th>
                  <th className="text-left px-3 py-1.5">Failed steps</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {data.maintenance.recent_runs.map((r, i) => (
                  <tr key={i} className="font-mono">
                    <td className="px-3 py-1.5">{timeAgo(r.run_at)}</td>
                    <td className="px-3 py-1.5">
                      <span
                        className={
                          r.status === "ok"
                            ? "text-emerald-600"
                            : r.fail_count > 0
                            ? "text-amber-600"
                            : "text-red-600"
                        }
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {Math.floor(r.duration_s / 60)}m {Math.floor(r.duration_s % 60)}s
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-500">{r.step_count}</td>
                    <td className={`px-3 py-1.5 text-right ${r.fail_count > 0 ? "text-amber-600" : "text-slate-400"}`}>
                      {r.fail_count}
                    </td>
                    <td className="px-3 py-1.5 text-slate-500 text-[10px]">
                      {r.fails.slice(0, 4).join(", ")}
                      {r.fails.length > 4 ? ` +${r.fails.length - 4}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* PIPELINE */}
      <Section title="Pipeline">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile
            label="Embedding zero-rate (24h)"
            value={`${data.pipeline.embedding.zero_pct_24h}%`}
            sub={`${fmtNum(data.pipeline.embedding.total_24h)} sample`}
            status={
              data.pipeline.embedding.zero_pct_24h >= 10
                ? "error"
                : data.pipeline.embedding.zero_pct_24h >= 1
                ? "warn"
                : "ok"
            }
          />
          <Tile
            label="Embedding NULL-rate (24h)"
            value={`${data.pipeline.embedding.null_pct_24h}%`}
            status={
              data.pipeline.embedding.null_pct_24h >= 10
                ? "error"
                : data.pipeline.embedding.null_pct_24h >= 5
                ? "warn"
                : "ok"
            }
          />
          <Tile
            label="Articles in 24h"
            value={fmtNum(data.pipeline.clustering.articles_24h)}
            sub={`${fmtNum(data.pipeline.clustering.new_stories_24h)} new stories`}
            status={data.pipeline.clustering.halt_alert ? "error" : "ok"}
          />
          <Tile
            label="Bias coverage"
            value={`${data.pipeline.bias.coverage_pct}%`}
            sub={`${fmtNum(data.pipeline.bias.scored)} / ${fmtNum(data.pipeline.bias.eligible)} eligible`}
            status={data.pipeline.bias.coverage_pct >= 70 ? "ok" : data.pipeline.bias.coverage_pct >= 30 ? "warn" : "error"}
          />
          <Tile
            label="Translation backlog (FA)"
            value={fmtNum(data.pipeline.translation.translatable_now)}
            sub={`${fmtNum(data.pipeline.translation.stuck_unrecoverable)} unrecoverable`}
            status={data.pipeline.translation.translatable_now > 200 ? "warn" : "ok"}
          />
          <Tile
            label="Articles missing title_fa"
            value={fmtNum(data.pipeline.translation.no_title_fa_total)}
            sub="total"
          />
          <Tile
            label="Articles missing title_en"
            value={fmtNum(data.pipeline.translation.no_title_en_total)}
            sub="total"
          />
          <Tile
            label="Last article ingested"
            value={
              data.freshness.last_article_minutes_ago != null
                ? `${data.freshness.last_article_minutes_ago}m ago`
                : "never"
            }
            status={
              data.freshness.last_article_minutes_ago != null && data.freshness.last_article_minutes_ago > 360
                ? "warn"
                : "ok"
            }
          />
        </div>
      </Section>

      {/* DATA INTEGRITY */}
      <Section title="Data integrity">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-slate-200 dark:border-slate-800">
            <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Stories
            </div>
            <div className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
              <KV k="Total" v={fmtNum(data.data_integrity.stories.total)} />
              <KV k="Active (frozen=null, archived=null)" v={fmtNum(data.data_integrity.stories.active)} />
              <KV k="Frozen" v={fmtNum(data.data_integrity.stories.frozen)} />
              <KV k="Archived" v={fmtNum(data.data_integrity.stories.archived)} />
              <KV
                k={`Active oversized (≥${data.data_integrity.max_cluster_size} articles, not frozen)`}
                v={fmtNum(data.data_integrity.stories.oversized_active)}
                sub={`${fmtNum(data.data_integrity.stories.oversized_total)} historical incl. frozen`}
                status={data.data_integrity.stories.oversized_active > 0 ? "error" : "ok"}
              />
              <KV
                k="NULL first_published_at"
                v={fmtNum(data.data_integrity.stories.null_first_published)}
                status={data.data_integrity.stories.null_first_published > 50 ? "warn" : "ok"}
              />
              <KV
                k="Multi-article without centroid"
                v={fmtNum(data.data_integrity.stories.null_centroid_multiarticle)}
                status={data.data_integrity.stories.null_centroid_multiarticle > 0 ? "warn" : "ok"}
              />
              <KV
                k="Frozen bumped after freeze (1h)"
                v={fmtNum(data.data_integrity.frozen_recently_bumped)}
                status={data.data_integrity.frozen_recently_bumped > 0 ? "error" : "ok"}
              />
            </div>
          </div>
          <div className="border border-slate-200 dark:border-slate-800">
            <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Articles
            </div>
            <div className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
              <KV k="Total" v={fmtNum(data.data_integrity.articles.total)} />
              <KV
                k="Orphans (no story)"
                v={fmtNum(data.data_integrity.articles.orphans)}
                sub={
                  data.data_integrity.articles.total
                    ? `${((data.data_integrity.articles.orphans / data.data_integrity.articles.total) * 100).toFixed(1)}%`
                    : undefined
                }
              />
              <KV
                k="Missing embedding"
                v={fmtNum(data.data_integrity.articles.no_embedding)}
              />
              <KV
                k="Missing title_fa"
                v={fmtNum(data.data_integrity.articles.no_title_fa)}
              />
              <KV
                k="Missing title_en"
                v={fmtNum(data.data_integrity.articles.no_title_en)}
              />
            </div>
          </div>
        </div>
      </Section>

      {/* FRESHNESS */}
      <Section title="Freshness">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile
            label="Trending stories"
            value={fmtNum(data.freshness.trending_count)}
            sub={`${data.freshness.trending_under_7d_count} under 7d`}
          />
          <Tile
            label="Oldest trending age"
            value={`${data.freshness.oldest_trending_age_days.toFixed(1)}d`}
            status={data.freshness.oldest_trending_age_days >= 7 ? "error" : "ok"}
          />
          <Tile
            label="Trending under 7 days"
            value={fmtPct(data.freshness.trending_under_7d_pct)}
            status={data.freshness.trending_under_7d_pct >= 100 ? "ok" : data.freshness.trending_under_7d_pct >= 80 ? "warn" : "error"}
          />
          <Tile
            label="Last article"
            value={
              data.freshness.last_article_minutes_ago != null
                ? `${data.freshness.last_article_minutes_ago}m ago`
                : "—"
            }
          />
        </div>
      </Section>

      {/* EXTERNAL */}
      <Section title="External dependencies">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-slate-200 dark:border-slate-800">
            <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
              Telegram
              <StatusIcon
                status={
                  data.external.telegram.session_status === "ok"
                    ? "ok"
                    : data.external.telegram.session_status === "broken"
                    ? "error"
                    : "warn"
                }
              />
            </div>
            <div className="divide-y divide-slate-200 dark:divide-slate-800 text-sm">
              <KV k="Active channels" v={fmtNum(data.external.telegram.active_channels)} />
              <KV
                k="Session status"
                v={data.external.telegram.session_status}
                status={
                  data.external.telegram.session_status === "ok"
                    ? "ok"
                    : data.external.telegram.session_status === "broken"
                    ? "error"
                    : "warn"
                }
              />
              <KV
                k="Last fetch"
                v={timeAgo(data.external.telegram.last_fetch)}
              />
              <KV
                k="Last post"
                v={timeAgo(data.external.telegram.last_post)}
              />
            </div>
          </div>
          <div className="border border-slate-200 dark:border-slate-800">
            <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center justify-between">
              <span>RSS sources</span>
              <span className="text-slate-400">
                {data.external.rss.active_sources} active ·{" "}
                <span className={data.external.rss.silent_7d_count > 0 ? "text-amber-600" : ""}>
                  {data.external.rss.silent_7d_count} silent 7d
                </span>{" "}
                ·{" "}
                <span className={data.external.rss.silent_24h_count > 0 ? "text-slate-500" : ""}>
                  {data.external.rss.silent_24h_count} silent 24h
                </span>
              </span>
            </div>
            <div className="divide-y divide-slate-200 dark:divide-slate-800 text-xs">
              {rssToShow.length === 0 && (
                <div className="px-3 py-3 text-slate-500 text-center">All sources fresh.</div>
              )}
              {rssToShow.map((s) => (
                <div key={s.slug} className="px-3 py-1.5 flex items-center justify-between">
                  <div>
                    <span className="font-mono text-slate-500">{s.slug}</span>
                    {s.name && <span className="ml-2 text-slate-700 dark:text-slate-300">{s.name}</span>}
                  </div>
                  <div className="text-slate-400 font-mono text-[11px]">
                    {s.days_silent != null ? `${s.days_silent}d silent` : "no articles ever"}
                  </div>
                </div>
              ))}
            </div>
            {(data.external.rss.silent_24h.length > 0 || data.external.rss.silent_7d.length > 0) && (
              <div className="px-3 py-2 border-t border-slate-200 dark:border-slate-800 text-[11px]">
                <button
                  onClick={() => setShowAllRss((v) => !v)}
                  className="text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {showAllRss ? "show only 7d-silent" : "show all silent (24h + 7d)"}
                </button>
              </div>
            )}
          </div>
        </div>
      </Section>

      {/* CANARIES */}
      <Section title="Canaries">
        <p className="text-xs text-slate-500 mb-3 max-w-3xl">
          Each canary is a tripwire that has caught a real bug. Click any row to see why it
          matters and how to investigate when it trips.
        </p>
        <div className="border border-slate-200 dark:border-slate-800 divide-y divide-slate-200 dark:divide-slate-800">
          {data.canaries.map((c) => {
            const open = openCanary === c.id;
            return (
              <div key={c.id}>
                <button
                  onClick={() => setOpenCanary(open ? null : c.id)}
                  className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-900/30"
                >
                  {open ? (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  )}
                  <StatusIcon status={c.status} />
                  <div className="flex-1 text-sm">{c.name}</div>
                  <div className="text-sm font-mono">{String(c.value)}</div>
                  <div className="text-[11px] text-slate-400 font-mono w-32 text-right">
                    {c.threshold}
                  </div>
                </button>
                {open && (
                  <div className="px-12 py-3 bg-slate-50 dark:bg-slate-900/40 text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                    {c.why}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Section>

      <div className="text-[11px] text-slate-400 mt-8 mb-2 font-mono">
        Source: GET /api/v1/admin/health/overview · cache {data.cache_ttl_seconds}s · generated{" "}
        {data.generated_at}
      </div>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-7">
      <h2 className="text-sm font-black mb-3 border-b border-slate-200 dark:border-slate-800 pb-1.5 uppercase tracking-wider">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Tile({
  label,
  value,
  sub,
  delta,
  status,
  progress,
}: {
  label: string;
  value: string;
  sub?: string;
  delta?: number;
  status?: Status;
  progress?: number;
}) {
  const colors = status ? statusColors(status) : null;
  return (
    <div
      className={`border ${
        colors ? colors.border : "border-slate-200 dark:border-slate-800"
      } p-3 ${colors ? colors.bg : ""}`}
    >
      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`mt-1 text-xl font-black ${colors ? colors.text : ""}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>}
      {delta != null && delta !== 0 && (
        <div className={`mt-0.5 text-[10px] ${delta > 0 ? "text-red-500" : "text-emerald-500"}`}>
          {delta > 0 ? "↑" : "↓"} {fmt$(Math.abs(delta))} vs yesterday
        </div>
      )}
      {progress != null && (
        <div className="mt-2 h-1 bg-slate-100 dark:bg-slate-900 relative">
          <div
            className={`absolute inset-y-0 left-0 ${
              progress > 100 ? "bg-red-500" : progress > 80 ? "bg-amber-500" : "bg-emerald-500"
            }`}
            style={{ width: `${Math.min(100, progress)}%` }}
          />
        </div>
      )}
    </div>
  );
}

function BreakdownPanel({
  title,
  rows,
  total,
}: {
  title: string;
  rows: { key: string; cost: number; sub?: string }[];
  total: number;
}) {
  return (
    <div className="border border-slate-200 dark:border-slate-800">
      <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
        {title}
      </div>
      <div className="divide-y divide-slate-200 dark:divide-slate-800">
        {rows.length === 0 && (
          <div className="px-3 py-4 text-center text-xs text-slate-400">no data</div>
        )}
        {rows.map((r) => {
          const pct = total > 0 ? (r.cost / total) * 100 : 0;
          return (
            <div key={r.key} className="px-3 py-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono text-slate-600 dark:text-slate-300">{r.key}</span>
                <span className="font-mono font-bold">{fmt$(r.cost)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 h-1 bg-slate-100 dark:bg-slate-900 relative">
                  <div
                    className="absolute inset-y-0 left-0 bg-blue-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-[10px] text-slate-400 font-mono w-10 text-right">
                  {pct.toFixed(1)}%
                </span>
              </div>
              {r.sub && <div className="mt-0.5 text-[10px] text-slate-400">{r.sub}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function KV({
  k,
  v,
  sub,
  status,
}: {
  k: string;
  v: string;
  sub?: string;
  status?: Status;
}) {
  const colors = status ? statusColors(status) : null;
  return (
    <div className="px-3 py-1.5 flex items-center justify-between text-xs">
      <span className="text-slate-600 dark:text-slate-400">{k}</span>
      <span className={`font-mono font-bold ${colors ? colors.text : ""}`}>
        {v}
        {sub && <span className="ml-1 text-slate-400 font-normal">({sub})</span>}
      </span>
    </div>
  );
}
