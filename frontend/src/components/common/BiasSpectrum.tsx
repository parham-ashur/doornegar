"use client";

import { useLocale } from "next-intl";
import { cn, biasAlignmentLabel } from "@/lib/utils";

interface BiasSpectrumProps {
  value: number; // -1 (pro-regime) to +1 (opposition)
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}

export default function BiasSpectrum({
  value,
  size = "md",
  showLabel = true,
  className,
}: BiasSpectrumProps) {
  const locale = useLocale();

  // Map -1..+1 to 0..100 percentage
  const position = ((value + 1) / 2) * 100;

  const heights = { sm: "h-2", md: "h-3", lg: "h-4" };
  const markerSizes = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-6 w-6" };

  return (
    <div className={cn("w-full", className)}>
      <div className="relative">
        {/* Gradient bar */}
        <div className={cn("bias-gradient w-full rounded-full", heights[size])} />

        {/* Position marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2"
          style={{ left: `${position}%`, transform: `translate(-50%, -50%)` }}
        >
          <div
            className={cn(
              "rounded-full border-2 border-white bg-slate-900 shadow-md dark:border-slate-900 dark:bg-white",
              markerSizes[size]
            )}
          />
        </div>
      </div>

      {/* Labels */}
      {showLabel && (
        <div className="mt-1.5 flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>{locale === "fa" ? "حکومتی" : "Pro-regime"}</span>
          <span className="font-medium text-slate-700 dark:text-slate-300">
            {biasAlignmentLabel(value, locale)}
          </span>
          <span>{locale === "fa" ? "اپوزیسیون" : "Opposition"}</span>
        </div>
      )}
    </div>
  );
}
