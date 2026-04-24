"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { adminHeaders, hasAdminToken } from "./_auth";
import {
  Inbox,
  Send,
  Radio,
  Newspaper,
  GitBranch,
  Image as ImageIcon,
  FileText,
  AlertTriangle,
  Snowflake,
  Split,
  History,
  HelpCircle,
  ExternalLink,
} from "lucide-react";

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

  useEffect(() => {
    if (!hasAdminToken()) return;
    let cancelled = false;
    setLoadingGaps(true);
    fetch(`${API}/api/v1/admin/hitl/stories-without-image?limit=30`, {
      headers: adminHeaders(),
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled) return;
        setGaps(d?.stories || []);
      })
      .catch(() => {
        if (!cancelled) setGaps([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingGaps(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const extractId = (v: string): string | null => {
    const trimmed = v.trim();
    if (!trimmed) return null;
    const match = trimmed.match(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
    );
    return match ? match[0] : null;
  };

  const go = (kind: "stock-images" | "narrative") => {
    const id = extractId(storyId);
    if (!id) return;
    router.push(`/fa/dashboard/hitl/${kind}/${id}`);
  };

  return (
    <div dir="ltr">
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-1">
        Human-in-the-Loop
      </h1>
      <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-5 leading-6">
        Tools for the places where automation is wrong or unsure. Each
        touchpoint has a small queue — a few minutes a day keeps it clean.
      </p>

      {/* Tooling guide banner — always visible at top so the controls
          aren't a pile of unmarked icons. Lives here so the user doesn't
          have to click a tile to find out what everything does. */}
      <GuideBanner />

      {/* Primary tools grid with icons */}
      <h2 className="text-[12px] font-black uppercase tracking-wide text-slate-500 mb-2">
        Queues & editors
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
        <Tile
          icon={<Send className="w-5 h-5" />}
          href="/fa/dashboard/review-queue"
          title="Review queue"
          desc="Stories flagged by the guardrail pass: too big, too old, or single-source. Freeze or split."
          accent="red"
        />
        <Tile
          icon={<Radio className="w-5 h-5" />}
          href="/fa/dashboard/hitl/telegram-triage"
          title="Telegram triage"
          desc="Borderline posts (0.30–0.40 match score) not auto-attached. Pick the right story or unlink."
          accent="blue"
        />
        <Tile
          icon={<Inbox className="w-5 h-5" />}
          href="/fa/dashboard/hitl/submissions"
          title="User submissions"
          desc="Review articles and posts submitted via /submit and attach to the right story."
          accent="indigo"
        />
        <Tile
          icon={<GitBranch className="w-5 h-5" />}
          href="/fa/dashboard/hitl/arcs"
          title="Narrative arcs"
          desc="Build arcs from related stories that play out in sequence. Auto-suggested by centroid cosine ≥ 0.55."
          accent="violet"
        />
        <Tile
          icon={<Newspaper className="w-5 h-5" />}
          href="/fa/dashboard/hitl/sources"
          title="Outlet classification"
          desc="Sources (RSS) and Telegram channels in one tabbed area. Fix location, alignment, and faction here."
          accent="slate"
        />
        <Tile
          icon={<FileText className="w-5 h-5" />}
          href="/fa/dashboard/edit-stories"
          title="Story editor"
          desc="Titles, side narratives, and bias comparison across top stories. Manual edits stick."
          accent="emerald"
        />
      </div>

      {/* Image gap queue inline — priority sorted, one-click to picker */}
      <div className="mb-8 border border-slate-200 dark:border-slate-800 p-4">
        <div className="flex items-baseline justify-between mb-3">
          <div className="flex items-center gap-2">
            <ImageIcon className="w-4 h-4 text-slate-500" />
            <h2 className="text-[13px] font-black text-slate-900 dark:text-white">
              Stories without image
            </h2>
          </div>
          <span className="text-[11px] text-slate-400">
            {loadingGaps
              ? "Loading…"
              : gaps
              ? `${gaps.length} ${gaps.length === 1 ? "story" : "stories"}`
              : ""}
          </span>
        </div>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-3 leading-6">
          These stories have no real cover image and are hidden from the
          homepage and related-stories list until one is picked. Highest
          trending-score first.
        </p>
        {gaps && gaps.length === 0 && !loadingGaps && (
          <p className="text-[13px] text-emerald-600 dark:text-emerald-400">
            ✓ No high-priority stories missing an image.
          </p>
        )}
        {gaps && gaps.length > 0 && (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {gaps.slice(0, 10).map((g) => (
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
                  className="shrink-0 text-[12px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 inline-flex items-center gap-1"
                >
                  <ImageIcon className="w-3 h-3" />
                  Pick image
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Edit a specific story */}
      <div className="border border-slate-200 dark:border-slate-800 p-4">
        <h2 className="text-[13px] font-black text-slate-900 dark:text-white mb-1">
          Jump to a specific story
        </h2>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-3 leading-6">
          Paste a story URL or UUID — jumps straight to the image picker or
          narrative editor for that story.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            dir="ltr"
            value={storyId}
            onChange={(e) => setStoryId(e.target.value)}
            placeholder="https://doornegar.org/fa/stories/… or UUID"
            className="flex-1 min-w-[240px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-[13px] px-2 py-1.5"
          />
          <button
            type="button"
            onClick={() => go("stock-images")}
            disabled={!extractId(storyId)}
            className="text-[13px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40 inline-flex items-center gap-1"
          >
            <ImageIcon className="w-3.5 h-3.5" /> Pick image
          </button>
          <button
            type="button"
            onClick={() => go("narrative")}
            disabled={!extractId(storyId)}
            className="text-[13px] font-bold px-3 py-1.5 border border-slate-300 dark:border-slate-700 disabled:opacity-40 inline-flex items-center gap-1"
          >
            <FileText className="w-3.5 h-3.5" /> Edit narrative
          </button>
        </div>
      </div>
    </div>
  );
}

function Tile({
  icon,
  href,
  title,
  desc,
  accent,
}: {
  icon: React.ReactNode;
  href: string;
  title: string;
  desc: string;
  accent: "red" | "blue" | "indigo" | "violet" | "slate" | "emerald";
}) {
  const accentClasses: Record<typeof accent, string> = {
    red: "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border-red-100 dark:border-red-900/40",
    blue: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 border-blue-100 dark:border-blue-900/40",
    indigo: "text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 border-indigo-100 dark:border-indigo-900/40",
    violet: "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-900/20 border-violet-100 dark:border-violet-900/40",
    slate: "text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/40 border-slate-200 dark:border-slate-800",
    emerald: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-100 dark:border-emerald-900/40",
  };
  return (
    <Link
      href={href}
      className="group block border border-slate-200 dark:border-slate-800 p-3 hover:border-blue-400 transition-colors"
    >
      <div className="flex items-start gap-3 mb-2">
        <div className={`shrink-0 w-9 h-9 flex items-center justify-center border ${accentClasses[accent]}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-[13px] font-black text-slate-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
            {title}
          </h3>
        </div>
        <ExternalLink className="shrink-0 w-3 h-3 text-slate-300 group-hover:text-blue-400" />
      </div>
      <p className="text-[12px] text-slate-500 dark:text-slate-400 leading-5">
        {desc}
      </p>
    </Link>
  );
}

function GuideBanner() {
  return (
    <div className="mb-6 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 p-4">
      <div className="flex items-start gap-3 mb-3">
        <HelpCircle className="shrink-0 w-5 h-5 text-blue-500 mt-0.5" />
        <div className="flex-1">
          <h2 className="text-[13px] font-black text-slate-900 dark:text-white mb-1">
            Tooling guide
          </h2>
          <p className="text-[12px] text-slate-500 dark:text-slate-400 leading-5">
            Quick reference for what each control does and when to use it.
          </p>
        </div>
        <Link
          href="/fa/dashboard/hitl/help"
          className="shrink-0 text-[11px] text-blue-500 hover:underline"
        >
          Full guide →
        </Link>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-[12px] text-slate-600 dark:text-slate-400 leading-5">
        <GuideItem
          icon={<AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
          name="Review queue"
          meaning="Stories flagged at tier 1/2/3 for size or age. Tier 3 = propose freeze."
        />
        <GuideItem
          icon={<Snowflake className="w-3.5 h-3.5 text-blue-500" />}
          name="Freeze"
          meaning="Stop new articles attaching. Use after an event ends. Reversible."
        />
        <GuideItem
          icon={<Split className="w-3.5 h-3.5 text-violet-500" />}
          name="Split"
          meaning="Carve one cluster into N children, optionally wrapped in an arc."
        />
        <GuideItem
          icon={<GitBranch className="w-3.5 h-3.5 text-violet-500" />}
          name="Arc scaffold"
          meaning='Outline an A→B→C→D narrative, system matches or creates chapters.'
        />
        <GuideItem
          icon={<Radio className="w-3.5 h-3.5 text-sky-500" />}
          name="Telegram triage"
          meaning="Borderline auto-link decisions between 0.30 and 0.40 match score."
        />
        <GuideItem
          icon={<History className="w-3.5 h-3.5 text-slate-500" />}
          name="Story events"
          meaning="Every pipeline decision + HITL action logged per story."
        />
      </div>
    </div>
  );
}

function GuideItem({
  icon,
  name,
  meaning,
}: {
  icon: React.ReactNode;
  name: string;
  meaning: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="shrink-0 mt-0.5">{icon}</span>
      <div className="flex-1 min-w-0">
        <span className="font-black text-slate-900 dark:text-white">{name}</span>
        <span className="text-slate-500 dark:text-slate-400"> — {meaning}</span>
      </div>
    </div>
  );
}
