"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { adminHeaders, hasAdminToken } from "./_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ImageGap = {
  id: string;
  slug: string;
  title_fa: string;
  article_count: number;
  source_count: number;
  first_published_at: string | null;
  trending_score: number;
};

export default function HitlIndex() {
  const router = useRouter();
  const [storyId, setStoryId] = useState("");
  const [gaps, setGaps] = useState<ImageGap[] | null>(null);
  const [loadingGaps, setLoadingGaps] = useState(false);

  // Fetch stories needing cover images on mount (admin-gated endpoint;
  // page already assumes an admin token exists in localStorage).
  useEffect(() => {
    if (!hasAdminToken()) return;
    let cancelled = false;
    setLoadingGaps(true);
    fetch(`${API}/api/v1/admin/hitl/stories-without-image?limit=30`, {
      headers: adminHeaders(),
      cache: "no-store",
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (cancelled) return;
        setGaps(d?.stories || []);
      })
      .catch(() => {
        if (!cancelled) setGaps([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingGaps(false);
      });
    return () => { cancelled = true; };
  }, []);

  const tiles = [
    {
      href: "/fa/dashboard/hitl/help",
      title: "Tooling guide",
      desc: "What each tool does, when to use it, and the API path for each.",
    },
    {
      href: "/fa/dashboard/hitl/submissions",
      title: "User submissions",
      desc: "Review content submitted via /submit and attach to the right story.",
    },
    {
      href: "/fa/dashboard/hitl/telegram-triage",
      title: "Telegram triage queue",
      desc: "Borderline posts (0.30–0.40) that weren't auto-attached. Pick the best story manually.",
    },
    {
      href: "/fa/dashboard/hitl/channels",
      title: "Channel classification",
      desc: "Sample each channel's posts and fix its type (news, analyst, repost, etc.).",
    },
    {
      href: "/fa/dashboard/hitl/sources",
      title: "Source classification",
      desc: "Production location, state alignment, political faction per outlet — edit here so the 4-subgroup taxonomy (principlist / reformist / moderate / radical) stays accurate.",
    },
    {
      href: "/fa/dashboard/hitl/arcs",
      title: "Narrative arcs",
      desc: "Suggest and build narrative arcs — related stories that unfold in sequence.",
    },
  ];

  const extractId = (v: string): string | null => {
    const trimmed = v.trim();
    if (!trimmed) return null;
    const match = trimmed.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    return match ? match[0] : null;
  };

  const go = (kind: "stock-images" | "narrative") => {
    const id = extractId(storyId);
    if (!id) return;
    router.push(`/fa/dashboard/hitl/${kind}/${id}`);
  };

  return (
    <div dir="ltr">
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-4">
        Human-in-the-Loop tools
      </h1>
      <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-6 leading-6">
        These tools cover the places where automation is wrong or uncertain.
        Each touchpoint has a small queue — a few minutes a day keeps it clean.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tiles.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="block border border-slate-200 dark:border-slate-800 p-4 hover:border-blue-400 transition-colors"
          >
            <h2 className="text-[13px] font-black text-slate-900 dark:text-white mb-1">
              {t.title}
            </h2>
            <p className="text-[13px] text-slate-500 dark:text-slate-400 leading-6">
              {t.desc}
            </p>
          </Link>
        ))}
      </div>

      {/* Stories without a cover image — queue of work */}
      <div className="mt-8 border border-slate-200 dark:border-slate-800 p-4">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-[13px] font-black text-slate-900 dark:text-white">
            Stories without image
          </h2>
          <span className="text-[11px] text-slate-400">
            {loadingGaps
              ? "Loading…"
              : gaps
              ? `${gaps.length} ${gaps.length === 1 ? "story" : "stories"}`
              : ""}
          </span>
        </div>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-3 leading-6">
          These stories used to fall back to a source logo on the homepage.
          Pick a better image from Unsplash so the card renders cleanly.
        </p>
        {gaps && gaps.length === 0 && !loadingGaps && (
          <p className="text-[13px] text-emerald-600 dark:text-emerald-400">
            ✓ No high-priority stories missing an image.
          </p>
        )}
        {gaps && gaps.length > 0 && (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {gaps.map((g) => (
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
                    {g.first_published_at && (
                      <> · {new Date(g.first_published_at).toLocaleDateString("en-US")}</>
                    )}
                  </div>
                </div>
                <Link
                  href={`/fa/dashboard/hitl/stock-images/${g.id}`}
                  className="shrink-0 text-[12px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90"
                >
                  Pick image
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-6 border border-slate-200 dark:border-slate-800 p-4">
        <h2 className="text-[13px] font-black text-slate-900 dark:text-white mb-1">
          Edit a specific story
        </h2>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-3 leading-6">
          Paste a story URL or UUID — jumps straight to the image picker or
          narrative editor.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            dir="ltr"
            value={storyId}
            onChange={(e) => setStoryId(e.target.value)}
            placeholder="https://doornegar.org/fa/stories/… or UUID"
            className="flex-1 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-[13px] px-2 py-1.5"
          />
          <button
            type="button"
            onClick={() => go("stock-images")}
            disabled={!extractId(storyId)}
            className="text-[13px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
          >
            Pick image
          </button>
          <button
            type="button"
            onClick={() => go("narrative")}
            disabled={!extractId(storyId)}
            className="text-[13px] font-bold px-3 py-1.5 border border-slate-300 dark:border-slate-700 disabled:opacity-40"
          >
            Edit narrative
          </button>
        </div>
      </div>
    </div>
  );
}
