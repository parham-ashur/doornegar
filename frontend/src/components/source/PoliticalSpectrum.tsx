"use client";

import type { Source } from "@/lib/types";

function getSpectrumScore(source: Source): number {
  const align = source.state_alignment;
  const irgc = source.irgc_affiliated;

  if (align === "state") return irgc ? 1 : 1;
  if (align === "semi_state") return 2;
  if (align === "independent") return 3;
  if (align === "diaspora") {
    const slug = source.slug || "";
    if (slug.includes("bbc") || slug.includes("dw") || slug.includes("euronews") || slug.includes("rfi") || slug.includes("zamaneh")) return 4;
    return 5;
  }
  return 3;
}

interface Props {
  sources: Source[];
  sourceNeutrality: Record<string, number> | null;
}

export default function PoliticalSpectrum({ sources, sourceNeutrality }: Props) {
  const items = sources.map((s) => ({
    source: s,
    yScore: getSpectrumScore(s),
    neutrality: sourceNeutrality?.[s.slug] ?? 0,
  }));

  const chartHeight = 260;

  return (
    <div dir="rtl">
      {/* X-axis top label (neutral) */}
      <div className="text-center text-[9px] text-slate-400 dark:text-slate-500 mb-1">بی‌طرف</div>

      {/* Chart area */}
      <div className="relative" style={{ height: chartHeight }}>

        {/* X-axis: vertical line in center */}
        <div className="absolute top-0 bottom-0 w-px bg-slate-400 dark:bg-slate-500" style={{ left: "50%" }} />

        {/* Y-axis: horizontal gradient bar in center with labels on it */}
        <div className="absolute left-0 right-0" style={{ top: "50%", transform: "translateY(-50%)" }}>
          <div className="flex items-center gap-0">
            <span className="text-[9px] text-slate-500 dark:text-slate-400 shrink-0 pl-1">محافظه‌کار</span>
            <div className="flex-1 h-[3px]" style={{
              background: "linear-gradient(to left, #c2410c, #ea580c, #f97316, #94a3b8, #60a5fa, #2563eb, #1e3a5f)",
            }} />
            <span className="text-[9px] text-slate-500 dark:text-slate-400 shrink-0 pr-1">اپوزیسیون</span>
          </div>
        </div>

        {/* 4 horizontal separator lines between 5 rows */}
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="absolute bg-slate-200 dark:bg-slate-700/40"
            style={{ top: `${(i / 5) * 100}%`, left: "20%", right: "20%", height: "1px" }}
          />
        ))}

        {/* Logos positioned in 2D */}
        {items.map(({ source: s, yScore, neutrality }) => {
          const yPct = ((yScore - 0.5) / 5) * 100;
          const xPct = ((neutrality + 1) / 2) * 100;

          return (
            <div
              key={s.slug}
              className="absolute group z-10"
              style={{
                top: `${Math.max(5, Math.min(92, yPct))}%`,
                left: `${Math.max(8, Math.min(92, xPct))}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              {s.logo_url ? (
                <div className="w-9 h-9 rounded-full overflow-hidden bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm transition-transform group-hover:scale-125">
                  <img src={s.logo_url} alt={s.name_fa || ""} className="w-full h-full object-cover" loading="lazy" />
                </div>
              ) : (
                <div className="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-[10px] font-bold text-slate-500 dark:text-slate-300 border border-slate-200 dark:border-slate-600 shadow-sm transition-transform group-hover:scale-125">
                  {(s.name_fa || s.name_en || "?").charAt(0)}
                </div>
              )}
              <div className="hidden md:block absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 dark:bg-white text-white dark:text-slate-900 text-[9px] px-2 py-0.5 whitespace-nowrap pointer-events-none z-20 shadow-lg">
                {s.name_fa || s.name_en}
              </div>
            </div>
          );
        })}
      </div>

      {/* X-axis bottom label (one-sided) */}
      <div className="text-center text-[9px] text-slate-400 dark:text-slate-500 mt-1">یک‌طرفه</div>
    </div>
  );
}
