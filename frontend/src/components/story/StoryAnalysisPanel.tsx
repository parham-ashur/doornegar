"use client";

import { useState } from "react";
import { GROUP_COLORS, GROUP_LABELS_FA } from "@/lib/narrativeGroups";
import type { NarrativeGroup, StoryAnalysis } from "@/lib/types";

type TabKey = "bias" | "inside" | "outside";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bias", label: "مقایسه روایت‌ها" },
  { key: "inside", label: "روایت درون‌مرزی" },
  { key: "outside", label: "روایت برون‌مرزی" },
];

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
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
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

export default function StoryAnalysisPanel({ analysis }: { analysis: StoryAnalysis | null }) {
  const [activeTab, setActiveTab] = useState<TabKey>("bias");

  const hasBias = analysis?.bias_explanation_fa || analysis?.state_summary_fa || analysis?.diaspora_summary_fa;
  if (!analysis && !hasBias) return null;

  return (
    <div dir="rtl">
      {/* Tab bar */}
      <div className="flex gap-0 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-5 py-3 text-[13px] font-bold transition-colors ${
              activeTab === tab.key
                ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                : "text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content — full width */}
      <div className="py-5 border-b border-slate-200 dark:border-slate-800">
        {activeTab === "bias" && (
          <div>
            {/* Editor prose overview — sits above the two-column split */}
            {analysis?.bias_explanation_fa && (
              <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-300 mb-5">
                {analysis.bias_explanation_fa}
              </p>
            )}
            {/* Two-column 4-subgroup comparison. Inside gets principlist +
                reformist (navy family); outside gets moderate + radical
                (amber family). Each subgroup uses its own GROUP_COLORS
                shade so the reader can read bullets by faction at a glance. */}
            {(analysis?.narrative?.inside || analysis?.narrative?.outside) ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Inside Iran */}
                <div className="border-r-2 border-[#1e3a5f] pr-4 space-y-4">
                  <p className="text-[13px] font-black text-[#1e3a5f] dark:text-blue-300">
                    روایت درون‌مرزی
                  </p>
                  <SubgroupBullets
                    group="principlist"
                    bullets={analysis?.narrative?.inside?.principlist || []}
                  />
                  <SubgroupBullets
                    group="reformist"
                    bullets={analysis?.narrative?.inside?.reformist || []}
                  />
                  {!(analysis?.narrative?.inside?.principlist?.length ||
                     analysis?.narrative?.inside?.reformist?.length) &&
                     analysis?.state_summary_fa && (
                    <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                      {analysis.state_summary_fa}
                    </p>
                  )}
                </div>
                {/* Outside Iran */}
                <div className="border-r-2 border-[#c2410c] pr-4 space-y-4">
                  <p className="text-[13px] font-black text-[#c2410c] dark:text-orange-400">
                    روایت برون‌مرزی
                  </p>
                  <SubgroupBullets
                    group="moderate_diaspora"
                    bullets={analysis?.narrative?.outside?.moderate || []}
                  />
                  <SubgroupBullets
                    group="radical_diaspora"
                    bullets={analysis?.narrative?.outside?.radical || []}
                  />
                  {!(analysis?.narrative?.outside?.moderate?.length ||
                     analysis?.narrative?.outside?.radical?.length) &&
                     analysis?.diaspora_summary_fa && (
                    <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                      {analysis.diaspora_summary_fa}
                    </p>
                  )}
                </div>
              </div>
            ) : (analysis?.state_summary_fa || analysis?.diaspora_summary_fa) ? (
              // Legacy two-string fallback when the 4-subgroup structure
              // hasn't been populated for this story yet.
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="border-r-2 border-[#1e3a5f] pr-4">
                  <p className="text-[13px] font-black text-[#1e3a5f] dark:text-blue-300 mb-2">
                    روایت درون‌مرزی
                  </p>
                  <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                    {analysis?.state_summary_fa || "—"}
                  </p>
                </div>
                <div className="border-r-2 border-[#c2410c] pr-4">
                  <p className="text-[13px] font-black text-[#c2410c] dark:text-orange-400 mb-2">
                    روایت برون‌مرزی
                  </p>
                  <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                    {analysis?.diaspora_summary_fa || "—"}
                  </p>
                </div>
              </div>
            ) : !analysis?.bias_explanation_fa ? (
              <p className="text-[13px] text-slate-400">داده‌ای موجود نیست</p>
            ) : null}
          </div>
        )}

        {activeTab === "inside" && (
          <div>
            {analysis?.narrative?.inside ? (
              <>
                <SubgroupBullets
                  group="principlist"
                  bullets={analysis.narrative.inside.principlist || []}
                />
                <SubgroupBullets
                  group="reformist"
                  bullets={analysis.narrative.inside.reformist || []}
                />
                <FramingTags framing={analysis.scores?.state?.framing || null} />
              </>
            ) : analysis?.state_summary_fa ? (
              <>
                <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.state_summary_fa}</p>
                <FramingTags framing={analysis.scores?.state?.framing || null} />
              </>
            ) : (
              <p className="text-[13px] text-slate-400">روایتی از سوی رسانه‌های درون‌مرزی یافت نشد</p>
            )}
          </div>
        )}

        {activeTab === "outside" && (
          <div>
            {analysis?.narrative?.outside ? (
              <>
                <SubgroupBullets
                  group="moderate_diaspora"
                  bullets={analysis.narrative.outside.moderate || []}
                />
                <SubgroupBullets
                  group="radical_diaspora"
                  bullets={analysis.narrative.outside.radical || []}
                />
                <FramingTags framing={analysis.scores?.diaspora?.framing || null} />
              </>
            ) : analysis?.diaspora_summary_fa ? (
              <>
                <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.diaspora_summary_fa}</p>
                <FramingTags framing={analysis.scores?.diaspora?.framing || null} />
              </>
            ) : (
              <p className="text-[13px] text-slate-400">روایتی از سوی رسانه‌های برون‌مرزی یافت نشد</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
