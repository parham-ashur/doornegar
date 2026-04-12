"use client";

import type { Source } from "@/lib/types";

// Y-axis: 1-5, conservative (top) → opposition (bottom)
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

  // Group by row for stacking
  const rows: Record<number, typeof items> = {};
  for (const item of items) {
    if (!rows[item.yScore]) rows[item.yScore] = [];
    rows[item.yScore].push(item);
  }

  const chartHeight = 200;

  return (
    <div dir="rtl">
      <div className="flex gap-0">
        {/* Y-axis labels (right side) */}
        <div className="flex flex-col justify-between py-1 pl-2 text-[9px] text-slate-400 dark:text-slate-500 shrink-0" style={{ height: chartHeight }}>
          <span>محافظه‌کار</span>
          <span>اپوزیسیون</span>
        </div>

        {/* Chart */}
        <div className="relative flex-1" style={{ height: chartHeight }}>

          {/* Y-axis: vertical gradient in center */}
          <div className="absolute h-[3px] left-0 right-0" style={{
            top: "50%",
            transform: "translateY(-50%)",
            background: "linear-gradient(to bottom, #1e3a5f, #2563eb, #94a3b8, #f97316, #c2410c)",
          }} />

          {/* X-axis: vertical line in center */}
          <div className="absolute top-0 bottom-0 w-px bg-slate-400 dark:bg-slate-500" style={{ left: "50%" }} />

          {/* X-axis labels */}
          <div className="absolute text-[9px] text-slate-400 dark:text-slate-500" style={{ left: 4, top: -14 }}>یک‌طرفه</div>
          <div className="absolute text-[9px] text-slate-400 dark:text-slate-500" style={{ right: 4, top: -14 }}>بی‌طرف</div>

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
            // Y: score 1 (top) → 5 (bottom)
            const yPct = ((yScore - 0.5) / 5) * 100;
            // X: neutrality -1 (left, one-sided) → +1 (right, neutral)
            const xPct = ((neutrality + 1) / 2) * 100;
            const clampedX = Math.max(8, Math.min(92, xPct));
            const clampedY = Math.max(5, Math.min(90, yPct));

            return (
              <div
                key={s.slug}
                className="absolute group z-10"
                style={{
                  top: `${clampedY}%`,
                  left: `${clampedX}%`,
                  transform: "translate(-50%, -50%)",
                }}
              >
                {s.logo_url ? (
                  <div className="w-9 h-9 rounded-full overflow-hidden bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm transition-transform group-hover:scale-125">
                    <img src={s.logo_url} alt={s.name_fa || ""} className="w-full h-full object-cover" loading="lazy" />
                  </div>
                ) : (
                  <div className="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-500 dark:text-slate-300 border border-slate-200 dark:border-slate-600 shadow-sm transition-transform group-hover:scale-125">
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
      </div>
    </div>
  );
}
