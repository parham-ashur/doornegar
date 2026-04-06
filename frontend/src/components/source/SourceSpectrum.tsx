"use client";

import Link from "next/link";
import { Shield } from "lucide-react";
import type { Source } from "@/lib/types";

interface SourceSpectrumProps {
  sources: Source[];
  locale: string;
  highlightTopic?: string; // optional: highlight sources covering a specific topic
}

// Map state_alignment + factional_alignment to a position on -1 to +1 axis
function getSpectrumPosition(source: Source): number {
  // State/IRGC = far left (pro-regime)
  if (source.irgc_affiliated) return -0.9;
  if (source.state_alignment === "state") {
    if (source.factional_alignment === "hardline") return -0.85;
    return -0.7;
  }
  if (source.state_alignment === "semi_state") {
    if (source.factional_alignment === "principlist") return -0.5;
    if (source.factional_alignment === "moderate") return -0.2;
    return -0.3;
  }
  if (source.state_alignment === "independent") return 0.1;
  // Diaspora
  if (source.factional_alignment === "opposition") return 0.7;
  return 0.4; // diaspora neutral
}

function getSpectrumColor(position: number): string {
  if (position < -0.5) return "bg-red-500 border-red-400";
  if (position < -0.1) return "bg-amber-500 border-amber-400";
  if (position <= 0.1) return "bg-emerald-500 border-emerald-400";
  if (position <= 0.5) return "bg-blue-400 border-blue-300";
  return "bg-blue-600 border-blue-500";
}

export default function SourceSpectrum({ sources, locale, highlightTopic }: SourceSpectrumProps) {
  const positioned = sources
    .map((s) => ({ source: s, position: getSpectrumPosition(s) }))
    .sort((a, b) => a.position - b.position);

  return (
    <div>
      {/* Spectrum bar */}
      <div className="relative mx-auto max-w-3xl">
        {/* Gradient bar */}
        <div className="h-3 rounded-full bias-gradient opacity-60" />

        {/* Axis labels */}
        <div className="mt-1 flex justify-between text-[10px] text-slate-500 dark:text-slate-400">
          <span>{locale === "fa" ? "حکومتی" : "Pro-regime"}</span>
          <span>{locale === "fa" ? "میانه" : "Center"}</span>
          <span>{locale === "fa" ? "اپوزیسیون" : "Opposition"}</span>
        </div>

        {/* Source dots on the spectrum */}
        <div className="relative mt-4 h-16">
          {positioned.map(({ source, position }, i) => {
            const leftPercent = ((position + 1) / 2) * 100;
            // Stagger vertically to avoid overlap
            const topOffset = (i % 2) * 28;
            const name = locale === "fa" ? source.name_fa : source.name_en;

            return (
              <Link
                key={source.slug}
                href={`/${locale}/sources/${source.slug}`}
                className="absolute flex flex-col items-center group"
                style={{
                  left: `${leftPercent}%`,
                  top: `${topOffset}px`,
                  transform: "translateX(-50%)",
                }}
              >
                <div
                  className={`flex items-center gap-1 rounded-full border-2 px-2.5 py-1 text-[10px] font-semibold text-white shadow-sm transition-transform group-hover:scale-110 ${getSpectrumColor(position)}`}
                >
                  {source.irgc_affiliated && <Shield className="h-3 w-3" />}
                  {name.length > 12 ? name.slice(0, 10) + "…" : name}
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
