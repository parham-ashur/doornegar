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
      {/* Y-axis top label */}
      <div className="text-center text-[9px] text-slate-400 dark:text-slate-500 mb-1">بی‌طرف</div>

      {/* Chart: labels + columns */}
      <div className="flex items-stretch gap-0">
        {/* Y-axis label left */}
        <div className="flex items-end pb-1 shrink-0">
          <span className="text-[9px] text-slate-400 dark:text-slate-500" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>محافظه‌کار</span>
        </div>

        {/* 5 columns */}
        <div className="flex-1 relative">
          {/* X-axis: horizontal gradient line in center — reversed: dark blue (right/conservative) → orange (left/opposition) */}
          <div className="absolute left-0 right-0 h-[3px] z-0" style={{
            top: "50%",
            transform: "translateY(-50%)",
            background: "linear-gradient(to left, #1e3a5f, #2563eb, #94a3b8, #f97316, #c2410c)",
          }} />

          {/* Vertical center line (neutrality axis) */}
          <div className="absolute top-0 bottom-0 w-px bg-slate-300 dark:bg-slate-600 z-0" style={{ left: "50%" }} />

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

        {/* Y-axis label right */}
        <div className="flex items-start pt-1 shrink-0">
          <span className="text-[9px] text-slate-400 dark:text-slate-500" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>اپوزیسیون</span>
        </div>
      </div>

      {/* Y-axis bottom label */}
      <div className="text-center text-[9px] text-slate-400 dark:text-slate-500 mt-1">یک‌طرفه</div>
    </div>
  );
}
