"use client";

import type { Source } from "@/lib/types";

// 7-point Likert: 1 = strongly conservative/pro-regime, 7 = strongly opposition
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

export default function PoliticalSpectrum({ sources }: { sources: Source[] }) {
  const groups: Record<number, Source[]> = {};
  for (const s of sources) {
    const score = getSpectrumScore(s);
    if (!groups[score]) groups[score] = [];
    groups[score].push(s);
  }

  return (
    <div dir="rtl">
      {/* Labels */}
      <div className="flex items-center justify-between mb-2 text-[10px] text-slate-500">
        <span>محافظه‌کار</span>
        <span>اپوزیسیون</span>
      </div>

      {/* Gradient bar: dark blue (conservative/right) → orange (opposition/left) */}
      <div className="h-1.5 w-full" style={{
        background: "linear-gradient(to left, #c2410c, #ea580c, #f97316, #94a3b8, #60a5fa, #2563eb, #1e3a5f)"
      }} />

      {/* 7 columns with logos stacked vertically */}
      <div className="grid grid-cols-7 gap-0 mt-3" style={{ minHeight: "50px" }}>
        {[1, 2, 3, 4, 5, 6, 7].map((score) => {
          const items = groups[score] || [];
          return (
            <div key={score} className="flex flex-col items-center gap-2 px-0.5">
              {items.map((s) => (
                <div key={s.slug} className="group relative flex flex-col items-center" title={s.name_fa || s.name_en}>
                  {s.logo_url ? (
                    <div className="w-8 h-8 rounded-full overflow-hidden bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      <img
                        src={s.logo_url}
                        alt={s.name_fa || s.name_en}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-[10px] font-bold text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600">
                      {(s.name_fa || s.name_en || "?").charAt(0)}
                    </div>
                  )}
                  {/* Name: hover only on desktop, hidden on mobile */}
                  <span className="hidden md:block absolute -bottom-5 opacity-0 group-hover:opacity-100 transition-opacity text-[8px] text-slate-500 dark:text-slate-400 text-center whitespace-nowrap pointer-events-none">
                    {s.name_fa || s.name_en}
                  </span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
