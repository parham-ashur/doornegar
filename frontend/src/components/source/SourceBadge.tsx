"use client";

import { useLocale } from "next-intl";
import { cn, alignmentBadgeClasses, alignmentLabels } from "@/lib/utils";
import type { StateAlignment } from "@/lib/types";
import { Shield } from "lucide-react";

interface SourceBadgeProps {
  alignment: StateAlignment;
  irgcAffiliated?: boolean;
  className?: string;
}

export default function SourceBadge({
  alignment,
  irgcAffiliated = false,
  className,
}: SourceBadgeProps) {
  const locale = useLocale();
  const label = alignmentLabels[alignment][locale === "fa" ? "fa" : "en"];

  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <span className={alignmentBadgeClasses[alignment]}>{label}</span>
      {irgcAffiliated && (
        <span className="badge bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
          <Shield className="me-0.5 h-3 w-3" />
          {locale === "fa" ? "سپاه" : "IRGC"}
        </span>
      )}
    </span>
  );
}
