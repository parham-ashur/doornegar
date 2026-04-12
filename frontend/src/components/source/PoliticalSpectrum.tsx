"use client";

import type { Source } from "@/lib/types";

// 7-point Likert scale: 1 = strongly conservative/pro-regime, 7 = strongly opposition
// Based on state_alignment + factional_alignment + known editorial positions
function getSpectrumScore(source: Source): number {
  const align = source.state_alignment;
  const faction = source.factional_alignment;
  const irgc = source.irgc_affiliated;

  // State media
  if (align === "state") {
    if (irgc) return 1; // IRGC-affiliated (Fars, Tasnim)
    if (faction === "principlist" || faction === "hardline") return 1;
    return 2; // Other state (IRNA, PressTV)
  }
  if (align === "semi_state") {
    if (faction === "reformist") return 3; // Reformist-leaning semi-state
    return 2; // Tabnak, Khabar Online
  }
  // Independent
  if (align === "independent") {
    return 4; // Center
  }
  // Diaspora / opposition
  if (align === "diaspora") {
    // Known hardcoded positions for major outlets
    const slug = source.slug || "";
    if (slug.includes("bbc") || slug.includes("dw") || slug.includes("euronews")) return 5; // Center-opposition
    if (slug.includes("rfi") || slug.includes("zamaneh")) return 5;
    if (slug.includes("farda") || slug.includes("voa")) return 6; // Opposition-leaning
    if (slug.includes("iran-international") || slug.includes("iranintl")) return 6;
    if (slug.includes("kayhan-london")) return 6;
    return 5; // Default diaspora
  }
  return 4; // Unknown → center
}

const LABELS = [
  { score: 1, label: "محافظه‌کار", color: "bg-red-600" },
  { score: 2, label: "", color: "bg-red-400" },
  { score: 3, label: "", color: "bg-orange-400" },
  { score: 4, label: "میانه", color: "bg-slate-400" },
  { score: 5, label: "", color: "bg-blue-300" },
  { score: 6, label: "", color: "bg-blue-500" },
  { score: 7, label: "اپوزیسیون", color: "bg-blue-700" },
];

export default function PoliticalSpectrum({ sources }: { sources: Source[] }) {
  // Group sources by score
  const groups: Record<number, Source[]> = {};
  for (const s of sources) {
    const score = getSpectrumScore(s);
    if (!groups[score]) groups[score] = [];
    groups[score].push(s);
  }

  return (
    <div dir="rtl" className="space-y-3">
      {/* Scale bar */}
      <div className="flex items-center gap-0.5">
        {LABELS.map((l) => {
          const count = groups[l.score]?.length || 0;
          return (
            <div key={l.score} className="flex-1 flex flex-col items-center gap-1">
              <div className={`w-full h-2 ${l.color} ${count > 0 ? "opacity-100" : "opacity-20"}`} />
              {l.label && (
                <span className="text-[9px] text-slate-500">{l.label}</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Source dots on the scale */}
      <div className="space-y-1.5">
        {LABELS.filter((l) => groups[l.score]?.length).map((l) => (
          <div key={l.score} className="flex items-center gap-2">
            <div className={`w-2 h-2 shrink-0 ${l.color}`} />
            <div className="flex flex-wrap gap-1">
              {groups[l.score]!.map((s) => (
                <span key={s.slug} className="text-[11px] text-slate-600 dark:text-slate-400">
                  {s.name_fa || s.name_en}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
