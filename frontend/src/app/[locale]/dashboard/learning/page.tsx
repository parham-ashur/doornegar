"use client";

// /dashboard/learning — feedback-impact telemetry. Two tabs:
//   1. Events: recent story_events from feedback + clustering decisions.
//   2. Source trust: per-source cluster_quality_score + 30d flag rate.
// Drives Parham's view of "what stories the system is correcting because
// of feedback, and which sources are getting penalized." All data is
// computed server-side from story_events + rater_feedback +
// improvement_feedback; no client-side aggregation.

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { RefreshCw, ArrowRight } from "lucide-react";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type EventItem = {
  id: string;
  event_type: string;
  actor: string;
  story_id: string | null;
  article_id: string | null;
  story_title: string | null;
  article_title: string | null;
  signals: Record<string, unknown>;
  confidence: number | null;
  created_at: string | null;
};

type SourceTrust = {
  source_id: string;
  slug: string;
  name_fa: string;
  name_en: string;
  state_alignment: string;
  cluster_quality_score: number;
  articles_30d: number;
  flagged_30d: number;
  flag_rate_30d: number;
};

const EVENT_LABELS: Record<string, string> = {
  feedback_orphan_rater: "Rater orphaned",
  feedback_orphan_anon: "Anon orphaned",
  feedback_rehome: "Rehomed",
  feedback_summary_regen: "Summary regenerated",
  feedback_niloofar_orphan: "Niloofar orphaned",
  feedback_niloofar_dismiss: "Niloofar dismissed",
  feedback_rejected_threshold: "Aged out (no consensus)",
  cluster_block_negative: "Blocked (negative pair)",
  cluster_block_low_trust: "Blocked (low source trust)",
  source_trust_change: "Source trust changed",
  source_trust_fast_penalty: "Source trust (fast penalty)",
  story_split_candidate: "Split candidate (centroid drift)",
};

const EVENT_COLORS: Record<string, string> = {
  feedback_orphan_rater: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  feedback_orphan_anon: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  feedback_rehome: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  feedback_summary_regen: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  feedback_niloofar_orphan: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  feedback_niloofar_dismiss: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  feedback_rejected_threshold: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  cluster_block_negative: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  cluster_block_low_trust: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  source_trust_change: "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  source_trust_fast_penalty: "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  story_split_candidate: "bg-pink-50 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
};

