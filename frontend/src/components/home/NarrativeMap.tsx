"use client";

import { useState, useRef } from "react";
import type { StoryBrief } from "@/lib/types";

// Simulate article positions for a story based on its coverage split
// In production, these would come from actual article embeddings reduced to 2D
function generateArticleDots(s: StoryBrief): { x: number; y: number; side: "conservative" | "opposition" }[] {
  const dots: { x: number; y: number; side: "conservative" | "opposition" }[] = [];
  const seed = s.article_count * 7;

  // Conservative articles — cluster on the right
  const cCount = Math.round(s.article_count * (s.state_pct || 0) / 100);
  for (let i = 0; i < cCount; i++) {
    const hash = (seed + i * 13) % 1000;
    dots.push({
      x: 60 + (hash % 30),
      y: 15 + ((hash * 7) % 70),
      side: "conservative",
    });
  }

  // Opposition articles — cluster on the left
  const oCount = Math.round(s.article_count * (s.diaspora_pct || 0) / 100);
  for (let i = 0; i < oCount; i++) {
    const hash = (seed + i * 17 + 500) % 1000;
    dots.push({
      x: 10 + (hash % 30),
      y: 15 + ((hash * 7) % 70),
      side: "opposition",
    });
  }

  return dots;
}

export default function NarrativeMap({ stories }: { stories: StoryBrief[] }) {
  const [selected, setSelected] = useState<string | null>(stories[0]?.id || null);
  const listRef = useRef<HTMLDivElement>(null);

  const active = stories.find(s => s.id === selected);
  const dots = active ? generateArticleDots(active) : [];

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

        {/* Article dots */}
        {dots.map((d, i) => (
          <div
            key={i}
            className="absolute transition-all duration-500"
            style={{
              left: `${d.x}%`,
              top: `${d.y}%`,
              transform: "translate(-50%, -50%)",
            }}
          >
            <div className={`rounded-full ${
              d.side === "conservative"
                ? "bg-[#1e3a5f] dark:bg-blue-400"
                : "bg-[#ea580c] dark:bg-orange-400"
            } opacity-50`}
              style={{ width: 8, height: 8 }}
            />
          </div>
        ))}

        {/* Story info */}
        {active && (
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
