"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  RefreshCw, ArrowLeft, Check, Trash2, ExternalLink, Clock,
  CheckCircle2, ChevronDown, ChevronUp, Copy, Play, XCircle,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FeedbackItem {
  id: string;
  target_type: string;
  target_id: string | null;
  target_url: string | null;
  issue_type: string;
  current_value: string | null;
  suggested_value: string | null;
  reason: string | null;
  rater_name: string | null;
  rater_contact: string | null;
  status: string;
  priority: string | null;
  admin_notes: string | null;
  resolved_at: string | null;
  created_at: string;
}

interface ListResponse {
  items: FeedbackItem[];
  total: number;
  open: number;
  in_progress: number;
}

const TARGET_LABELS: Record<string, string> = {
  story: "Story",
  story_title: "Story title",
  story_image: "Story image",
  story_summary: "Story summary",
  article: "Article",
  source: "Source",
  layout: "Layout",
  homepage: "Homepage",
  other: "Other",
};

const ISSUE_LABELS: Record<string, string> = {
  wrong_title: "Wrong title",
  bad_image: "Bad image",
  wrong_clustering: "Wrong clustering",
  bad_summary: "Bad summary",
  wrong_source_class: "Wrong source classification",
  layout_issue: "Layout issue",
  bug: "Bug",
  feature_request: "Feature request",
  other: "Other",
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  open: { label: "Open", color: "text-amber-600 dark:text-amber-400" },
  in_progress: { label: "In progress", color: "text-blue-600 dark:text-blue-400" },
  done: { label: "Done", color: "text-emerald-600 dark:text-emerald-400" },
  wont_do: { label: "Won't do", color: "text-slate-500" },
  duplicate: { label: "Duplicate", color: "text-slate-500" },
};

