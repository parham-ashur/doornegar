"use client";

import { useState, useEffect } from "react";
import { Play, CheckCircle, XCircle, Loader2, AlertTriangle, DollarSign, Zap, Activity } from "lucide-react";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Cost = "free" | "llm-light" | "llm-heavy";

type Action = {
  id: string;
  label: string;
  description: string;
  endpoint: string;
  cost: Cost;
  category: "cluster" | "ingest" | "analysis" | "cleanup";
  confirm?: string;
};

const ACTIONS: Action[] = [
  // ── CLUSTERING ──────────────────────────────────────────────
  {
    id: "recluster-orphans",
    label: "Retry-cluster orphan articles",
    description: "Walks orphan articles older than 6h and attaches them to existing stories at ≥0.40 cosine. Pure math. Cap 500/run — re-run if attach rate is high.",
    endpoint: "/api/v1/admin/maintenance/recluster-orphans",
    cost: "free",
    category: "cluster",
  },
  {
    id: "merge-tiny-cosine",
    label: "Merge near-duplicate tiny stories",
    description: "Deterministic pre-merge: folds story pairs with article_count ≤ 4 and centroid cosine ≥ 0.60 into the larger one. Shrinks the hidden-story backlog.",
    endpoint: "/api/v1/admin/maintenance/merge-tiny-cosine",
    cost: "free",
    category: "cluster",
  },
  {
    id: "recompute-centroids",
    label: "Recompute story centroids",
    description: "Recomputes centroid_embedding for stories with NULL centroid (needed after merges and article moves). Pure math.",
    endpoint: "/api/v1/admin/maintenance/recompute-centroids",
    cost: "free",
    category: "cluster",
  },

  // ── INGEST / NLP ────────────────────────────────────────────
  {
    id: "ingest",
    label: "Ingest RSS + Telegram",
    description: "Pulls new articles from all active RSS feeds and Telegram channels. Does not call the LLM.",
    endpoint: "/api/v1/admin/ingest/trigger",
    cost: "free",
    category: "ingest",
  },
  {
    id: "nlp",
    label: "NLP process unprocessed articles",
    description: "Embeds, translates (when needed), and extracts keywords for articles where processed_at is NULL. Calls the translation LLM for English-only titles.",
    endpoint: "/api/v1/admin/nlp/trigger",
    cost: "llm-light",
    category: "ingest",
  },
  {
    id: "cluster",
    label: "Cluster new articles",
    description: "Runs the full clustering pipeline: match to existing stories, cluster unmatched into new, promote crossers, merge similar hidden. Uses gpt-4o-mini for the LLM confirmation pass.",
    endpoint: "/api/v1/admin/cluster/trigger",
    cost: "llm-heavy",
    category: "cluster",
    confirm: "Clustering will send ambiguous article/story pairs to the LLM. Spend depends on how many new articles exist. Continue?",
  },

  // ── ANALYSIS ────────────────────────────────────────────────
  {
    id: "bias",
    label: "Bias-score unscored articles",
    description: "Scores one representative article per source per visible story with gpt-4o-mini. Batch size 20. Already deduped against rows already in bias_scores.",
    endpoint: "/api/v1/admin/bias/trigger",
    cost: "llm-heavy",
    category: "analysis",
    confirm: "Bias scoring calls gpt-4o-mini per article (batch 20). Continue?",
  },

  // ── CLEANUP ─────────────────────────────────────────────────
  {
    id: "prune-stagnant",
    label: "Prune stagnant tiny stories",
    description: "Deletes 1-article stories older than 48h and 2-4 article stories older than 14 days. is_edited stories are preserved. Safe.",
    endpoint: "/api/v1/admin/maintenance/prune-stagnant",
    cost: "free",
    category: "cleanup",
  },
  {
    id: "prune-noise",
    label: "Prune noise (short articles + junk posts)",
    description: "Deletes unlinked Telegram posts and RSS-origin orphans with <200 chars of content. Safe — only touches rows that haven't been analyzed yet.",
    endpoint: "/api/v1/admin/maintenance/prune-noise",
    cost: "free",
    category: "cleanup",
  },
];

const CATEGORY_LABELS: Record<Action["category"], string> = {
  cluster: "Clustering",
  ingest: "Ingest & NLP",
  analysis: "Analysis (LLM)",
  cleanup: "Cleanup",
};

