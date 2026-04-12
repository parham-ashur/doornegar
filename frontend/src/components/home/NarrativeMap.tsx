"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type { StoryBrief } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SourceAlignment = "state" | "semi_state" | "independent" | "diaspora";

interface ArticlePosition {
  article_id: string;
  title_fa: string;
  source_slug: string;
  source_alignment: SourceAlignment;
  x: number;
  y: number;
}

interface DotData {
  article_id: string;
  title_fa: string;
  source_slug: string;
  x: number;
  y: number;
  color: "conservative" | "opposition" | "independent";
}

function alignmentToColor(alignment: SourceAlignment): DotData["color"] {
  switch (alignment) {
    case "state":
    case "semi_state":
      return "conservative";
    case "diaspora":
      return "opposition";
    case "independent":
    default:
      return "independent";
  }
}

/** Fallback: generate positions from alignment percentages when API is unavailable */
function generateFallbackDots(s: StoryBrief): DotData[] {
  const dots: DotData[] = [];
  const seed = s.article_count * 7;

  const cCount = Math.round(s.article_count * (s.state_pct || 0) / 100);
  for (let i = 0; i < cCount; i++) {
    const hash = (seed + i * 13) % 1000;
    dots.push({
      article_id: `fallback-c-${i}`,
      title_fa: "",
      source_slug: "",
      x: 60 + (hash % 30),
      y: 15 + ((hash * 7) % 70),
      color: "conservative",
    });
  }

  const oCount = Math.round(s.article_count * (s.diaspora_pct || 0) / 100);
  for (let i = 0; i < oCount; i++) {
    const hash = (seed + i * 17 + 500) % 1000;
    dots.push({
      article_id: `fallback-o-${i}`,
      title_fa: "",
      source_slug: "",
      x: 10 + (hash % 30),
      y: 15 + ((hash * 7) % 70),
      color: "opposition",
    });
  }

  return dots;
}

function mapPositionsToDots(positions: ArticlePosition[]): DotData[] {
  return positions.map((p) => ({
    article_id: p.article_id,
    title_fa: p.title_fa,
    source_slug: p.source_slug,
    x: p.x,
    y: p.y,
    color: alignmentToColor(p.source_alignment),
  }));
}

export default function NarrativeMap({ stories }: { stories: StoryBrief[] }) {
  const [selected, setSelected] = useState<string | null>(stories[0]?.id || null);
  const [dots, setDots] = useState<DotData[]>([]);
  const [loading, setLoading] = useState(false);
  const [hoveredDot, setHoveredDot] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const cacheRef = useRef<Map<string, DotData[]>>(new Map());

  const active = stories.find((s) => s.id === selected);

  const fetchPositions = useCallback(
    async (storyId: string) => {
      // Return cached data if available
      const cached = cacheRef.current.get(storyId);
      if (cached) {
        setDots(cached);
        return;
      }

      const story = stories.find((s) => s.id === storyId);
      setLoading(true);

      try {
        const res = await fetch(
          `${API_BASE}/api/v1/stories/${storyId}/article-positions`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const positions: ArticlePosition[] = await res.json();
        const mapped = mapPositionsToDots(positions);
        cacheRef.current.set(storyId, mapped);
        setDots(mapped);
      } catch {
        // Fall back to alignment-based positioning
        if (story) {
          const fallback = generateFallbackDots(story);
          cacheRef.current.set(storyId, fallback);
          setDots(fallback);
        } else {
          setDots([]);
        }
      } finally {
        setLoading(false);
      }
    },
    [stories]
  );

  useEffect(() => {
    if (selected) {
      fetchPositions(selected);
    } else {
      setDots([]);
    }
  }, [selected, fetchPositions]);

  const dotColorClasses: Record<DotData["color"], string> = {
    conservative: "bg-[#1e3a5f] dark:bg-blue-400",
    opposition: "bg-[#ea580c] dark:bg-orange-400",
    independent: "bg-slate-400 dark:bg-slate-500",
  };

  return (
    <div dir="rtl" className="grid grid-cols-12 gap-0" style={{ minHeight: 350 }}>
      {/* Right: Story list */}
      <div ref={listRef} className="col-span-4 border-l border-slate-200 dark:border-slate-800 pl-4 overflow-y-auto" style={{ maxHeight: 380 }}>
        {stories.slice(0, 15).map((s, i) => (
          <button
            key={s.id}
            onClick={() => setSelected(s.id)}
            className={`w-full text-right block py-3 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800/60" : ""} transition-colors ${
              selected === s.id
                ? "bg-slate-50 dark:bg-slate-800/50"
                : "hover:bg-slate-50 dark:hover:bg-slate-800/30"
            }`}
          >
            <h4 className={`text-[13px] font-bold leading-snug line-clamp-2 ${
              selected === s.id ? "text-blue-700 dark:text-blue-400" : "text-slate-900 dark:text-white"
            }`}>
              {s.title_fa}
            </h4>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {s.article_count} مقاله
              {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · {s.state_pct}٪</span>}
              {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · {s.diaspora_pct}٪</span>}
            </p>
          </button>
        ))}
      </div>

      {/* Left: Scatter plot of articles */}
      <div className="col-span-8 pr-4 relative" style={{ height: 380 }}>
        {/* Center line */}
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-slate-100 dark:bg-slate-800/50" />

        {/* Side labels */}
        <div className="absolute right-4 top-3 text-[11px] font-medium text-[#1e3a5f] dark:text-blue-300">محافظه‌کار</div>
        <div className="absolute left-4 top-3 text-[11px] font-medium text-[#ea580c] dark:text-orange-400">اپوزیسیون</div>

        {/* Loading indicator */}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex items-center gap-2 text-[12px] text-slate-400 dark:text-slate-500">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span>بارگذاری...</span>
            </div>
          </div>
        )}

        {/* Article dots */}
        {!loading && dots.map((d) => (
          <div
            key={d.article_id}
            className="absolute transition-all duration-500"
            style={{
              left: `${d.x}%`,
              top: `${d.y}%`,
              transform: "translate(-50%, -50%)",
            }}
            onMouseEnter={() => { if (d.title_fa) setHoveredDot(d.article_id); }}
            onMouseLeave={() => setHoveredDot(null)}
          >
            <div
              className={`rounded-full ${dotColorClasses[d.color]} opacity-50 hover:opacity-90 transition-opacity cursor-default`}
              style={{ width: 8, height: 8 }}
            />
            {/* Tooltip */}
            {hoveredDot === d.article_id && d.title_fa && (
              <div
                className="absolute z-20 bottom-full left-1/2 -translate-x-1/2 mb-2 pointer-events-none"
                style={{ width: "max-content", maxWidth: 220 }}
              >
                <div className="bg-slate-900 dark:bg-slate-700 text-white text-[11px] leading-snug px-2.5 py-1.5 rounded shadow-lg">
                  <p className="line-clamp-2">{d.title_fa}</p>
                  {d.source_slug && (
                    <p className="text-slate-400 text-[10px] mt-0.5">{d.source_slug}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Story info */}
        {active && !loading && (
          <div className="absolute bottom-3 left-3 right-3">
            <p className="text-[12px] text-slate-500 dark:text-slate-400 text-center">
              <span className="text-[#1e3a5f] dark:text-blue-300 font-medium">{Math.round(active.article_count * (active.state_pct || 0) / 100)} مقاله محافظه‌کار</span>
              {" · "}
              <span className="text-[#ea580c] dark:text-orange-400 font-medium">{Math.round(active.article_count * (active.diaspora_pct || 0) / 100)} مقاله اپوزیسیون</span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
