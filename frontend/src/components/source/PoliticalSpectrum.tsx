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
  // Group by column (1-5)
  const columns: Record<number, { source: Source; neutrality: number }[]> = {};
  for (const s of sources) {
    const score = getSpectrumScore(s);
    const n = sourceNeutrality?.[s.slug] ?? 0;
    if (!columns[score]) columns[score] = [];
    columns[score].push({ source: s, neutrality: n });
  }

  // Sort each column by neutrality (highest = top = most neutral)
  for (const col of Object.values(columns)) {
    col.sort((a, b) => b.neutrality - a.neutrality);
  }

  // RTL: column order 1 (conservative) on right → 5 (opposition) on left
  const colOrder = [1, 2, 3, 4, 5];

  return (
    <div dir="rtl">
      {/* Chart: columns + Y-axis on left */}
      <div className="flex items-stretch gap-0">
        {/* 5 columns */}
        <div className="flex-1 relative">
          {/* X-axis: horizontal gradient line in center with labels */}
          <div className="absolute left-0 right-0 z-0 flex items-center" style={{ top: "50%", transform: "translateY(-50%)" }}>
            <span className="text-[9px] text-slate-500 dark:text-slate-400 shrink-0 pl-1">محافظه‌کار</span>
            <div className="flex-1 h-[3px]" style={{
              background: "linear-gradient(to left, #1e3a5f, #2563eb, #94a3b8, #f97316, #c2410c)",
            }} />
            <span className="text-[9px] text-slate-500 dark:text-slate-400 shrink-0 pr-1">اپوزیسیون</span>
          </div>

          {/* Y-axis vertical line (left side in visual / right in RTL) */}
          <div className="absolute top-0 bottom-0 w-px bg-slate-400 dark:bg-slate-500 z-0" style={{ left: 0 }} />

          {/* 4 vertical separator lines */}
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="absolute bg-slate-200 dark:bg-slate-700/30 z-0"
              style={{ left: `${(i / 5) * 100}%`, top: "15%", bottom: "15%", width: "1px" }}
            />
          ))}

          {/* Columns with stacked logos */}
          <div className="grid grid-cols-5 relative z-10" style={{ minHeight: 220 }}>
            {colOrder.map((score) => {
              const items = columns[score] || [];
              return (
                <div key={score} className="flex flex-col items-center justify-center gap-2 py-3">
                  {items.map(({ source: s }) => (
                    <div key={s.slug} className="group relative">
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
                  ))}
                </div>
              );
            })}
          </div>
        </div>

        {/* Y-axis on left side */}
        <div className="flex flex-col justify-between py-1 pr-2 shrink-0 text-[9px] text-slate-400 dark:text-slate-500">
          <span>بی‌طرف</span>
          <span>یک‌طرفه</span>
        </div>
      </div>
    </div>
  );
}
