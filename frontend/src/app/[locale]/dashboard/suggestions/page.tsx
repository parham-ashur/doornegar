"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  RefreshCw, ArrowLeft, Check, X, Trash2, ExternalLink,
  Clock, CheckCircle2, XCircle, Copy, ChevronDown, ChevronUp,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Suggestion {
  id: string;
  suggestion_type: string;
  name: string;
  url: string;
  language: string | null;
  suggested_category: string | null;
  description: string | null;
  submitter_name: string | null;
  submitter_contact: string | null;
  submitter_notes: string | null;
  status: string;
  reviewer_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
}

interface ListResponse {
  suggestions: Suggestion[];
  total: number;
  pending: number;
}

const TYPE_LABELS: Record<string, string> = {
  media: "Media outlet",
  telegram: "Telegram channel",
  x_twitter: "X / Twitter",
  youtube: "YouTube",
  instagram: "Instagram",
  website: "Website",
  other: "Other",
};

const CATEGORY_LABELS: Record<string, string> = {
  state: "State",
  semi_state: "Semi-state",
  independent: "Independent",
  diaspora: "Diaspora",
  not_sure: "Not sure",
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "Pending", color: "text-amber-600 dark:text-amber-400" },
  approved: { label: "Approved", color: "text-emerald-600 dark:text-emerald-400" },
  rejected: { label: "Rejected", color: "text-red-500" },
  duplicate: { label: "Duplicate", color: "text-slate-500" },
  already_tracked: { label: "Already tracked", color: "text-slate-500" },
};