export default function ImprovementsAdminPage() {
  const [authed, setAuthed] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [openCount, setOpenCount] = useState(0);
  const [inProgress, setInProgress] = useState(0);
  const [filter, setFilter] = useState<string>("open");
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      if (localStorage.getItem("doornegar_admin") === "true") setAuthed(true);
      const token = localStorage.getItem("doornegar_admin_token");
      if (token) setAdminToken(token);
    }
  }, []);

  const authHeader = useCallback((): Record<string, string> => {
    return adminToken ? { Authorization: `Bearer ${adminToken}` } : {};
  }, [adminToken]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter && filter !== "all") params.append("status", filter);
      params.append("limit", "200");
      const res = await fetch(`${API}/api/v1/improvements/admin?${params}`, {
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ListResponse = await res.json();
      setItems(data.items);
      setTotal(data.total);
      setOpenCount(data.open);
      setInProgress(data.in_progress);
    } catch (e: any) {
      console.error(e);
    }
    setLoading(false);
  }, [filter, authHeader]);

  useEffect(() => {
    if (authed) fetchItems();
  }, [authed, fetchItems]);

  async function update(id: string, patch: { status?: string; priority?: string; admin_notes?: string }) {
    try {
      const res = await fetch(`${API}/api/v1/improvements/admin/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      fetchItems();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this feedback item permanently?")) return;
    try {
      const res = await fetch(`${API}/api/v1/improvements/admin/${id}`, {
        method: "DELETE",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      fetchItems();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      });
    } catch { return iso; }
  }

  function copyClaudePrompt(item: FeedbackItem) {
    const lines = [
      `Improvement feedback (id: ${item.id}):`,
      `Target: ${TARGET_LABELS[item.target_type] || item.target_type}${item.target_id ? ` (${item.target_id})` : ""}`,
      item.target_url ? `URL: ${item.target_url}` : null,
      `Issue: ${ISSUE_LABELS[item.issue_type] || item.issue_type}`,
      item.current_value ? `Current: ${item.current_value}` : null,
      item.suggested_value ? `Suggested: ${item.suggested_value}` : null,
      item.reason ? `Reason: ${item.reason}` : null,
      item.rater_name ? `Reported by: ${item.rater_name}` : null,
    ].filter(Boolean);
    navigator.clipboard.writeText(lines.join("\n"));
    alert("Copied. Paste in Claude to request a fix.");
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
          Improvements Admin
        </h1>
        <Link
          href="/fa/dashboard"
          className="inline-flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Access through main dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <Link
            href="/fa/dashboard"
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white mb-2"
          >
            <ArrowLeft className="h-3 w-3" /> Back to dashboard
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            Improvement Todo List
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} total · {openCount} open · {inProgress} in progress
          </p>
        </div>
        <button
          onClick={fetchItems}
          disabled={loading}
          className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-4 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Admin token */}
      <div className="mb-6 border border-slate-200 dark:border-slate-800 p-4">
        <label className="block text-xs font-semibold text-slate-500 mb-2">
          Admin Token
        </label>
        <div className="flex gap-2">
          <input
            type="password"
            value={adminToken}
            onChange={(e) => {
              setAdminToken(e.target.value);
              localStorage.setItem("doornegar_admin_token", e.target.value);
            }}
            placeholder="Paste ADMIN_TOKEN"
            className="flex-1 px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none"
          />
          <button
            onClick={fetchItems}
            className="px-4 py-2 text-sm bg-slate-900 dark:bg-white text-white dark:text-slate-900"
          >
            Load
          </button>
        </div>
      </div>

      {/* Status filters */}
      <div className="mb-6 flex flex-wrap gap-2">
        {["open", "in_progress", "done", "wont_do", "all"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 text-xs border transition-colors ${
              filter === s
                ? "border-slate-900 dark:border-white bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                : "border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-500"
            }`}
          >
            {s === "all" ? "All" : STATUS_LABELS[s]?.label || s}
          </button>
        ))}
      </div>

      {loading && !items.length && (
        <p className="text-sm text-slate-500 py-8 text-center">Loading...</p>
      )}

      {!loading && items.length === 0 && (
        <p className="text-sm text-slate-500 py-8 text-center">
          No feedback items {filter !== "all" ? `with status "${filter}"` : "yet"}.
        </p>
      )}

      {/* Items */}
      <div className="space-y-3">
        {items.map((item) => {
          const expanded = expandedId === item.id;
          const status = STATUS_LABELS[item.status] || { label: item.status, color: "text-slate-500" };
          return (
            <div
              key={item.id}
              className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
            >
              <div className="p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1 flex-wrap text-xs">
                      <span className="font-bold text-slate-700 dark:text-slate-300">
                        {ISSUE_LABELS[item.issue_type] || item.issue_type}
                      </span>
                      <span className="text-slate-400">•</span>
                      <span className="text-slate-500">
                        {TARGET_LABELS[item.target_type] || item.target_type}
                      </span>
                      <span className={`font-medium ${status.color}`}>
                        {status.label}
                      </span>
                      {item.priority && (
                        <span className={`px-1.5 py-0.5 text-[10px] border ${
                          item.priority === "high" ? "border-red-400 text-red-500" :
                          item.priority === "medium" ? "border-amber-400 text-amber-600" :
                          "border-slate-300 text-slate-500"
                        }`}>
                          {item.priority}
                        </span>
                      )}
                      <span className="text-slate-400">{formatDate(item.created_at)}</span>
                    </div>

                    {(item.suggested_value || item.reason) && (
                      <p className="text-sm text-slate-700 dark:text-slate-300 leading-6 mt-1" dir="rtl">
                        {item.suggested_value || item.reason}
                      </p>
                    )}

                    {item.target_url && (
                      <a
                        href={item.target_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline mt-1"
                      >
                        View page <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>

                  <div className="flex flex-col gap-1 shrink-0">
                    {item.status === "open" && (
                      <button
                        onClick={() => update(item.id, { status: "in_progress" })}
                        title="Start"
                        className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20"
                      >
                        <Play className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {item.status !== "done" && (
                      <button
                        onClick={() => update(item.id, { status: "done" })}
                        title="Mark done"
                        className="p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {item.status !== "wont_do" && item.status !== "done" && (
                      <button
                        onClick={() => update(item.id, { status: "wont_do" })}
                        title="Won't do"
                        className="p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                      </button>
                    )}
                    <button
                      onClick={() => copyClaudePrompt(item)}
                      title="Copy Claude prompt"
                      className="p-1.5 text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/20"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => setExpandedId(expanded ? null : item.id)}
                      className="p-1.5 text-slate-400 hover:text-slate-900 dark:hover:text-white"
                    >
                      {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>

                {expanded && (
                  <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800/50 space-y-3 text-xs">
                    {item.target_id && (
                      <div>
                        <p className="text-slate-400">Target ID</p>
                        <p className="font-mono text-slate-700 dark:text-slate-300">{item.target_id}</p>
                      </div>
                    )}
                    {item.current_value && (
                      <div>
                        <p className="text-slate-400 mb-1">Current value</p>
                        <p className="text-slate-700 dark:text-slate-300 p-2 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800" dir="rtl">
                          {item.current_value}
                        </p>
                      </div>
                    )}
                    {item.suggested_value && (
                      <div>
                        <p className="text-slate-400 mb-1">Suggested value</p>
                        <p className="text-slate-700 dark:text-slate-300 p-2 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/50" dir="rtl">
                          {item.suggested_value}
                        </p>
                      </div>
                    )}
                    {item.reason && (
                      <div>
                        <p className="text-slate-400 mb-1">Reason</p>
                        <p className="text-slate-700 dark:text-slate-300" dir="rtl">{item.reason}</p>
                      </div>
                    )}
                    {item.rater_name && (
                      <div>
                        <p className="text-slate-400">Reported by</p>
                        <p className="text-slate-700 dark:text-slate-300">{item.rater_name}</p>
                      </div>
                    )}
                    {item.admin_notes && (
                      <div>
                        <p className="text-slate-400 mb-1">Admin notes</p>
                        <p className="text-slate-700 dark:text-slate-300">{item.admin_notes}</p>
                      </div>
                    )}
                    <div className="flex items-center gap-3 pt-2 border-t border-slate-100 dark:border-slate-800/50">
                      <button
                        onClick={() => {
                          const notes = prompt("Admin notes:", item.admin_notes || "");
                          if (notes !== null) update(item.id, { admin_notes: notes });
                        }}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        Edit notes
                      </button>
                      <button
                        onClick={() => {
                          const p = prompt("Priority (low/medium/high):", item.priority || "");
                          if (p === "low" || p === "medium" || p === "high") update(item.id, { priority: p });
                        }}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        Set priority
                      </button>
                      <button
                        onClick={() => remove(item.id)}
                        className="text-xs text-red-500 hover:underline"
                      >
                        <Trash2 className="h-3 w-3 inline" /> Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