const EVENT_TYPE_FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "All" },
  { key: "feedback_orphan_rater", label: "Rater orphan" },
  { key: "feedback_orphan_anon", label: "Anon orphan" },
  { key: "feedback_rehome", label: "Rehome" },
  { key: "feedback_summary_regen", label: "Summary regen" },
  { key: "feedback_niloofar_orphan", label: "Niloofar agreed" },
  { key: "feedback_niloofar_dismiss", label: "Niloofar dismissed" },
  { key: "feedback_rejected_threshold", label: "Aged out" },
  { key: "cluster_block_negative", label: "Negative-pair block" },
  { key: "cluster_block_low_trust", label: "Low-trust block" },
  { key: "source_trust_change", label: "Trust change" },
  { key: "source_trust_fast_penalty", label: "Fast penalty" },
  { key: "story_split_candidate", label: "Split candidate" },
];

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export default function LearningDashboardPage() {
  const [authed, setAuthed] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [tab, setTab] = useState<"events" | "sources">("events");
  const [events, setEvents] = useState<EventItem[]>([]);
  const [sources, setSources] = useState<SourceTrust[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const h = adminHeaders();
      const params = new URLSearchParams({ limit: "200" });
      if (filter !== "all") params.set("event_type", filter);
      const [eRes, sRes] = await Promise.all([
        fetch(`${API}/api/v1/admin/feedback-impact/events?${params.toString()}`, { headers: h, cache: "no-store" }).then(r => r.json()),
        fetch(`${API}/api/v1/admin/feedback-impact/source-trust`, { headers: h, cache: "no-store" }).then(r => r.json()),
      ]);
      setEvents(eRes.items || []);
      setSources(sRes.items || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Error");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (authed) fetchAll();
  }, [authed, fetchAll]);

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

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Learning impact</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            What feedback changed in the system, and which sources got penalized for it.
          </p>
        </div>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-300 dark:border-slate-700 text-sm hover:bg-slate-50 dark:hover:bg-slate-900"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="flex gap-0 border-b border-slate-200 dark:border-slate-800 mb-4">
        <button
          onClick={() => setTab("events")}
          className={`px-4 py-2 text-sm font-bold border-b-2 -mb-px ${
            tab === "events"
              ? "border-slate-900 dark:border-white text-slate-900 dark:text-white"
              : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
          }`}
        >
          Recent events ({events.length})
        </button>
        <button
          onClick={() => setTab("sources")}
          className={`px-4 py-2 text-sm font-bold border-b-2 -mb-px ${
            tab === "sources"
              ? "border-slate-900 dark:border-white text-slate-900 dark:text-white"
              : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
          }`}
        >
          Source trust ({sources.length})
        </button>
      </div>

      {err && <p className="text-sm text-red-500 mb-3">{err}</p>}

      {tab === "events" && (
        <>
          <div className="flex flex-wrap gap-1.5 mb-4">
            {EVENT_TYPE_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`px-2 py-0.5 text-[12px] border ${
                  filter === f.key
                    ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900 border-slate-900 dark:border-white"
                    : "border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-900"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {events.length === 0 ? (
            <p className="text-sm text-slate-400 py-12 text-center">No events for this filter yet.</p>
          ) : (
            <div className="border border-slate-200 dark:border-slate-800 divide-y divide-slate-200 dark:divide-slate-800">
              {events.map((e) => (
                <div key={e.id} className="px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-900/50 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`inline-block px-1.5 py-0.5 text-[11px] font-medium ${EVENT_COLORS[e.event_type] || "bg-slate-100 text-slate-600"}`}>
                      {EVENT_LABELS[e.event_type] || e.event_type}
                    </span>
                    <span className="text-[11px] text-slate-400">{timeAgo(e.created_at)} ago</span>
                    <span className="text-[11px] text-slate-400">· {e.actor}</span>
                    {typeof e.confidence === "number" && (
                      <span className="text-[11px] text-slate-400">· cosine {e.confidence.toFixed(3)}</span>
                    )}
                  </div>

                  {e.story_title && (
                    <div className="flex items-center gap-2 text-sm mb-1">
                      <Link href={`/stories/${e.story_id}`} className="text-slate-700 dark:text-slate-300 hover:underline" target="_blank">
                        {e.story_title}
                      </Link>
                    </div>
                  )}
                  {e.article_title && (
                    <div className="flex items-start gap-1 text-[13px] text-slate-500 dark:text-slate-400 mb-1">
                      <ArrowRight className="h-3 w-3 flex-shrink-0 mt-1" />
                      <span className="line-clamp-1">{e.article_title}</span>
                    </div>
                  )}
                  {Object.keys(e.signals || {}).length > 0 && (
                    <div className="text-[11px] text-slate-400 mt-1 font-mono">
                      {Object.entries(e.signals).slice(0, 4).map(([k, v]) => (
                        <span key={k} className="mr-2">
                          {k}={String(v).slice(0, 60)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === "sources" && (
        <div className="border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/50 text-left">
              <tr>
                <th className="px-3 py-2 font-bold">Source</th>
                <th className="px-3 py-2 font-bold">Alignment</th>
                <th className="px-3 py-2 font-bold text-right">Articles 30d</th>
                <th className="px-3 py-2 font-bold text-right">Flagged</th>
                <th className="px-3 py-2 font-bold text-right">Flag rate</th>
                <th className="px-3 py-2 font-bold text-right">Trust score</th>
                <th className="px-3 py-2 font-bold text-right">Effect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {sources.map((s) => {
                const score = s.cluster_quality_score;
                const factor = score < 1.0 ? (1.0 / score) : 1.0;
                const baseThreshold = 0.45;
                const effective = Math.min(baseThreshold * factor, 0.95);
                return (
                  <tr key={s.source_id} className="hover:bg-slate-50 dark:hover:bg-slate-900/50">
                    <td className="px-3 py-2">
                      <div className="font-medium">{s.name_fa}</div>
                      <div className="text-[11px] text-slate-400">{s.slug}</div>
                    </td>
                    <td className="px-3 py-2 text-[12px] text-slate-500">{s.state_alignment}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.articles_30d}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {s.flagged_30d > 0 ? (
                        <span className="text-amber-600 dark:text-amber-400">{s.flagged_30d}</span>
                      ) : (
                        <span className="text-slate-400">0</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-[12px] text-slate-500">
                      {(s.flag_rate_30d * 100).toFixed(1)}%
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <span
                        className={
                          score < 0.7
                            ? "text-red-600 dark:text-red-400 font-bold"
                            : score < 0.9
                            ? "text-amber-600 dark:text-amber-400 font-medium"
                            : "text-slate-700 dark:text-slate-300"
                        }
                      >
                        {score.toFixed(3)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-[12px] text-slate-500 tabular-nums">
                      {score < 1.0
                        ? `cosine ≥ ${effective.toFixed(2)} required`
                        : "baseline"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
