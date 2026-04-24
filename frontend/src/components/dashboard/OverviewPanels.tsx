"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminHeaders } from "@/app/[locale]/dashboard/hitl/_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Compact overview panels — 7-day cost + ingest health + review
 * queue load — rendered on the Overview page so the daily check-in
 * doesn't require three extra clicks. Each card is a link to the
 * full-detail view.
 */
export default function OverviewPanels() {
  const [cost, setCost] = useState<{ total_cost: number; calls: number } | null>(null);
  const [ingest, setIngest] = useState<{ stale_sources: number; stale_channels: number } | null>(null);
  const [queue, setQueue] = useState<{ t1: number; t2: number; t3: number; images: number } | null>(null);

  useEffect(() => {
    const h = adminHeaders();
    // 7-day cost summary
    fetch(`${API}/api/v1/admin/cost/summary?window=7d`, { headers: h, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        setCost({
          total_cost: Number(d.total_cost || 0),
          calls: Number(d.total_calls || 0),
        });
      })
      .catch(() => {});

    // Ingest staleness counts — sources + channels
    Promise.all([
      fetch(`${API}/api/v1/admin/sources/stats`, { headers: h, cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(`${API}/api/v1/admin/channels/stats`, { headers: h, cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]).then(([srcs, chans]) => {
      const staleSrc = (srcs?.items || []).filter(
        (s: { is_stale?: boolean }) => s.is_stale
      ).length;
      const staleCh = (chans?.items || []).filter(
        (c: { is_stale?: boolean }) => c.is_stale
      ).length;
      setIngest({ stale_sources: staleSrc, stale_channels: staleCh });
    });

    // Review queue tier counts + image gaps
    Promise.all([
      fetch(`${API}/api/v1/admin/hitl/review-queue?min_tier=1&limit=1`, {
        headers: h,
        cache: "no-store",
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(`${API}/api/v1/admin/hitl/stories-without-image?limit=1`, {
        headers: h,
        cache: "no-store",
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]).then(([q, gaps]) => {
      const tc = q?.tier_counts || {};
      setQueue({
        t1: Number(tc["1"]) || 0,
        t2: Number(tc["2"]) || 0,
        t3: Number(tc["3"]) || 0,
        images: Number(gaps?.count) || 0,
      });
    });
  }, []);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
      <Card
        href="/fa/dashboard/review-queue"
        title="Review queue"
        loading={!queue}
      >
        {queue && (
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {queue.t3}
            </span>
            <span className="text-[12px] text-slate-500">
              tier 3 · {queue.t2} t2 · {queue.t1} t1 · {queue.images} image gaps
            </span>
          </div>
        )}
      </Card>

      <Card
        href="/fa/dashboard/cost"
        title="Cost · last 7 days"
        loading={!cost}
      >
        {cost && (
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              ${cost.total_cost.toFixed(2)}
            </span>
            <span className="text-[12px] text-slate-500">
              {cost.calls.toLocaleString()} LLM calls
            </span>
          </div>
        )}
      </Card>

      <Card
        href="/fa/dashboard/fetch-stats"
        title="Ingest health"
        loading={!ingest}
      >
        {ingest && (
          <div className="flex items-baseline gap-3">
            <span
              className={`text-2xl font-black ${
                ingest.stale_sources + ingest.stale_channels > 0
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-slate-900 dark:text-white"
              }`}
            >
              {ingest.stale_sources + ingest.stale_channels}
            </span>
            <span className="text-[12px] text-slate-500">
              stale · {ingest.stale_sources} sources · {ingest.stale_channels}{" "}
              channels
            </span>
          </div>
        )}
      </Card>
    </div>
  );
}

function Card({
  href,
  title,
  loading,
  children,
}: {
  href: string;
  title: string;
  loading: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="block border border-slate-200 dark:border-slate-800 p-3 hover:border-blue-400 transition-colors"
    >
      <div className="text-[11px] font-black uppercase tracking-wide text-slate-500 mb-2">
        {title}
      </div>
      {loading ? (
        <div className="text-[12px] text-slate-400">Loading…</div>
      ) : (
        children
      )}
    </Link>
  );
}
