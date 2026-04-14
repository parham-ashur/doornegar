"use client";

import type { Source } from "@/lib/types";
import { alignmentLabels } from "@/lib/utils";
import type { StateAlignment } from "@/lib/types";

interface Props {
  sourceA: Source;
  sourceB: Source;
  onClose: () => void;
}

function AlignmentDot({ alignment }: { alignment: StateAlignment }) {
  const colors: Record<StateAlignment, string> = {
    state: "#1e3a5f",
    semi_state: "#6b7280",
    independent: "#059669",
    diaspora: "#ea580c",
  };
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0"
      style={{ backgroundColor: colors[alignment] || "#64748b" }}
    />
  );
}

function SourceColumn({ source }: { source: Source }) {
  const alignment = source.state_alignment as StateAlignment;
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-2">
        <AlignmentDot alignment={alignment} />
        <h3 className="text-base font-black text-slate-900 dark:text-white truncate">
          {source.name_fa}
        </h3>
      </div>

      <dl className="space-y-2 text-[12px]">
        <div>
          <dt className="text-slate-500 dark:text-slate-400">جایگاه سیاسی</dt>
          <dd className="font-bold text-slate-800 dark:text-slate-200">
            {alignmentLabels[alignment]?.fa || alignment}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">محل تولید</dt>
          <dd className="font-bold text-slate-800 dark:text-slate-200">
            {source.production_location === "inside_iran"
              ? "داخل ایران"
              : "خارج از ایران"}
          </dd>
        </div>
        {source.factional_alignment && (
          <div>
            <dt className="text-slate-500 dark:text-slate-400">گرایش جناحی</dt>
            <dd className="font-bold text-slate-800 dark:text-slate-200">
              {source.factional_alignment}
            </dd>
          </div>
        )}
        {source.description_fa && (
          <div>
            <dt className="text-slate-500 dark:text-slate-400">درباره</dt>
            <dd className="text-slate-700 dark:text-slate-300 line-clamp-3 leading-relaxed">
              {source.description_fa}
            </dd>
          </div>
        )}
        {source.credibility_score != null && (
          <div>
            <dt className="text-slate-500 dark:text-slate-400">امتیاز اعتبار</dt>
            <dd className="font-bold text-slate-800 dark:text-slate-200">
              {Math.round(source.credibility_score * 100)}٪
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export default function SourceComparison({ sourceA, sourceB, onClose }: Props) {
  return (
    <div className="mb-8 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 p-5">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-200 dark:border-slate-800">
        <h2 className="text-sm font-black text-slate-900 dark:text-white">
          مقایسه رسانه‌ها
        </h2>
        <button
          onClick={onClose}
          className="text-[11px] text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
        >
          بستن
        </button>
      </div>

      <div className="flex gap-6">
        <SourceColumn source={sourceA} />
        <div className="w-px bg-slate-200 dark:bg-slate-700 shrink-0" />
        <SourceColumn source={sourceB} />
      </div>

      <p className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400">
        برای مقایسه عمیق‌تر، روی هر خبر کلیک کنید تا پوشش هر دو رسانه را ببینید.
      </p>
    </div>
  );
}
