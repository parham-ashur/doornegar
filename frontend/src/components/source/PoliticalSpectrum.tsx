"use client";

import type { Source } from "@/lib/types";

// X-axis: 1-7 conservative → opposition
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

// 7 band colors from conservative (dark blue) to opposition (orange)
const BAND_COLORS = [
  "rgba(30, 58, 95, 0.25)",   // 1 - dark blue
  "rgba(37, 99, 235, 0.20)",  // 2 - blue
  "rgba(96, 165, 250, 0.15)", // 3 - light blue
  "rgba(148, 163, 184, 0.10)",// 4 - gray (center)
  "rgba(251, 191, 36, 0.15)", // 5 - light orange
  "rgba(234, 88, 12, 0.20)",  // 6 - orange
  "rgba(194, 65, 12, 0.25)",  // 7 - dark orange
];

interface Props {
  sources: Source[];
  sourceNeutrality: Record<string, number> | null;
}

export default function PoliticalSpectrum({ sources, sourceNeutrality }: Props) {
  // Compute positions for each source
  const items = sources.map((s) => {
    const xScore = getSpectrumScore(s); // 1-7
    const neutrality = sourceNeutrality?.[s.slug] ?? 0; // -1 to +1
    return { source: s, xScore, neutrality };
  });

  // Chart dimensions
  const chartHeight = 200;
  const chartWidth = "100%";

  return (
    <div dir="rtl">
      {/* Labels */}
      <div className="flex items-center justify-between mb-1 text-[10px] text-slate-500">
        <span>محافظه‌کار</span>
        <span>اپوزیسیون</span>
      </div>

      {/* 2D chart */}
      <div className="relative w-full border border-slate-200 dark:border-slate-800 overflow-hidden" style={{ height: chartHeight }}>
        {/* 7 vertical bands */}
        <div className="absolute inset-0 flex">
          {BAND_COLORS.map((bg, i) => (
            <div
              key={i}
              className="flex-1 border-l first:border-l-0 border-slate-200/30 dark:border-slate-700/30"
              style={{ background: bg }}
            />
          ))}
        </div>

        {/* Y-axis label */}
        <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between py-1 pl-1 text-[8px] text-slate-400 pointer-events-none" dir="ltr">
          <span>بی‌طرف</span>
          <span>یک‌طرفه</span>
        </div>

        {/* Source logos positioned in 2D */}
        {items.map(({ source: s, xScore, neutrality }) => {
          // X: score 1-7 mapped to 0-100%
          const xPct = ((xScore - 0.5) / 7) * 100;
          // Y: neutrality -1 (bottom, one-sided) to +1 (top, neutral)
          const yPct = ((1 - neutrality) / 2) * 100; // invert: +1 = top

          return (
            <div
              key={s.slug}
              className="absolute group"
              style={{
                right: `${xPct}%`,
                top: `${Math.max(5, Math.min(85, yPct))}%`,
                transform: "translate(50%, -50%)",
              }}
            >
              {s.logo_url ? (
                <div className="w-7 h-7 rounded-full overflow-hidden bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 shadow-sm">
                  <img
                    src={s.logo_url}
                    alt={s.name_fa || s.name_en}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
              ) : (
                <div className="w-7 h-7 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-[9px] font-bold text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 shadow-sm">
                  {(s.name_fa || s.name_en || "?").charAt(0)}
                </div>
              )}
              {/* Tooltip on hover — desktop only */}
              <div className="hidden md:block absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-[9px] px-2 py-0.5 whitespace-nowrap pointer-events-none z-10">
                {s.name_fa || s.name_en}
                {neutrality !== 0 && <span className="mr-1 text-[8px] opacity-70">({neutrality > 0 ? "+" : ""}{neutrality.toFixed(1)})</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Bottom gradient bar */}
      <div className="h-1 w-full mt-0" style={{
        background: "linear-gradient(to left, #c2410c, #ea580c, #f97316, #94a3b8, #60a5fa, #2563eb, #1e3a5f)"
      }} />
    </div>
  );
}
