"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import type { StoryBrief } from "@/lib/types";
import { toFa } from "@/lib/utils";

type SourceAlignment = "state" | "semi_state" | "independent" | "diaspora";

interface ArticlePosition {
  article_id: string;
  title_fa: string;
  source_slug: string;
  source_name_fa?: string;
  source_logo_url?: string;
  article_url?: string;
  source_alignment: SourceAlignment;
  x: number;
  y: number;
}

interface DotData {
  article_id: string;
  title_fa: string;
  source_slug: string;
  source_name_fa?: string;
  source_logo_url?: string;
  article_url?: string;
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
    source_name_fa: p.source_name_fa,
    source_logo_url: p.source_logo_url,
    article_url: p.article_url,
    x: p.x,
    y: p.y,
    color: alignmentToColor(p.source_alignment),
  }));
}

export default function NarrativeMap({ stories, prefetchedPositions }: { stories: StoryBrief[]; prefetchedPositions?: Record<string, ArticlePosition[]> }) {
  const [selected, setSelected] = useState<string | null>(stories[0]?.id || null);
  const [hoveredDot, setHoveredDot] = useState<string | null>(null);
  const [clickedDot, setClickedDot] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const active = stories.find((s) => s.id === selected);

  // Build cache from prefetched data (computed once, not in effect)
  const cache = useRef<Record<string, DotData[]>>({});
  if (prefetchedPositions && Object.keys(cache.current).length === 0) {
    for (const [storyId, positions] of Object.entries(prefetchedPositions)) {
      cache.current[storyId] = positions.length > 0
        ? mapPositionsToDots(positions)
        : generateFallbackDots(stories.find(s => s.id === storyId)!);
    }
  }

  // Get dots for selected story (instant)
  const dots = selected
    ? (cache.current[selected] || generateFallbackDots(stories.find(s => s.id === selected)!))
    : [];

  // Group dots by source so multi-article sources draw connecting lines.
  // Independent of hover/click state — memo keyed on dots only.
  const bySource = useMemo(() => {
    const out: Record<string, DotData[]> = {};
    for (const d of dots) {
      if (!d.source_slug) continue;
      if (!out[d.source_slug]) out[d.source_slug] = [];
      out[d.source_slug].push(d);
    }
    return Object.values(out).filter(g => g.length >= 2);
  }, [dots]);

  // O(n²) collision-nudge for overlapping logos. Independent of hover/click —
  // recomputing on every state change burns ~5×n² ops per hover.
  const nudgedDots = useMemo(() => {
    const SIZE_PCT = 6;
    const out = dots.map(d => ({ ...d }));
    for (let pass = 0; pass < 5; pass++) {
      let moved = false;
      for (let i = 0; i < out.length; i++) {
        for (let j = i + 1; j < out.length; j++) {
          const dx = out[i].x - out[j].x;
          const dy = out[i].y - out[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < SIZE_PCT) {
            const push = (SIZE_PCT - dist) / 2 + 1;
            out[i].y = Math.max(5, out[i].y - push);
            out[j].y = Math.min(95, out[j].y + push);
            if (Math.abs(dx) < 2) {
              out[i].x = Math.max(5, out[i].x - 1.5);
              out[j].x = Math.min(95, out[j].x + 1.5);
            }
            moved = true;
          }
        }
      }
      if (!moved) break;
    }
    return out;
  }, [dots]);

  const loading = false;

  const dotColorClasses: Record<DotData["color"], string> = {
    conservative: "bg-[#1e3a5f] dark:bg-blue-400",
    opposition: "bg-[#ea580c] dark:bg-orange-400",
    independent: "bg-slate-400 dark:bg-slate-500",
  };

  return (
    <div ref={containerRef} dir="rtl" className="grid grid-cols-12 gap-0" style={{ minHeight: 350 }}>
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
              {toFa(s.article_count)} مقاله
              {s.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300"> · {s.state_pct}٪</span>}
              {s.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400"> · {s.diaspora_pct}٪</span>}
            </p>
          </button>
        ))}
      </div>

      {/* Left: Scatter plot of articles */}
      <div className="col-span-8 pr-4 relative" style={{ height: 380 }}>
        {/* X-axis: center line */}
        <div className="absolute left-0 right-0 h-px bg-slate-200 dark:bg-slate-700/40" style={{ top: "50%" }} />
        {/* Y-axis: center line */}
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-slate-200 dark:bg-slate-700/40" />

        {/* X-axis labels */}
        <div className="absolute right-4 text-[10px] font-medium text-[#1e3a5f] dark:text-blue-300" style={{ top: "50%", transform: "translateY(4px)" }}>درون‌مرزی</div>
        <div className="absolute left-4 text-[10px] font-medium text-[#ea580c] dark:text-orange-400" style={{ top: "50%", transform: "translateY(4px)" }}>برون‌مرزی</div>

        {/* Y-axis labels */}
        <div className="absolute text-[10px] font-medium text-slate-400 dark:text-slate-500" style={{ left: "50%", top: 4, transform: "translateX(-50%)" }}>بی‌طرف</div>
        <div className="absolute text-[10px] font-medium text-slate-400 dark:text-slate-500" style={{ left: "50%", bottom: 4, transform: "translateX(-50%)" }}>یک‌جانبه</div>

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

        {/* Connecting lines between same-source articles */}
        {!loading && bySource.map((group, gi) => (
          <svg key={`line-${gi}`} className="absolute inset-0 w-full h-full pointer-events-none z-0" style={{ overflow: "visible" }}>
            {group.slice(0, -1).map((d, i) => {
              const next = group[i + 1];
              const colorMap = { conservative: "#1e3a5f", opposition: "#ea580c", independent: "#94a3b8" };
              return (
                <line
                  key={`${d.article_id}-${next.article_id}`}
                  x1={`${d.x}%`} y1={`${d.y}%`}
                  x2={`${next.x}%`} y2={`${next.y}%`}
                  stroke={colorMap[d.color] || "#94a3b8"}
                  strokeWidth="1.5"
                  opacity="0.45"
                  strokeDasharray="4,3"
                />
              );
            })}
          </svg>
        ))}

        {/* Article logos — nudge overlapping positions */}
        {!loading && (() => {
          const borderColor: Record<string, string> = { conservative: "border-[#1e3a5f]", opposition: "border-[#ea580c]", independent: "border-slate-400" };
          return nudgedDots.map((d) => (
            <div
              key={d.article_id}
              className="absolute transition-all duration-500 z-10"
              style={{
                left: `${d.x}%`,
                top: `${d.y}%`,
                transform: "translate(-50%, -50%)",
              }}
              onMouseEnter={() => { if (d.title_fa) setHoveredDot(d.article_id); }}
              onMouseLeave={() => { if (clickedDot !== d.article_id) setHoveredDot(null); }}
              onClick={(e) => { e.stopPropagation(); setClickedDot(clickedDot === d.article_id ? null : d.article_id); }}
            >
              {d.source_logo_url ? (
                <div className={`w-6 h-6 rounded-full overflow-hidden bg-white dark:bg-slate-800 border ${borderColor[d.color]} shadow-sm hover:scale-150 transition-transform cursor-pointer`}>
                  <img src={d.source_logo_url} alt={d.source_name_fa || ""} className="w-full h-full object-cover" loading="lazy" />
                </div>
              ) : (
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[7px] font-bold hover:scale-150 transition-transform cursor-pointer ${
                  d.color === "conservative" ? "bg-[#1e3a5f]/20 text-[#1e3a5f] dark:bg-blue-900/40 dark:text-blue-300 border border-[#1e3a5f]/40" :
                  d.color === "opposition" ? "bg-[#ea580c]/20 text-[#ea580c] dark:bg-orange-900/40 dark:text-orange-300 border border-[#ea580c]/40" :
                  "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-300 border border-slate-300"
                }`}>
                  {(d.source_name_fa || d.source_slug || "").slice(0, 2)}
                </div>
              )}
              {(hoveredDot === d.article_id || clickedDot === d.article_id) && (
                <div
                  className={`absolute z-20 bottom-full left-1/2 -translate-x-1/2 mb-2 ${clickedDot === d.article_id ? "" : "pointer-events-none"}`}
                  style={{ width: "max-content", maxWidth: 260 }}
                >
                  <div className="bg-slate-900 dark:bg-slate-700 text-white text-[11px] leading-snug px-2.5 py-1.5 rounded shadow-lg">
                    {d.source_name_fa && <p className="font-bold text-[10px] mb-0.5">{d.source_name_fa}</p>}
                    {d.title_fa && <p className="line-clamp-2 mb-1">{d.title_fa}</p>}
                    {d.article_url && (
                      <a href={d.article_url} target="_blank" rel="noopener noreferrer"
                        className="text-[10px] text-blue-300 hover:text-blue-200 underline">
                        مشاهده مقاله ←
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          ));
        })()}

        {/* Article count — top left, not overlapping Y-axis label */}
        {active && !loading && (
          <div className="absolute top-3 left-4 z-20">
            <p className="text-[10px] text-slate-400 dark:text-slate-500">
              {toFa(active.article_count)} مقاله
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
