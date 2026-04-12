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
  // Group sources by their x-column (1-7)
  const columns: Record<number, { source: Source; neutrality: number }[]> = {};
  for (const s of sources) {
    const x = getSpectrumScore(s);
    const n = sourceNeutrality?.[s.slug] ?? 0;
    if (!columns[x]) columns[x] = [];
    columns[x].push({ source: s, neutrality: n });
  }

  // Sort each column by neutrality (highest = top)
  for (const col of Object.values(columns)) {
    col.sort((a, b) => b.neutrality - a.neutrality);
  }

  const chartHeight = 240;

  // Column indices: RTL → 1 (conservative) on right, 7 (opposition) on left
  // But grid renders LTR, so we reverse: column order = [7,6,5,4,3,2,1]
  const colOrder = [7, 6, 5, 4, 3, 2, 1];

  return (
    <div dir="rtl">
      {/* Top labels */}
      <div className="flex items-center justify-between mb-2 text-[11px] font-medium text-slate-500 dark:text-slate-400">
        <span>محافظه‌کار</span>
        <span>اپوزیسیون</span>
      </div>

      {/* Chart */}
      <div className="relative" style={{ height: chartHeight }}>

        {/* Y-axis: vertical line in the CENTER */}
        <div className="absolute top-0 bottom-0 w-px bg-slate-400 dark:bg-slate-500" style={{ left: "50%" }} />

        {/* Y-axis labels (next to center line) */}
        <div className="absolute text-[9px] text-slate-400 dark:text-slate-500" style={{ left: "50%", top: 4, transform: "translateX(6px)" }}>بی‌طرف</div>
        <div className="absolute text-[9px] text-slate-400 dark:text-slate-500" style={{ left: "50%", bottom: 4, transform: "translateX(6px)" }}>یک‌طرفه</div>

        {/* X-axis: horizontal gradient line in the CENTER */}
        <div className="absolute left-0 right-0 h-[3px]" style={{
          top: "50%",
          transform: "translateY(-50%)",
          background: "linear-gradient(to left, #c2410c, #ea580c, #f97316, #94a3b8, #60a5fa, #2563eb, #1e3a5f)",
        }} />

        {/* 6 short vertical separator lines between columns */}
        {[1, 2, 3, 4, 5, 6].map((i) => {
          const pct = (i / 7) * 100;
          return (
            <div
              key={i}
              className="absolute bg-slate-200 dark:bg-slate-700/40"
              style={{ left: `${pct}%`, top: "20%", bottom: "20%", width: "1px" }}
            />
          );
        })}

        {/* 7 columns with logos */}
        <div className="absolute inset-0 grid grid-cols-7">
          {colOrder.map((score) => {
            const items = columns[score] || [];
            return (
              <div key={score} className="flex flex-col items-center justify-center gap-2 relative">
                {items.map(({ source: s, neutrality }) => {
                  // Y position within the column based on neutrality
                  // +1 = top (neutral), -1 = bottom (one-sided)
                  const yPct = ((1 - neutrality) / 2) * 100;
                  const clampedY = Math.max(10, Math.min(85, yPct));

                  return (
                    <div
                      key={s.slug}
                      className="absolute group z-10"
                      style={{
                        top: `${clampedY}%`,
                        transform: "translateY(-50%)",
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
                      {/* Tooltip */}
                      <div className="hidden md:block absolute -bottom-7 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 dark:bg-white text-white dark:text-slate-900 text-[9px] px-2 py-0.5 whitespace-nowrap pointer-events-none z-20 shadow-lg">
                        {s.name_fa || s.name_en}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