export default function SuggestionsAdminPage() {
  const [authed, setAuthed] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [total, setTotal] = useState(0);
  const [pending, setPending] = useState(0);
  const [filter, setFilter] = useState<string>("pending");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("doornegar_admin_token");
      if (token) {
        setAdminToken(token);
        setAuthed(true);
      }
    }
  }, []);

  const authHeader = useCallback((): Record<string, string> => {
    return adminToken ? { Authorization: `Bearer ${adminToken}` } : {};
  }, [adminToken]);

  const fetchSuggestions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filter && filter !== "all") params.append("status", filter);
      params.append("limit", "100");
      const res = await fetch(`${API}/api/v1/suggestions/admin?${params}`, {
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ListResponse = await res.json();
      setSuggestions(data.suggestions);
      setTotal(data.total);
      setPending(data.pending);
    } catch (e: any) {
      setError(e.message || "Error loading");
    }
    setLoading(false);
  }, [filter, authHeader]);

  useEffect(() => {
    if (authed) fetchSuggestions();
  }, [authed, fetchSuggestions]);

  async function updateStatus(id: string, newStatus: string, notes?: string) {
    try {
      const res = await fetch(`${API}/api/v1/suggestions/admin/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ status: newStatus, reviewer_notes: notes || null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      fetchSuggestions();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  }

  async function deleteSuggestion(id: string) {
    if (!confirm("Delete this suggestion permanently?")) return;
    try {
      const res = await fetch(`${API}/api/v1/suggestions/admin/${id}`, {
        method: "DELETE",
        headers: authHeader(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      fetchSuggestions();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
          Suggestions Admin
        </h1>
        <p className="text-sm text-slate-500 mb-4">
          Access through the main dashboard first.
        </p>
        <Link
          href="/fa/dashboard"
          className="inline-flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Go to dashboard
        </Link>
      </div>
    );
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      });
    } catch { return iso; }
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
            Source Suggestions
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} total · {pending} pending review
          </p>
        </div>
        <button
          onClick={fetchSuggestions}
          disabled={loading}
          className="flex items-center gap-2 border border-slate-200 dark:border-slate-700 px-4 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Admin token input — only show if missing or there was an auth error */}
      {(!adminToken || error) && (
        <div className="mb-6 border border-slate-200 dark:border-slate-800 p-4">
          <label className="block text-xs font-semibold text-slate-500 mb-2">
            Admin Token (required for admin endpoints in production)
          </label>
          <div className="flex gap-2">
            <input
              type="password"
              value={adminToken}
              onChange={(e) => {
                setAdminToken(e.target.value);
                localStorage.setItem("doornegar_admin_token", e.target.value);
              }}
              placeholder="Paste ADMIN_TOKEN here"
              className="flex-1 px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={fetchSuggestions}
              className="px-4 py-2 text-sm bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90"
            >
              Load
            </button>
          </div>
        </div>
      )}

      {/* Help panel */}
      <div className="mb-6 border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/20 p-4 text-xs leading-6 text-slate-700 dark:text-slate-300">
        <p className="font-bold text-slate-900 dark:text-white mb-2">How to review source suggestions</p>
        <p className="mb-2">
          These are new media outlets, Telegram channels, or websites submitted by visitors via <code className="text-[11px] bg-white dark:bg-slate-900 px-1 border border-slate-200 dark:border-slate-800">/fa/suggest</code>. Click the URL to inspect the source, then use the buttons on the right:
        </p>
        <ul className="space-y-1 list-none">
          <li><span className="inline-flex items-center gap-1"><Check className="h-3 w-3 text-emerald-600" /> <strong>Approve</strong></span> — good source, you intend to add it to the tracked list (you'll still need to add it manually via backend seeding)</li>
          <li><span className="inline-flex items-center gap-1"><X className="h-3 w-3 text-red-500" /> <strong>Reject</strong></span> — not relevant, low quality, or unsafe</li>
          <li><span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-slate-500" /> <strong>Already tracked</strong></span> — duplicate of a source already in the system</li>
          <li><span className="inline-flex items-center gap-1"><ChevronDown className="h-3 w-3" /> <strong>Expand</strong></span> — see full description, submitter info, and add reviewer notes</li>
        </ul>
        <p className="mt-2 text-slate-500">
          Approving does NOT automatically start scraping — it just marks the suggestion as accepted. Actual integration still requires adding the source to the backend seed.
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-2">
        {["pending", "approved", "rejected", "duplicate", "already_tracked", "all"].map((s) => (
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

      {error && (
        <div className="mb-6 p-4 border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/10 text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {loading && !suggestions.length && (
        <p className="text-sm text-slate-500 py-8 text-center">Loading...</p>
      )}

      {!loading && suggestions.length === 0 && (
        <p className="text-sm text-slate-500 py-8 text-center">
          No suggestions {filter !== "all" ? `with status "${filter}"` : "yet"}.
        </p>
      )}

      {/* Suggestion list */}
      <div className="space-y-3">
        {suggestions.map((s) => {
          const expanded = expandedId === s.id;
          const status = STATUS_LABELS[s.status] || { label: s.status, color: "text-slate-500" };
          return (
            <div
              key={s.id}
              className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
            >
              {/* Row header */}
              <div className="p-4 flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1 flex-wrap">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                      {TYPE_LABELS[s.suggestion_type] || s.suggestion_type}
                    </span>
                    <span className={`text-xs font-medium ${status.color}`}>
                      {status.label}
                    </span>
                    <span className="text-xs text-slate-400">{formatDate(s.created_at)}</span>
                  </div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white truncate">
                    {s.name}
                  </h3>
                  <a
                    href={s.url.startsWith("http") ? s.url : `https://t.me/${s.url.replace(/^@/, "")}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1"
                  >
                    {s.url} <ExternalLink className="h-3 w-3" />
                  </a>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {s.status === "pending" && (
                    <>
                      <button
                        onClick={() => updateStatus(s.id, "approved")}
                        title="Approve"
                        className="p-2 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => updateStatus(s.id, "rejected")}
                        title="Reject"
                        className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        <X className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => updateStatus(s.id, "already_tracked")}
                        title="Already tracked"
                        className="p-2 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800"
                      >
                        <CheckCircle2 className="h-4 w-4" />
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => setExpandedId(expanded ? null : s.id)}
                    title={expanded ? "Collapse" : "Expand"}
                    className="p-2 text-slate-400 hover:text-slate-900 dark:hover:text-white"
                  >
                    {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* Expanded details */}
              {expanded && (
                <div className="px-4 pb-4 pt-0 border-t border-slate-100 dark:border-slate-800/50 space-y-3">
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <p className="text-slate-400">Language</p>
                      <p className="text-slate-900 dark:text-slate-200">{s.language || "—"}</p>
                    </div>
                    <div>
                      <p className="text-slate-400">Suggested category</p>
                      <p className="text-slate-900 dark:text-slate-200">
                        {s.suggested_category ? CATEGORY_LABELS[s.suggested_category] : "—"}
                      </p>
                    </div>
                  </div>

                  {s.description && (
                    <div>
                      <p className="text-xs text-slate-400 mb-1">Description</p>
                      <p className="text-xs leading-5 text-slate-700 dark:text-slate-300" dir="rtl">
                        {s.description}
                      </p>
                    </div>
                  )}

                  {(s.submitter_name || s.submitter_contact || s.submitter_notes) && (
                    <div className="border-t border-slate-100 dark:border-slate-800/50 pt-3">
                      <p className="text-xs text-slate-400 mb-2">Submitter</p>
                      {s.submitter_name && (
                        <p className="text-xs text-slate-700 dark:text-slate-300">
                          Name: {s.submitter_name}
                        </p>
                      )}
                      {s.submitter_contact && (
                        <p className="text-xs text-slate-700 dark:text-slate-300">
                          Contact: <span className="font-mono">{s.submitter_contact}</span>
                          <button
                            onClick={() => navigator.clipboard.writeText(s.submitter_contact!)}
                            className="ml-2 inline-flex items-center"
                            title="Copy"
                          >
                            <Copy className="h-3 w-3 text-slate-400 hover:text-slate-900" />
                          </button>
                        </p>
                      )}
                      {s.submitter_notes && (
                        <p className="text-xs text-slate-700 dark:text-slate-300 mt-1" dir="rtl">
                          Notes: {s.submitter_notes}
                        </p>
                      )}
                    </div>
                  )}

                  {s.reviewer_notes && (
                    <div className="border-t border-slate-100 dark:border-slate-800/50 pt-3">
                      <p className="text-xs text-slate-400 mb-1">Reviewer notes</p>
                      <p className="text-xs text-slate-700 dark:text-slate-300">{s.reviewer_notes}</p>
                    </div>
                  )}

                  {/* Add reviewer notes */}
                  <div className="border-t border-slate-100 dark:border-slate-800/50 pt-3">
                    <button
                      onClick={() => {
                        const notes = prompt("Reviewer notes:", s.reviewer_notes || "");
                        if (notes !== null) updateStatus(s.id, s.status, notes);
                      }}
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      {s.reviewer_notes ? "Edit notes" : "Add notes"}
                    </button>
                    <button
                      onClick={() => deleteSuggestion(s.id)}
                      className="text-xs text-red-500 hover:underline mr-4"
                    >
                      <Trash2 className="h-3 w-3 inline" /> Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
