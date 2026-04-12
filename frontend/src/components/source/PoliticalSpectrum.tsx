"use client";

import type { Source } from "@/lib/types";

function getSpectrumScore(source: Source): number {
  const align = source.state_alignment;
  const faction = source.factional_alignment;
  const irgc = source.irgc_affiliated;

  if (align === "state") {
    if (irgc) return 1;
    if (faction === "principlist" || faction === "hardline") return 1;
    return 2;
  }
  if (align === "semi_state") {
    if (faction === "reformist") return 3;
    return 2;
  }
  if (align === "independent") return 4;
  if (align === "diaspora") {
    const slug = source.slug || "";
    if (slug.includes("bbc") || slug.includes("dw") || slug.includes("euronews")) return 5;
    if (slug.includes("rfi") || slug.includes("zamaneh")) return 5;
    if (slug.includes("farda") || slug.includes("voa")) return 6;
    if (slug.includes("iran-international") || slug.includes("iranintl")) return 6;
    if (slug.includes("kayhan-london")) return 6;
    return 5;
  }
  return 4;
}

interface Props {
  sources: Source[];
  sourceNeutrality: Record<string, number> | null;
}

export default function PoliticalSpectrum({ sources, sourceNeutrality }: Props) {
  const items = sources.map((s) => {
    const xScore = getSpectrumScore(s);
    const neutrality = sourceNeutrality?.[s.slug] ?? 0;
    return { source: s, xScore, neutrality };
  });

  const chartHeight = 220;

  return (
    <div dir="rtl">
      {/* Top labels */}
      <div className="flex items-center justify-between mb-3 text-[11px] font-medium text-slate-500 dark:text-slate-400">
        <span>محافظه‌کار</span>
        <span>اپوزیسیون</span>
      </div>

      {/* Chart area */}
      <div className="relative w-full" style={{ height: chartHeight }}>

        {/* Y-axis line (dark gray, left side in LTR = right side in RTL) */}
        <div className="absolute right-0 top-0 bottom-0 w-px bg-slate-400 dark:bg-slate-500" />

        {/* Y-axis labels */}
        <div className="absolute right-2 top-1 text-[9px] text-slate-400 dark:text-slate-500">بی‌طرف</div>
        <div className="absolute right-2 bottom-1 text-[9px] text-slate-400 dark:text-slate-500">یک‌طرفه</div>

        {/* 6 vertical separator lines (between 7 zones), shorter than full height */}
        {[1, 2, 3, 4, 5, 6].map((i) => {
          const leftPct = (i / 7) * 100;
          return (
            <div
              key={i}
              className="absolute bg-slate-200 dark:bg-slate-700/50"
              style={{
                left: `${leftPct}%`,
                top: "15%",
                bottom: "15%",
                width: "1px",
              }}
            />
          );
        })}

        {/* Source logos positioned in 2D */}
        {items.map(({ source: s, xScore, neutrality }) => {
          // X: score 1-7 mapped to percentage (RTL: 1=right, 7=left)
          const xPct = ((xScore - 0.5) / 7) * 100;
          // Y: neutrality -1 (bottom) to +1 (top)
          const yPct = ((1 - neutrality) / 2) * 100;

          return (
            <div
              key={s.slug}
              className="absolute group z-10"
              style={{
                right: `${xPct}%`,
                top: `${Math.max(8, Math.min(82, yPct))}%`,
                transform: "translate(50%, -50%)",
              }}
            >
              {s.logo_url ? (
                <div className="w-8 h-8 rounded-full overflow-hidden bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm transition-transform group-hover:scale-125">
                  <img
                    src={s.logo_url}
                    alt={s.name_fa || s.name_en}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
              ) : (
                <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-[10px] font-bold text-slate-500 dark:text-slate-300 border border-slate-200 dark:border-slate-600 shadow-sm transition-transform group-hover:scale-125">
                  {(s.name_fa || s.name_en || "?").charAt(0)}
                </div>
              )}
              {/* Tooltip — desktop hover only */}
              <div className="hidden md:block absolute -bottom-7 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 dark:bg-white text-white dark:text-slate-900 text-[9px] px-2 py-0.5 whitespace-nowrap pointer-events-none z-20 shadow-lg">
                {s.name_fa || s.name_en}
              </div>
            </div>
          );
        })}
      </div>

      {/* X-axis gradient bar */}
      <div className="h-1.5 w-full" style={{
        background: "linear-gradient(to left, #c2410c, #ea580c, #f97316, #94a3b8, #60a5fa, #2563eb, #1e3a5f)"
      }} />
    </div>
  );
}
