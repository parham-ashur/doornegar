"use client";

import { useState } from "react";
import { GROUP_COLORS, GROUP_LABELS_FA } from "@/lib/narrativeGroups";
import type { NarrativeGroup, StoryAnalysis } from "@/lib/types";

const TAB_BASE =
  "cursor-pointer px-5 py-3 text-[13px] font-bold transition-colors";
const TAB_INACTIVE =
  "text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50";
const TAB_ACTIVE =
  "bg-slate-900 dark:bg-white text-white dark:text-slate-900";

type TabKey = "bias" | "inside" | "outside";

function FramingTags({ framing }: { framing: string | string[] | null }) {
  if (!framing) return null;
  const items = Array.isArray(framing) ? framing : [framing];
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-4">
      <span className="text-[13px] text-slate-500">چارچوب‌بندی:</span>
      {items.map((f, i) => (
        <span
          key={i}
          className="framing-keyword px-2 py-0.5 text-[13px] border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300"
          data-keyword={(f || "").trim()}
        >
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
    <div className="mb-5">
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

// Three tabs, distinct content per tab:
//   1. مقایسه روایت‌ها — editor prose (bias_explanation_fa) only.
//      The overall comparative framing without repeating the
//      per-side bullets the other two tabs cover.
//   2. روایت درون‌مرزی — principlist + reformist subgroup bullets
//      (colored) + state-side framing tags.
//   3. روایت برون‌مرزی — moderate + radical subgroup bullets
//      (colored) + diaspora-side framing tags.
//
// No content repeats across tabs. Previously all three rendered
// the same 4-subgroup bullets and readers saw each one up to 3×.
export default function StoryAnalysisPanel({ analysis }: { analysis: StoryAnalysis | null }) {
  const [active, setActive] = useState<TabKey>("bias");

  const hasBias =
    analysis?.bias_explanation_fa ||
    analysis?.state_summary_fa ||
    analysis?.diaspora_summary_fa ||
    analysis?.narrative?.inside ||
    analysis?.narrative?.outside;
  // Empty-state: story is too new / coverage too thin for a comparison.
  // Explain why and that it will auto-fill, instead of hiding the section
  // entirely or showing empty tabs.
  if (!analysis || !hasBias) {
    return (
      <div dir="rtl" className="border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 p-4">
        <h3 className="text-[13px] font-black text-slate-700 dark:text-slate-300 mb-2">
          تحلیل سوگیری و مقایسهٔ روایت‌ها
        </h3>
        <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400">
          این خبر تازه ثبت شده است. برای مقایسهٔ روایت درون‌مرزی و برون‌مرزی و تحلیل سوگیری،
          به پوشش از چند رسانه از هر دو طرف نیاز داریم. به‌محض آماده‌شدن تحلیل، این بخش
          به‌طور خودکار پُر می‌شود.
        </p>
      </div>
    );
  }

  return (
    <div dir="rtl">
      {/* Tab bar */}
      <div className="flex gap-0 border-b border-slate-200 dark:border-slate-800">
        <button type="button" onClick={() => setActive("bias")} className={`${TAB_BASE} ${active === "bias" ? TAB_ACTIVE : TAB_INACTIVE}`}>مقایسه روایت‌ها</button>
        <button type="button" onClick={() => setActive("inside")} className={`${TAB_BASE} ${active === "inside" ? TAB_ACTIVE : TAB_INACTIVE}`}>روایت درون‌مرزی</button>
        <button type="button" onClick={() => setActive("outside")} className={`${TAB_BASE} ${active === "outside" ? TAB_ACTIVE : TAB_INACTIVE}`}>روایت برون‌مرزی</button>
      </div>

      {/* Tab content */}
      <div className="py-5 border-b border-slate-200 dark:border-slate-800">
        <div className={active === "bias" ? "block" : "hidden"}>
            {/* Per-subgroup BIAS framing (how each subgroup slants the
                story — word choices, emphasis, framing) — distinct from
                the narrative bullets in the inside/outside tabs (which
                report WHAT they said). Colored headings by side +
                subgroup; falls back to the flat bias_explanation_fa
                prose on legacy stories without per-subgroup bias. */}
            {(() => {
              const bs = analysis.narrative?.bias_by_subgroup;
              const hasStructured =
                bs && (bs.principlist || bs.reformist || bs.moderate_diaspora || bs.radical_diaspora);
              if (!hasStructured) {
                return analysis.bias_explanation_fa ? (
                  <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-300">
                    {analysis.bias_explanation_fa}
                  </p>
                ) : (
                  <p className="text-[13px] text-slate-400">
                    متن تحلیل سوگیری هنوز نوشته نشده.
                  </p>
                );
              }
              return (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Inside Iran column */}
                  <div className="border-r-2 border-[#1e3a5f] pr-4 space-y-5">
                    <h4 className="text-[14px] font-black text-[#1e3a5f] dark:text-blue-300">
                      روایت درون‌مرزی
                    </h4>
                    {bs.principlist && (
                      <div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="inline-block h-2.5 w-2.5"
                            style={{ backgroundColor: GROUP_COLORS.principlist }}
                          />
                          <h5 className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300">
                            {GROUP_LABELS_FA.principlist}
                          </h5>
                        </div>
                        <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                          {bs.principlist}
                        </p>
                      </div>
                    )}
                    {bs.reformist && (
                      <div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="inline-block h-2.5 w-2.5"
                            style={{ backgroundColor: GROUP_COLORS.reformist }}
                          />
                          <h5 className="text-[13px] font-bold text-[#4f7cac] dark:text-sky-300">
                            {GROUP_LABELS_FA.reformist}
                          </h5>
                        </div>
                        <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                          {bs.reformist}
                        </p>
                      </div>
                    )}
                  </div>
                  {/* Outside Iran column */}
                  <div className="border-r-2 border-[#c2410c] pr-4 space-y-5">
                    <h4 className="text-[14px] font-black text-[#c2410c] dark:text-orange-400">
                      روایت برون‌مرزی
                    </h4>
                    {bs.moderate_diaspora && (
                      <div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="inline-block h-2.5 w-2.5"
                            style={{ backgroundColor: GROUP_COLORS.moderate_diaspora }}
                          />
                          <h5 className="text-[13px] font-bold text-[#f97316] dark:text-amber-400">
                            {GROUP_LABELS_FA.moderate_diaspora}
                          </h5>
                        </div>
                        <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                          {bs.moderate_diaspora}
                        </p>
                      </div>
                    )}
                    {bs.radical_diaspora && (
                      <div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="inline-block h-2.5 w-2.5"
                            style={{ backgroundColor: GROUP_COLORS.radical_diaspora }}
                          />
                          <h5 className="text-[13px] font-bold text-[#c2410c] dark:text-red-400">
                            {GROUP_LABELS_FA.radical_diaspora}
                          </h5>
                        </div>
                        <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                          {bs.radical_diaspora}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
        </div>

        <div className={active === "inside" ? "block" : "hidden"}>
            {analysis.narrative?.inside &&
             ((analysis.narrative.inside.principlist?.length || 0) +
              (analysis.narrative.inside.reformist?.length || 0) > 0) ? (
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
            ) : analysis.state_summary_fa ? (
              <>
                <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.state_summary_fa}</p>
                <FramingTags framing={analysis.scores?.state?.framing || null} />
              </>
            ) : (
              <p className="text-[13px] text-slate-400">روایتی از سوی رسانه‌های درون‌مرزی یافت نشد</p>
            )}
        </div>

        <div className={active === "outside" ? "block" : "hidden"}>
            {analysis.narrative?.outside &&
             ((analysis.narrative.outside.moderate?.length || 0) +
              (analysis.narrative.outside.radical?.length || 0) > 0) ? (
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
            ) : analysis.diaspora_summary_fa ? (
              <>
                <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.diaspora_summary_fa}</p>
                <FramingTags framing={analysis.scores?.diaspora?.framing || null} />
              </>
            ) : (
              <p className="text-[13px] text-slate-400">روایتی از سوی رسانه‌های برون‌مرزی یافت نشد</p>
            )}
        </div>
      </div>
    </div>
  );
}
