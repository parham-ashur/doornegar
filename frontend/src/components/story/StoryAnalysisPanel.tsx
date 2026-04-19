"use client";

import { GROUP_COLORS, GROUP_LABELS_FA } from "@/lib/narrativeGroups";
import type { NarrativeGroup, StoryAnalysis } from "@/lib/types";

function FramingTags({ framing }: { framing: string | string[] | null }) {
  if (!framing) return null;
  const items = Array.isArray(framing) ? framing : [framing];
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-3">
      <span className="text-[13px] text-slate-500">چارچوب‌بندی:</span>
      {items.map((f, i) => (
        <span key={i} className="px-2 py-0.5 text-[13px] border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300">
          {f}
        </span>
      ))}
    </div>
  );
}

function SubgroupBullets({
  group,
  bullets,
}: {
  group: NarrativeGroup;
  bullets: string[];
}) {
  if (!bullets || bullets.length === 0) return null;
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="inline-block h-2.5 w-2.5"
          style={{ backgroundColor: GROUP_COLORS[group] }}
        />
        <h5 className="text-[13px] font-bold text-slate-700 dark:text-slate-300">
          {GROUP_LABELS_FA[group]}
        </h5>
      </div>
      <ul className="space-y-1.5 pr-4">
        {bullets.map((b, i) => (
          <li key={i} className="text-[13px] leading-6 text-slate-600 dark:text-slate-400 list-disc">
            {b}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Single unified bias-comparison view. Previously had three tabs
// (bias / inside / outside) that rendered overlapping content — the
// inside + outside tabs were just subsets of what the bias tab already
// showed in two columns. Collapsing to one canonical layout means the
// reader sees each subgroup's bullets exactly once, with framing tags
// aligned to the side they describe.
export default function StoryAnalysisPanel({ analysis }: { analysis: StoryAnalysis | null }) {
  const hasBias =
    analysis?.bias_explanation_fa ||
    analysis?.state_summary_fa ||
    analysis?.diaspora_summary_fa ||
    analysis?.narrative?.inside ||
    analysis?.narrative?.outside;
  if (!analysis || !hasBias) return null;

  const insideBullets =
    (analysis.narrative?.inside?.principlist?.length || 0) +
    (analysis.narrative?.inside?.reformist?.length || 0);
  const outsideBullets =
    (analysis.narrative?.outside?.moderate?.length || 0) +
    (analysis.narrative?.outside?.radical?.length || 0);
  const hasSubgroups = insideBullets + outsideBullets > 0;

  return (
    <div dir="rtl" className="py-5 border-b border-slate-200 dark:border-slate-800">
      {/* Section heading */}
      <h3 className="text-[15px] font-black text-slate-900 dark:text-white mb-4">
        مقایسه روایت‌ها
      </h3>

      {/* Editor prose overview */}
      {analysis.bias_explanation_fa && (
        <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-300 mb-6">
          {analysis.bias_explanation_fa}
        </p>
      )}

      {hasSubgroups ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Inside Iran */}
          <div className="border-r-2 border-[#1e3a5f] pr-4 space-y-4">
            <p className="text-[13px] font-black text-[#1e3a5f] dark:text-blue-300">
              روایت درون‌مرزی
            </p>
            <SubgroupBullets
              group="principlist"
              bullets={analysis.narrative?.inside?.principlist || []}
            />
            <SubgroupBullets
              group="reformist"
              bullets={analysis.narrative?.inside?.reformist || []}
            />
            <FramingTags framing={analysis.scores?.state?.framing || null} />
          </div>

          {/* Outside Iran */}
          <div className="border-r-2 border-[#c2410c] pr-4 space-y-4">
            <p className="text-[13px] font-black text-[#c2410c] dark:text-orange-400">
              روایت برون‌مرزی
            </p>
            <SubgroupBullets
              group="moderate_diaspora"
              bullets={analysis.narrative?.outside?.moderate || []}
            />
            <SubgroupBullets
              group="radical_diaspora"
              bullets={analysis.narrative?.outside?.radical || []}
            />
            <FramingTags framing={analysis.scores?.diaspora?.framing || null} />
          </div>
        </div>
      ) : (analysis.state_summary_fa || analysis.diaspora_summary_fa) ? (
        // Legacy fallback — two flat summaries when no 4-subgroup
        // narrative is populated for the story yet.
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="border-r-2 border-[#1e3a5f] pr-4">
            <p className="text-[13px] font-black text-[#1e3a5f] dark:text-blue-300 mb-2">
              روایت درون‌مرزی
            </p>
            {analysis.state_summary_fa ? (
              <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                {analysis.state_summary_fa}
              </p>
            ) : (
              <p className="text-[13px] text-slate-400">—</p>
            )}
            <FramingTags framing={analysis.scores?.state?.framing || null} />
          </div>
          <div className="border-r-2 border-[#c2410c] pr-4">
            <p className="text-[13px] font-black text-[#c2410c] dark:text-orange-400 mb-2">
              روایت برون‌مرزی
            </p>
            {analysis.diaspora_summary_fa ? (
              <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                {analysis.diaspora_summary_fa}
              </p>
            ) : (
              <p className="text-[13px] text-slate-400">—</p>
            )}
            <FramingTags framing={analysis.scores?.diaspora?.framing || null} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
