"use client";

import Link from "next/link";
import SourceCategorization from "@/components/feedback/SourceCategorization";
import type { Source } from "@/lib/types";

interface SourceSpectrumProps {
  sources: Source[];
  locale: string;
  showFeedback?: boolean;
}

const alignmentInfo: Record<string, { label: string; color: string; bg: string }> = {
  state: { label: "محافظه‌کار", color: "text-red-600 dark:text-red-400", bg: "bg-red-500" },
  semi_state: { label: "نیمه‌دولتی", color: "text-orange-600 dark:text-orange-400", bg: "bg-orange-500" },
  independent: { label: "مستقل", color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-500" },
  diaspora: { label: "اپوزیسیون", color: "text-blue-600 dark:text-blue-400", bg: "bg-blue-500" },
};

export default function SourceSpectrum({ sources, locale, showFeedback }: SourceSpectrumProps) {
  // Group sources by alignment
  const groups: Record<string, Source[]> = {};
  for (const s of sources) {
    const align = s.state_alignment || "independent";
    if (!groups[align]) groups[align] = [];
    groups[align].push(s);
  }

  const order = ["state", "semi_state", "independent", "diaspora"];

  return (
    <div dir="rtl" className="space-y-4">
      {/* Spectrum bar */}
      <div className="flex h-2 w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
        {order.map((align) => {
          const count = groups[align]?.length || 0;
          if (count === 0) return null;
          const pct = (count / sources.length) * 100;
          return (
            <div
              key={align}
              className={alignmentInfo[align]?.bg || "bg-slate-400"}
              style={{ width: `${pct}%` }}
            />
          );
        })}
      </div>

      {/* Source list grouped by alignment */}
      {order.map((align) => {
        const group = groups[align];
        if (!group || group.length === 0) return null;
        const info = alignmentInfo[align];

        return (
          <div key={align}>
            <h4 className={`text-[11px] font-bold mb-2 ${info.color}`}>
              {info.label} ({group.length})
            </h4>
            <div className="flex flex-wrap gap-2">
              {group.map((source) => (
                <div key={source.slug} className="flex items-center gap-1.5">
                  <Link
                    href={`/${locale}/sources/${source.slug}`}
                    className="flex items-center gap-1.5 px-2 py-1 border border-slate-200 dark:border-slate-700 text-[11px] font-medium text-slate-700 dark:text-slate-300 hover:border-slate-400 dark:hover:border-slate-500 transition-colors"
                  >
                    {source.logo_url ? (
                      <img src={source.logo_url} alt="" className="h-4 w-4 object-contain" />
                    ) : (
                      <span className={`inline-block h-2.5 w-2.5 ${info.bg}`} />
                    )}
                    {source.name_fa}
                  </Link>
                  {showFeedback && (
                    <SourceCategorization sourceId={source.id} currentAlignment={source.state_alignment} />
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
