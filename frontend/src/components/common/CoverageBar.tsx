"use client";

import { cn } from "@/lib/utils";
import type { StateAlignment } from "@/lib/types";

interface CoverageBarProps {
  segments: { alignment: StateAlignment; count: number }[];
  showLabels?: boolean;
  height?: "sm" | "md" | "lg";
  className?: string;
}

const segmentColors: Record<StateAlignment, string> = {
  state: "bg-red-500",
  semi_state: "bg-orange-500",
  independent: "bg-emerald-500",
  diaspora: "bg-blue-500",
};

const segmentLabels: Record<StateAlignment, string> = {
  state: "حکومتی",
  semi_state: "نیمه‌دولتی",
  independent: "مستقل",
  diaspora: "برون‌مرزی",
};

const segmentTextColors: Record<StateAlignment, string> = {
  state: "text-red-600 dark:text-red-400",
  semi_state: "text-orange-600 dark:text-orange-400",
  independent: "text-emerald-600 dark:text-emerald-400",
  diaspora: "text-blue-600 dark:text-blue-400",
};

export default function CoverageBar({
  segments,
  showLabels = false,
  height = "md",
  className,
}: CoverageBarProps) {
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  if (total === 0) return null;

  const heights = { sm: "h-1.5", md: "h-2", lg: "h-3" };

  return (
    <div className={cn("w-full", className)}>
      <div className={cn("flex overflow-hidden bg-slate-200 dark:bg-slate-800", heights[height])}>
        {segments.map((segment) => {
          const pct = (segment.count / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              key={segment.alignment}
              className={cn(segmentColors[segment.alignment], "transition-all")}
              style={{ width: `${pct}%` }}
            />
          );
        })}
      </div>

      {showLabels && (
        <div className="mt-1.5 flex flex-wrap gap-3 text-[10px]">
          {segments
            .filter((s) => s.count > 0)
            .map((segment) => (
              <div key={segment.alignment} className={cn("flex items-center gap-1 font-medium", segmentTextColors[segment.alignment])}>
                <div className={cn("h-1.5 w-1.5", segmentColors[segment.alignment])} />
                {segmentLabels[segment.alignment]} ({segment.count})
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
