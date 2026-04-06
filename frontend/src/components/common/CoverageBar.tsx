"use client";

import { useLocale } from "next-intl";
import { cn, alignmentLabels } from "@/lib/utils";
import type { StateAlignment } from "@/lib/types";

interface CoverageBarProps {
  segments: { alignment: StateAlignment; count: number }[];
  showLabels?: boolean;
  height?: "sm" | "md" | "lg";
  className?: string;
}

const segmentColors: Record<StateAlignment, string> = {
  state: "bg-state",
  semi_state: "bg-semi-state",
  independent: "bg-independent",
  diaspora: "bg-diaspora",
};

export default function CoverageBar({
  segments,
  showLabels = false,
  height = "md",
  className,
}: CoverageBarProps) {
  const locale = useLocale();
  const total = segments.reduce((sum, s) => sum + s.count, 0);

  if (total === 0) return null;

  const heights = { sm: "h-2", md: "h-3", lg: "h-4" };

  return (
    <div className={cn("w-full", className)}>
      {/* Stacked bar */}
      <div className={cn("flex overflow-hidden rounded-full", heights[height])}>
        {segments.map((segment) => {
          const pct = (segment.count / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              key={segment.alignment}
              className={cn(segmentColors[segment.alignment], "transition-all")}
              style={{ width: `${pct}%` }}
              title={`${alignmentLabels[segment.alignment][locale === "fa" ? "fa" : "en"]}: ${segment.count}`}
            />
          );
        })}
      </div>

      {/* Labels */}
      {showLabels && (
        <div className="mt-1.5 flex flex-wrap gap-3 text-xs">
          {segments
            .filter((s) => s.count > 0)
            .map((segment) => (
              <div key={segment.alignment} className="flex items-center gap-1">
                <div className={cn("h-2.5 w-2.5 rounded-full", segmentColors[segment.alignment])} />
                <span className="text-slate-600 dark:text-slate-400">
                  {alignmentLabels[segment.alignment][locale === "fa" ? "fa" : "en"]}
                  {" "}({segment.count})
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
