"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ChevronDown, ChevronUp, ExternalLink, RefreshCw } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Tab = "sources" | "channels";

interface SourceStat {
  id: string;
  slug: string;
  name_fa: string | null;
  name_en: string;
  state_alignment: string | null;
  is_active: boolean;
  total: number;
  last_24h: number;
  last_7d: number;
  last_ingested_at: string | null;
  hours_since_last: number | null;
}

interface ChannelStat {
  id: string;
  username: string;
  title: string | null;
  channel_type: string | null;
  is_active: boolean;
  total: number;
  last_24h: number;
  last_7d: number;
  last_post_at: string | null;
  hours_since_last: number | null;
}

interface ArticleBrief {
  id: string;
  title_fa: string | null;
  title_en: string | null;
  title_original: string | null;
  url: string;
  published_at: string | null;
  ingested_at: string;
}

interface PostBrief {
  id: string;
  text: string | null;
  date: string;
  views: number | null;
  url: string | null;
}

function freshnessClass(hours: number | null, staleAfter: number): string {
  if (hours == null) return "text-slate-400";
  if (hours > staleAfter * 2) return "text-red-500";
  if (hours > staleAfter) return "text-amber-500";
  return "text-emerald-600 dark:text-emerald-400";
}

function fmtHours(hours: number | null): string {
  if (hours == null) return "never";
  if (hours < 1) return `${Math.round(hours * 60)}m ago`;
  if (hours < 48) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function FetchStatsPage() {
  const [authed, setAuthed] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [tab, setTab] = useState<Tab>("sources");
  const [sources, setSources] = useState<SourceStat[]>([]);
  const [channels, setChannels] = useState<ChannelStat[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [drilldownItems, setDrilldownItems] = useState<(ArticleBrief | PostBrief)[]>([]);
  const [drilldownLoading, setDrilldownLoading] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("doornegar_admin_token");
      if (token) {
        setAdminToken(token);
        setAuthed(true);
      }
    }
  }, []);

  const authHeaders = useCallback(
    (): Record<string, string> => (adminToken ? { Authorization: `Bearer ${adminToken}` } : {}),
    [adminToken],
  );

  const fetchStats = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    setError(null);
    try {
      const path = tab === "sources" ? "/api/v1/admin/sources/stats" : "/api/v1/admin/channels/stats";
      const res = await fetch(`${API}${path}`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (tab === "sources") setSources(data.sources || []);
      else setChannels(data.channels || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load stats");
    }
    setLoading(false);
  }, [authed, tab, authHeaders]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  async function toggleDrilldown(id: string) {
    if (expandedId === id) {
      setExpandedId(null);
      setDrilldownItems([]);
      return;
    }
    setExpandedId(id);
    setDrilldownItems([]);
    setDrilldownLoading(true);
    try {
      if (tab === "sources") {
        const res = await fetch(
          `${API}/api/v1/articles?source_id=${id}&page_size=30`,
          { headers: authHeaders() },
        );
        if (res.ok) {
          const data = await res.json();
          setDrilldownItems(data.articles || []);
        }
      } else {
        const res = await fetch(
          `${API}/api/v1/social/channels/${id}/posts?limit=30`,
          { headers: authHeaders() },
        );
        if (res.ok) {
          const data = await res.json();
          setDrilldownItems(data || []);
        }
      }
    } catch (e) {
      console.error(e);
    }
    setDrilldownLoading(false);
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Fetch stats</h1>
        <p className="text-sm text-slate-500 mb-4">
          Access the{" "}
          <Link href="/fa/dashboard" className="underline">
            main dashboard
          </Link>{" "}
          first to paste your admin token.
        </p>
      </div>
    );
  }

  const rows = tab === "sources" ? sources : channels;
  const staleAfter = tab === "sources" ? 6 : 4;  // hours before coloring as warning

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <Link
            href="/fa/dashboard"
            className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 dark:hover:text-slate-200 mb-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Fetch stats</h1>
          <p className="text-sm text-slate-500">
            Per-{tab === "sources" ? "source article" : "channel post"} counts. Click a row to see the latest items.
          </p>
        </div>
        <button
          onClick={fetchStats}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-sm border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="mb-4 flex gap-0 border-b border-slate-200 dark:border-slate-800">
        {(["sources", "channels"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setExpandedId(null);
              setDrilldownItems([]);
            }}
            className={`text-sm font-medium px-4 py-2 border-b-2 transition-colors ${
              tab === t
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t === "sources" ? `RSS sources (${sources.length})` : `Telegram channels (${channels.length})`}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="border border-slate-200 dark:border-slate-800">
        <div className="grid grid-cols-[1fr_100px_80px_80px_120px_40px] gap-2 px-3 py-2 text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
          <div>{tab === "sources" ? "Source" : "Channel"}</div>
          <div className="text-right">Total</div>
          <div className="text-right">24h</div>
          <div className="text-right">7d</div>
          <div className="text-right">Last seen</div>
          <div />
        </div>

        {rows.length === 0 && !loading && (
          <div className="px-3 py-8 text-center text-sm text-slate-400">No data.</div>
        )}

        {rows.map((row) => {
          const isExpanded = expandedId === row.id;
          const name = tab === "sources"
            ? (row as SourceStat).name_en
            : (row as ChannelStat).title || (row as ChannelStat).username;
          const subtitle = tab === "sources"
            ? (row as SourceStat).state_alignment || "—"
            : `@${(row as ChannelStat).username} · ${(row as ChannelStat).channel_type || "?"}`;

          return (
            <div key={row.id} className="border-b border-slate-100 dark:border-slate-800 last:border-0">
              <button
                onClick={() => toggleDrilldown(row.id)}
                className="w-full grid grid-cols-[1fr_100px_80px_80px_120px_40px] gap-2 px-3 py-2.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-900/50 text-left items-center"
              >
                <div className="min-w-0">
                  <div className="font-medium text-slate-900 dark:text-white truncate">
                    {name}
                    {!row.is_active && (
                      <span className="ms-2 text-[11px] text-slate-400">(inactive)</span>
                    )}
                  </div>
                  <div className="text-[12px] text-slate-400 truncate">{subtitle}</div>
                </div>
                <div className="text-right font-mono text-slate-700 dark:text-slate-300">{row.total}</div>
                <div className="text-right font-mono text-slate-700 dark:text-slate-300">{row.last_24h}</div>
                <div className="text-right font-mono text-slate-700 dark:text-slate-300">{row.last_7d}</div>
                <div className={`text-right text-[12px] ${freshnessClass(row.hours_since_last, staleAfter)}`}>
                  {fmtHours(row.hours_since_last)}
                </div>
                <div className="flex justify-end">
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-slate-400" />
                  )}
                </div>
              </button>

              {isExpanded && (
                <div className="px-3 pb-3 bg-slate-50 dark:bg-slate-900/30">
                  {drilldownLoading && (
                    <p className="text-sm text-slate-400 py-3">Loading latest items…</p>
                  )}
                  {!drilldownLoading && drilldownItems.length === 0 && (
                    <p className="text-sm text-slate-400 py-3">No items returned.</p>
                  )}
                  {!drilldownLoading && drilldownItems.length > 0 && (
                    <ul className="divide-y divide-slate-200 dark:divide-slate-800 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
                      {drilldownItems.map((item) => {
                        if (tab === "sources") {
                          const a = item as ArticleBrief;
                          const title = a.title_fa || a.title_en || a.title_original || "(no title)";
                          return (
                            <li key={a.id} className="px-3 py-2 text-sm">
                              <a
                                href={a.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-start gap-2 text-slate-700 dark:text-slate-300 hover:text-blue-600 dark:hover:text-blue-400"
                              >
                                <span className="flex-1 min-w-0 truncate">{title}</span>
                                <span className="shrink-0 text-[11px] text-slate-400">
                                  {a.published_at ? new Date(a.published_at).toLocaleDateString() : "—"}
                                </span>
                                <ExternalLink className="h-3 w-3 shrink-0 text-slate-400" />
                              </a>
                            </li>
                          );
                        }
                        const p = item as PostBrief;
                        return (
                          <li key={p.id} className="px-3 py-2 text-sm">
                            <div className="flex items-start gap-2">
                              <p className="flex-1 min-w-0 text-slate-700 dark:text-slate-300 line-clamp-2">
                                {p.text || "(no text)"}
                              </p>
                              <span className="shrink-0 text-[11px] text-slate-400">
                                {new Date(p.date).toLocaleDateString()}
                              </span>
                              {p.url && (
                                <a
                                  href={p.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="shrink-0 text-slate-400 hover:text-blue-600"
                                >
                                  <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                            </div>
                            {p.views != null && (
                              <p className="text-[11px] text-slate-400 mt-0.5">{p.views.toLocaleString()} views</p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer: legend */}
      <div className="mt-4 flex flex-wrap gap-4 text-[11px] text-slate-400">
        <span>
          <span className="text-emerald-600 dark:text-emerald-400">●</span> fresh
        </span>
        <span>
          <span className="text-amber-500">●</span> stale (&gt;{staleAfter}h)
        </span>
        <span>
          <span className="text-red-500">●</span> critical (&gt;{staleAfter * 2}h)
        </span>
      </div>
    </div>
  );
}
