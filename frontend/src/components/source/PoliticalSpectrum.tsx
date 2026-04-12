"use client";

import type { Source } from "@/lib/types";

// 5-point Likert: 1 = strongly conservative, 5 = strongly opposition
function getSpectrumScore(source: Source): number {
  const align = source.state_alignment;
  const faction = source.factional_alignment;
  const irgc = source.irgc_affiliated;

  if (align === "state") {
    if (irgc) return 1;
    return 1;
  }
  if (align === "semi_state") return 2;
  if (align === "independent") return 3;
  if (align === "diaspora") {
    const slug = source.slug || "";
    if (slug.includes("bbc") || slug.includes("dw") || slug.includes("euronews") || slug.includes("rfi") || slug.includes("zamaneh")) return 4;
    return 5; // iran-international, farda, voa, kayhan-london
  }
  return 3;
}

// Column background shades (subtle, transparent)
const COL_BG = [
  "rgba(30, 58, 95, 0.08)",   // 1 - conservative
  "rgba(37, 99, 235, 0.06)",  // 2
  "rgba(148, 163, 184, 0.04)",// 3 - center
  "rgba(249, 115, 22, 0.06)", // 4
  "rgba(194, 65, 12, 0.08)",  // 5 - opposition
];

interface Props {
  sources: Source[];
  sourceNeutrality: Record<string, number> | null;
}

export default function PoliticalSpectrum({ sources, sourceNeutrality }: Props) {
  // Group by column
  const columns: Record<number, Source[]> = {};
  for (const s of sources) {
    const score = getSpectrumScore(s);
    if (!columns[score]) columns[score] = [];
    columns[score].push(s);
  }

  // RTL: 1 on right (conservative), 5 on left (opposition)
  const colOrder = [1, 2, 3, 4, 5];

  return (
    <div dir="rtl">
      {/* Labels */}
      <div className="flex items-center justify-between mb-2 text-[10px] text-slate-400 dark:text-slate-500">
        <span>محافظه‌کار</span>
        <span>اپوزیسیون</span>
      </div>

      {/* 5 columns with rounded pill backgrounds */}
      <div className="grid grid-cols-5 gap-1.5">
        {colOrder.map((score, ci) => {
          const items = columns[score] || [];
          return (
            <div
              key={score}
              className="flex flex-col items-center gap-2 py-3 rounded-full min-h-[60px]"
              style={{ background: COL_BG[ci] }}
            >
              {items.map((s) => (
                <div key={s.slug} className="group relative">
                  {s.logo_url ? (
                    <div className="w-9 h-9 rounded-full overflow-hidden bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm transition-transform group-hover:scale-110">
                      <img src={s.logo_url} alt={s.name_fa || ""} className="w-full h-full object-cover" loading="lazy" />
                    </div>
                  ) : (
                    <div className="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-500 dark:text-slate-300 border border-slate-200 dark:border-slate-600 shadow-sm transition-transform group-hover:scale-110">
                      {(s.name_fa || s.name_en || "?").charAt(0)}
                    </div>
                  )}
                  {/* Tooltip — desktop hover */}
                  <div className="hidden md:block absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 dark:bg-white text-white dark:text-slate-900 text-[9px] px-2 py-0.5 whitespace-nowrap pointer-events-none z-20 shadow-lg">
                    {s.name_fa || s.name_en}
                  </div>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {/* Gradient bar under columns */}
      <div className="h-1 w-full mt-1 rounded-full" style={{
        background: "linear-gradient(to left, #c2410c, #f97316, #94a3b8, #2563eb, #1e3a5f)"
      }} />
    </div>
  );
}