const COST_BADGE: Record<Cost, { label: string; cls: string; icon: React.ReactNode }> = {
  free: { label: "free", cls: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 border-emerald-300 dark:border-emerald-700", icon: <Zap className="w-3 h-3" /> },
  "llm-light": { label: "LLM light", cls: "text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-700", icon: <DollarSign className="w-3 h-3" /> },
  "llm-heavy": { label: "LLM heavy", cls: "text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-red-300 dark:border-red-700", icon: <DollarSign className="w-3 h-3" /> },
};

type Result = { status: "ok" | "error"; stats?: any; error?: string; finished_at: number };

export default function ActionsPage() {
  const [authed, setAuthed] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<Record<string, Result>>({});

  useEffect(() => setAuthed(hasAdminToken()), []);

  async function run(action: Action) {
    if (action.confirm && !confirm(action.confirm)) return;
    setRunning(prev => {
      const n = new Set(prev);
      n.add(action.id);
      return n;
    });
    try {
      const r = await fetch(`${API}${action.endpoint}`, {
        method: "POST",
        headers: adminHeaders(),
      });
      const data = await r.json();
      setResults(prev => ({ ...prev, [action.id]: { ...data, finished_at: Date.now() } }));
    } catch (e: any) {
      setResults(prev => ({ ...prev, [action.id]: { status: "error", error: e?.message || "network", finished_at: Date.now() } }));
    } finally {
      setRunning(prev => {
        const n = new Set(prev);
        n.delete(action.id);
        return n;
      });
    }
  }

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
          onClick={() => { localStorage.setItem("doornegar_admin_token", tokenInput); setAuthed(true); }}
        >ورود</button>
      </div>
    );
  }

  const categories = ["cluster", "ingest", "analysis", "cleanup"] as const;

  return (
    <div className="p-6 max-w-5xl mx-auto text-slate-900 dark:text-slate-100">
      <div className="flex items-center gap-3 mb-6">
        <Activity className="w-7 h-7 text-blue-500" />
        <h1 className="text-2xl font-black">Maintenance Actions</h1>
      </div>

      <p className="text-sm text-slate-500 mb-6">
        One-click triggers for each maintenance step. Nothing destructive runs without a confirm dialog.
        Safe (<span className="text-emerald-600 dark:text-emerald-400">free</span>) actions are pure math / SQL.
        LLM actions call OpenAI and show up on the cost dashboard.
      </p>

      {categories.map(cat => {
        const actionsInCat = ACTIONS.filter(a => a.category === cat);
        if (!actionsInCat.length) return null;
        return (
          <div key={cat} className="mb-8">
            <h2 className="text-xs font-black uppercase tracking-wider text-slate-500 mb-3">
              {CATEGORY_LABELS[cat]}
            </h2>
            <div className="space-y-3">
              {actionsInCat.map(action => {
                const result = results[action.id];
                const isRunning = running.has(action.id);
                const badge = COST_BADGE[action.cost];
                return (
                  <div key={action.id} className="border border-slate-200 dark:border-slate-800 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-sm font-bold">{action.label}</h3>
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold border ${badge.cls}`}>
                            {badge.icon} {badge.label}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 leading-5">{action.description}</p>
                      </div>
                      <button
                        onClick={() => run(action)}
                        disabled={isRunning}
                        className="shrink-0 inline-flex items-center gap-2 px-3 py-2 border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-900/50 disabled:opacity-50 text-sm"
                      >
                        {isRunning ? (
                          <><Loader2 className="w-4 h-4 animate-spin" /> Running…</>
                        ) : (
                          <><Play className="w-4 h-4" /> Run</>
                        )}
                      </button>
                    </div>
                    {result && (
                      <div className={`mt-3 px-3 py-2 text-xs border ${
                        result.status === "ok"
                          ? "border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/40"
                          : "border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40"
                      }`}>
                        <div className="flex items-center gap-2 mb-1">
                          {result.status === "ok" ? <CheckCircle className="w-3 h-3 text-emerald-600" /> : <XCircle className="w-3 h-3 text-red-600" />}
                          <span className="font-bold">
                            {result.status === "ok" ? "Completed" : "Failed"}
                          </span>
                          <span className="text-slate-400 text-[10px]">
                            {new Date(result.finished_at).toLocaleTimeString()}
                          </span>
                        </div>
                        {result.error ? (
                          <pre className="text-red-700 dark:text-red-300 text-[11px] whitespace-pre-wrap">{result.error}</pre>
                        ) : (
                          <pre className="text-slate-700 dark:text-slate-300 text-[11px] font-mono whitespace-pre-wrap">
                            {JSON.stringify(result.stats || {}, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      <div className="border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 p-4 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2 mt-8">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
        <div>
          <strong>About Niloofar:</strong> Niloofar is a separate editorial workflow — she runs through the Claude session
          (not the API), so she doesn't have a button here. Invoke her by saying <em>&ldquo;run Niloofar&rdquo;</em> in the
          chat session. She gathers top-50 stories, writes preliminary summaries for empty ones, merges near-duplicates,
          scores per-article neutrality, and writes edits back to the DB via{" "}
          <code className="font-mono">journalist_audit.py --apply-from</code>.
        </div>
      </div>
    </div>
  );
}
