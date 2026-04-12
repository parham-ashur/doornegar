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
  const columns: Record<number, { source: Source; neutrality: number }[]> = {};
  for (const s of sources) {
    const score = getSpectrumScore(s);
    const n = sourceNeutrality?.[s.slug] ?? 0;
    if (!columns[score]) columns[score] = [];
    columns[score].push({ source: s, neutrality: n });
  }

  for (const col of Object.values(columns)) {
    col.sort((a, b) => b.neutrality - a.neutrality);
  }

  const colOrder = [1, 2, 3, 4, 5];

  return (
    <div dir="rtl" className="pl-16">
      {/* Chart: columns + Y-axis on left */}
      <div className="flex items-stretch gap-0">
        {/* 5 columns area */}
        <div className="flex-1 relative">
          {/* X-axis: horizontal gradient line in center — starts at Y-axis */}
          <div className="absolute right-0 z-0 flex items-center" style={{ left: "5%", top: "50%", transform: "translateY(-50%)" }}>
            <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 shrink-0 pl-2">محافظه‌کار</span>
            <div className="flex-1 h-[3px]" style={{
              background: "linear-gradient(to left, #1e3a5f, #2563eb, #94a3b8, #f97316, #c2410c)",
            }} />
          </div>

          {/* اپوزیسیون label — to the left of Y-axis, not overlapping */}
          <div className="absolute z-0 text-[11px] font-medium text-slate-500 dark:text-slate-400" style={{ left: 0, top: "50%", transform: "translateY(-50%) translateX(-100%)", paddingLeft: 4 }}>اپوزیسیون</div>

          {/* Y-axis vertical line */}
          <div className="absolute top-0 bottom-0 w-px bg-slate-400 dark:bg-slate-500 z-0" style={{ left: "5%" }} />

          {/* بی‌طرف / یک‌طرفه — to the right of Y-axis */}
          <div className="absolute z-0 text-[11px] font-medium text-slate-400 dark:text-slate-500" style={{ left: "6%", top: 2 }}>بی‌طرف</div>
          <div className="absolute z-0 text-[11px] font-medium text-slate-400 dark:text-slate-500" style={{ left: "6%", bottom: 2 }}>یک‌طرفه</div>

          {/* 4 vertical separator lines */}
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="absolute bg-slate-200 dark:bg-slate-700/30 z-0"
              style={{ left: `${(i / 5) * 100}%`, top: "15%", bottom: "15%", width: "1px" }}
            />
          ))}

          {/* Columns with stacked logos */}
          <div className="relative z-10 flex justify-center" style={{ minHeight: 320 }}>
            <div className="grid grid-cols-5 w-[85%]">
              {colOrder.map((score) => {
                const items = columns[score] || [];
                return (
                  <div key={score} className="flex flex-col items-center justify-center gap-2 py-3">
                    {items.map(({ source: s }) => (
                      <div key={s.slug} className="group relative">
                        {s.logo_url ? (
                          <div className="w-10 h-10 rounded-full overflow-hidden bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm transition-transform group-hover:scale-125">
                            <img src={s.logo_url} alt={s.name_fa || ""} className="w-full h-full object-cover" loading="lazy" />
                          </div>
                        ) : (
                          <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-500 dark:text-slate-300 border border-slate-200 dark:border-slate-600 shadow-sm transition-transform group-hover:scale-125">
                            {(s.name_fa || s.name_en || "?").charAt(0)}
                          </div>
                        )}
                        <div className="hidden md:block absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 dark:bg-white text-white dark:text-slate-900 text-[11px] px-2.5 py-1 whitespace-nowrap pointer-events-none z-20 shadow-lg">
                          {s.name_fa || s.name_en}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

      </div>

      {/* Caption */}
      <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-3 leading-5">
        محور افقی: جایگاه سیاسی رسانه از محافظه‌کار تا اپوزیسیون. محور عمودی: میزان بی‌طرفی پوشش خبری در این موضوع.
      </p>
    </div>
  );
}
