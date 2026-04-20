"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DriftChapter {
  story_id: string;
  title_fa: string | null;
  first_published_at: string | null;
  order: number;
  inside_word: string;
  outside_word: string;
}

interface DriftData {
  arc_id: string;
  title_fa: string;
  chapters: DriftChapter[];
}

/**
 * روایت در حال تغییر — visualizes how each side's dominant framing
 * word shifted across the chapters of an arc. One row per side, each
 * chapter's representative word is pulled from its `loaded_words`
 * analysis. Current chapter is highlighted. Arrow glyphs signal
 * chronological direction (RTL).
 *
 * Purely visual — clicking a word navigates to that chapter's story.
 */
export default function NarrativeDriftPanel({
  arcId,
  currentStoryId,
  locale,
}: {
  arcId: string;
  currentStoryId: string;
  locale: string;
}) {
  const [data, setData] = useState<DriftData | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/v1/arcs/${arcId}/drift`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setErr(true);
      });
    return () => {
      cancelled = true;
    };
  }, [arcId]);

  if (err || !data || data.chapters.length < 2) return null;

  // Only render if at least one chapter has a word on either side —
  // otherwise the strip is just four dashes and wastes space.
  const hasAnyWord = data.chapters.some((c) => c.inside_word || c.outside_word);
  if (!hasAnyWord) return null;

  const renderRow = (
    label: string,
    color: string,
    getter: (c: DriftChapter) => string,
  ) => (
    <div className="flex items-center gap-2 flex-wrap">
      <span
        className="text-[12px] font-bold shrink-0"
        style={{ color }}
      >
        {label}
      </span>
      {data.chapters.map((c, i) => {
        const word = getter(c);
        const isCurrent = c.story_id === currentStoryId;
        const isLast = i === data.chapters.length - 1;
        const display = word ? `«${word}»` : "—";
        const wordEl = isCurrent ? (
          <span
            className="text-[13px] font-black px-1.5 py-0.5"
            style={{ color, backgroundColor: `${color}1A` }}
          >
            {display}
            <span className="mr-1">✨</span>
          </span>
        ) : (
          <a
            href={`/${locale}/stories/${c.story_id}`}
            className="text-[13px] text-slate-600 dark:text-slate-400 hover:underline"
            style={{ color: word ? undefined : "#9ca3af" }}
          >
            {display}
          </a>
        );
        return (
          <span key={c.story_id} className="flex items-center gap-1.5">
            {wordEl}
            {!isLast && (
              <span className="text-slate-300 dark:text-slate-600 text-[12px]">←</span>
            )}
          </span>
        );
      })}
    </div>
  );

  return (
    <div
      dir="rtl"
      className="mt-4 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 p-3"
    >
      <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">
        روایت در حال تغییر
      </p>
      <div className="space-y-2">
        {renderRow("درون‌مرزی:", "#1e3a5f", (c) => c.inside_word)}
        {renderRow("برون‌مرزی:", "#c2410c", (c) => c.outside_word)}
      </div>
      <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-3 leading-5">
        واژهٔ بارگذاری‌شدهٔ غالب هر طرف در چپترهای قوس. ✨ چپتر فعلی را نشان می‌دهد.
      </p>
    </div>
  );
}
