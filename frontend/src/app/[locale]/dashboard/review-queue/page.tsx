"use client";

/**
 * Review Queue — single page that rolls up everything flagged by the
 * pipeline as needing HITL attention: guardrail tiers, image gaps,
 * Telegram triage count. Each row has inline freeze/unfreeze and links
 * to the split screen, image picker, or narrative editor.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type QueueItem = {
  story_id: string;
  title_fa: string;
  article_count: number;
  source_count: number;
  review_tier: number;
  first_published_at: string | null;
  last_updated_at: string | null;
  age_days: number | null;
  arc_id: string | null;
};

type QueueResponse = {
  items: QueueItem[];
  tier_counts: Record<string, number>;
};

type ImageGap = {
  id: string;
  slug: string;
  title_fa: string;
  article_count: number;
  source_count: number;
  trending_score: number;
};

const TIER_STYLE: Record<number, string> = {
  1: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800",
  2: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/20 dark:text-orange-300 dark:border-orange-800",
  3: "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800",
};

const TIER_LABEL: Record<number, string> = {
  1: "Tier 1 · soft warn",
  2: "Tier 2 · strong warn",
  3: "Tier 3 · propose freeze",
};

export default function ReviewQueuePage() {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [imageGaps, setImageGaps] = useState<ImageGap[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [minTier, setMinTier] = useState<1 | 2 | 3>(1);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [manualInput, setManualInput] = useState("");
  const [manualBusy, setManualBusy] = useState(false);

  useEffect(() => {
    if (!hasAdminToken()) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetch(`${API}/api/v1/admin/hitl/review-queue?min_tier=${minTier}&limit=200`, {
        headers: adminHeaders(),
        cache: "no-store",
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(`${API}/api/v1/admin/hitl/stories-without-image?limit=30`, {
        headers: adminHeaders(),
        cache: "no-store",
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]).then(([q, g]) => {
      if (cancelled) return;
      setQueue(q || { items: [], tier_counts: {} });
      setImageGaps(g?.stories || []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [minTier]);

  const items = useMemo(() => queue?.items || [], [queue]);

  const freeze = async (storyId: string) => {
    setBusyId(storyId);
    setMsg(null);
    const res = await fetch(
      `${API}/api/v1/admin/hitl/stories/${storyId}/freeze`,
      { method: "POST", headers: adminHeaders() }
    );
    setBusyId(null);
    if (res.ok) {
      setQueue((q) =>
        q ? { ...q, items: q.items.filter((i) => i.story_id !== storyId) } : q
      );
      setMsg(`Frozen ${storyId.slice(0, 8)} · matcher will skip it from now on.`);
    } else {
      setMsg("Freeze failed.");
    }
  };

  // Accept either a bare UUID or any URL containing one — pasting the
  // /fa/stories/<id> URL from the address bar is the common case.
  const UUID_RE =
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

  const manualAction = async (action: "freeze" | "unfreeze") => {
    const match = manualInput.trim().match(UUID_RE);
    if (!match) {
      setMsg("Could not find a story UUID in that input.");
      return;
    }
    const storyId = match[0];
    setManualBusy(true);
    setMsg(null);
    const res = await fetch(
      `${API}/api/v1/admin/hitl/stories/${storyId}/${action}`,
      { method: "POST", headers: adminHeaders() }
    );
    setManualBusy(false);
    if (res.ok) {
      if (action === "freeze") {
        setQueue((q) =>
          q ? { ...q, items: q.items.filter((i) => i.story_id !== storyId) } : q
        );
        setMsg(
          `Frozen ${storyId.slice(0, 8)} · matcher will skip it from now on.`
        );
      } else {
        setMsg(
          `Unfrozen ${storyId.slice(0, 8)} · matcher will re-evaluate next pass.`
        );
      }
      setManualInput("");
    } else {
      const err = await res.json().catch(() => ({}));
      setMsg(err.detail || `${action} failed.`);
    }
  };

  if (!hasAdminToken()) {
    return (
      <div>
        <h1 className="text-xl font-black mb-2">Review Queue</h1>
        <p className="text-[13px] text-slate-500">
          Admin token required. Set it via the HITL landing page first.
        </p>
      </div>
    );
  }

  const totals = queue?.tier_counts || {};
  const grandTotal =
    (Number(totals["1"]) || 0) +
    (Number(totals["2"]) || 0) +
    (Number(totals["3"]) || 0);

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <h1 className="text-xl font-black text-slate-900 dark:text-white">
          Review Queue
        </h1>
        <Link
          href="/fa/dashboard/hitl/help"
          className="text-[12px] text-blue-500"
        >
          What do these tiers mean? →
        </Link>
      </div>
      <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-6">
        Stories the guardrail pass flagged as too big, too old, or too
        single-source. Image gaps listed separately so the picker doesn't
        conflict with the freeze workflow.
      </p>

      {/* Manual freeze/unfreeze — for stories you already know are over
          and don't want to wait for the guardrail to flag. Accepts the
          story page URL or a bare UUID. */}
      <div className="mb-4 border border-slate-200 dark:border-slate-800 p-3">
        <div className="text-[12px] font-black text-slate-700 dark:text-slate-300 mb-1">
          Freeze a specific story
        </div>
        <p className="text-[11px] text-slate-500 mb-2">
          Paste the story page URL or its UUID. Freezing tells the matcher to
          stop attaching new articles. Unfreeze re-opens it.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={manualInput}
            onChange={(e) => setManualInput(e.target.value)}
            onKeyDown={(e) =>
              e.key === "Enter" && !manualBusy && manualAction("freeze")
            }
            placeholder="https://doornegar.org/fa/stories/<uuid>  or  <uuid>"
            dir="ltr"
            className="flex-1 px-2 py-1 text-[12px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
          />
          <button
            type="button"
            onClick={() => manualAction("freeze")}
            disabled={manualBusy || !manualInput.trim()}
            className="text-[12px] px-3 py-1 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
          >
            {manualBusy ? "…" : "Freeze"}
          </button>
          <button
            type="button"
            onClick={() => manualAction("unfreeze")}
            disabled={manualBusy || !manualInput.trim()}
            className="text-[12px] px-3 py-1 border border-slate-300 dark:border-slate-700 disabled:opacity-40"
          >
            Unfreeze
          </button>
        </div>
      </div>

      {/* Tier count pills + filter */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-[11px] text-slate-500">Filter:</span>
        {[1, 2, 3].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setMinTier(t as 1 | 2 | 3)}
            className={`text-[12px] px-2.5 py-1 border ${
              minTier === t
                ? TIER_STYLE[t]
                : "border-slate-300 dark:border-slate-700 text-slate-500"
            }`}
          >
            ≥ {TIER_LABEL[t]} ({totals[String(t)] || 0})
          </button>
        ))}
        <span className="text-[11px] text-slate-400 ml-auto">
          {grandTotal} stories flagged · {imageGaps?.length ?? 0} image gaps
        </span>
      </div>

      {msg && (
        <div className="text-[12px] text-emerald-600 dark:text-emerald-400 mb-3 border border-emerald-200 dark:border-emerald-800 px-3 py-2">
          {msg}
        </div>
      )}

      {/* Main queue */}
      {loading && (
        <div className="text-[12px] text-slate-400 py-6">Loading…</div>
      )}
      {!loading && items.length === 0 && (
        <div className="text-[12px] text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 px-3 py-4">
          ✓ Nothing at tier ≥ {minTier}. Nice and quiet.
        </div>
      )}
      {!loading && items.length > 0 && (
        <div className="border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800">
          {items.map((i) => (
            <div key={i.story_id} className="flex items-center gap-3 px-3 py-2">
              <span
                className={`text-[10px] font-black px-1.5 py-0.5 border ${
                  TIER_STYLE[i.review_tier] || TIER_STYLE[1]
                }`}
              >
                T{i.review_tier}
              </span>
              <div className="flex-1 min-w-0">
                <Link
                  href={`/fa/stories/${i.story_id}`}
                  target="_blank"
                  className="block text-[13px] text-slate-800 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 truncate"
                >
                  {i.title_fa || "(untitled)"}
                </Link>
                <div
                  className="text-[11px] text-slate-400 mt-0.5"
                  dir="ltr"
                >
                  {i.article_count} article{i.article_count === 1 ? "" : "s"} ·{" "}
                  {i.source_count} source{i.source_count === 1 ? "" : "s"}
                  {i.age_days !== null && <> · span {i.age_days.toFixed(1)}d</>}
                  {i.source_count === 1 && (
                    <>
                      {" · "}
                      <span className="text-amber-600 dark:text-amber-400">
                        single-source
                      </span>
                    </>
                  )}
                  {i.arc_id && (
                    <>
                      {" · "}
                      <Link
                        href={`/fa/stories/${i.story_id}`}
                        className="text-blue-500"
                      >
                        in arc
                      </Link>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Link
                  href={`/fa/dashboard/hitl/narrative/${i.story_id}`}
                  className="text-[11px] px-2 py-1 border border-slate-300 dark:border-slate-700"
                >
                  Narrative
                </Link>
                <button
                  type="button"
                  onClick={() => freeze(i.story_id)}
                  disabled={busyId === i.story_id}
                  className="text-[11px] px-2 py-1 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
                >
                  {busyId === i.story_id ? "…" : "Freeze"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Image gap panel */}
      <div className="mt-8 border border-slate-200 dark:border-slate-800 p-4">
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-[13px] font-black text-slate-900 dark:text-white">
            Image gaps
          </h2>
          <span className="text-[11px] text-slate-400">
            {imageGaps?.length ?? 0} stories · priority-sorted
          </span>
        </div>
        {imageGaps && imageGaps.length === 0 && (
          <p className="text-[12px] text-emerald-600 dark:text-emerald-400">
            ✓ No high-priority stories missing an image.
          </p>
        )}
        {imageGaps && imageGaps.length > 0 && (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {imageGaps.slice(0, 10).map((g) => (
              <li key={g.id} className="py-2 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/fa/stories/${g.id}`}
                    target="_blank"
                    className="block text-[13px] text-slate-800 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 truncate"
                  >
                    {g.title_fa || "(untitled)"}
                  </Link>
                  <div className="text-[11px] text-slate-400 mt-0.5" dir="ltr">
                    {g.source_count} source{g.source_count === 1 ? "" : "s"} ·{" "}
                    {g.article_count} article{g.article_count === 1 ? "" : "s"}
                  </div>
                </div>
                <Link
                  href={`/fa/dashboard/hitl/stock-images/${g.id}`}
                  className="shrink-0 text-[11px] px-2 py-1 bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                >
                  Pick image
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
