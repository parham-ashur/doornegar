"use client";

import { useState } from "react";
import { BarChart3, Brain } from "lucide-react";
import type { StoryAnalysis } from "@/lib/types";

type TabKey = "bias" | "conservative" | "opposition";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bias", label: "مقایسه سوگیری" },
  { key: "conservative", label: "محافظه‌کار" },
  { key: "opposition", label: "اپوزیسیون" },
];

function FramingTags({ framing }: { framing: string | string[] | null }) {
  if (!framing) return null;
  const items = Array.isArray(framing) ? framing : [framing];
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-3">
      <span className="text-[10px] text-slate-500">چارچوب‌بندی:</span>
      {items.map((f, i) => (
        <span key={i} className="px-2 py-0.5 text-[10px] border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300">
          {f}
        </span>
      ))}
    </div>
  );
}

export default function StoryAnalysisPanel({ analysis }: { analysis: StoryAnalysis | null }) {
  const [activeTab, setActiveTab] = useState<TabKey>("bias");

  const hasBias = analysis?.bias_explanation_fa || analysis?.state_summary_fa || analysis?.diaspora_summary_fa;
  if (!analysis && !hasBias) return null;

  // Compute some stats for the sidebar
  const stateFraming = analysis?.scores?.state?.framing;
  const diasporaFraming = analysis?.scores?.diaspora?.framing;
  const hasAnalyst = !!(analysis as any)?.analyst;
  const neutralityData = analysis?.source_neutrality;
  const neutralityValues = neutralityData ? Object.values(neutralityData) : [];
  const avgNeutrality = neutralityValues.length > 0
    ? neutralityValues.reduce((a, b) => a + b, 0) / neutralityValues.length
    : null;

  return (
    <div dir="rtl">
      {/* Tab bar with strong selected state */}
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

      {/* Content area: main content + analyst sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 border-b border-slate-200 dark:border-slate-800">
        {/* Main tab content (2/3) */}
        <div className="lg:col-span-2 py-5 lg:pl-6 lg:border-l border-slate-200 dark:border-slate-800">
          {activeTab === "bias" && (
            <div className="space-y-2">
              {analysis?.bias_explanation_fa
                ?.split(/[.؛]/)
                .map((s) => s.trim())
                .filter((s) => s.length > 10)
                .map((point, i) => (
                  <div key={i} className="flex gap-2 text-[13px] leading-6">
                    <span className="text-slate-400 mt-1 shrink-0">•</span>
                    <span className="text-slate-600 dark:text-slate-400">{point}</span>
                  </div>
                )) || (
                <p className="text-[13px] text-slate-400">داده‌ای موجود نیست</p>
              )}
            </div>
          )}

          {activeTab === "conservative" && (
            <div>
              {analysis?.state_summary_fa ? (
                <>
                  <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">
                    {analysis.state_summary_fa}
                  </p>
                  <FramingTags framing={analysis.scores?.state?.framing || null} />
                </>
              ) : (
                <p className="text-[13px] text-slate-400">پوششی از سوی رسانه‌های محافظه‌کار یافت نشد</p>
              )}
            </div>
          )}

          {activeTab === "opposition" && (
            <div>
              {analysis?.diaspora_summary_fa ? (
                <>
                  <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">
                    {analysis.diaspora_summary_fa}
                  </p>
                  <FramingTags framing={analysis.scores?.diaspora?.framing || null} />
                </>
              ) : (
                <p className="text-[13px] text-slate-400">پوششی از سوی رسانه‌های اپوزیسیون یافت نشد</p>
              )}
            </div>
          )}
        </div>

        {/* Analyst / Stats sidebar (1/3) */}
        <div className="py-5 lg:pr-6 space-y-5">
          {/* Summary stats */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 className="h-4 w-4 text-slate-400" />
              <h4 className="text-[12px] font-bold text-slate-900 dark:text-white">آمار خلاصه</h4>
            </div>
            <div className="space-y-2 text-[11px]">
              {stateFraming && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">چارچوب محافظه‌کار</span>
                  <span className="text-slate-700 dark:text-slate-300 font-medium">
                    {(Array.isArray(stateFraming) ? stateFraming : [stateFraming]).join("، ")}
                  </span>
                </div>
              )}
              {diasporaFraming && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">چارچوب اپوزیسیون</span>
                  <span className="text-slate-700 dark:text-slate-300 font-medium">
                    {(Array.isArray(diasporaFraming) ? diasporaFraming : [diasporaFraming]).join("، ")}
                  </span>
                </div>
              )}
              {avgNeutrality !== null && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">میانگین بی‌طرفی</span>
                  <span className={`font-mono font-medium ${avgNeutrality > 0 ? "text-emerald-600" : "text-red-500"}`}>
                    {avgNeutrality > 0 ? "+" : ""}{avgNeutrality.toFixed(2)}
                  </span>
                </div>
              )}
              {neutralityData && Object.entries(neutralityData).length > 0 && (
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-1">
                  {Object.entries(neutralityData)
                    .sort(([, a], [, b]) => b - a)
                    .map(([slug, score]) => (
                      <div key={slug} className="flex items-center justify-between text-[10px]">
                        <span className="text-slate-400 truncate max-w-[60%]">{slug}</span>
                        <span className={`font-mono ${score > 0 ? "text-emerald-500" : score < -0.3 ? "text-red-400" : "text-slate-500"}`}>
                          {score > 0 ? "+" : ""}{score.toFixed(1)}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>

          {/* Analyst placeholder */}
          <div className="border-t border-slate-100 dark:border-slate-800 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <Brain className="h-4 w-4 text-slate-400" />
              <h4 className="text-[12px] font-bold text-slate-900 dark:text-white">تحلیلگر دورنگر</h4>
            </div>
            {hasAnalyst ? (
              <p className="text-[11px] text-slate-500">تحلیل عمیق در دسترس است</p>
            ) : (
              <div className="space-y-2">
                <div className="h-3 w-3/4 bg-slate-100 dark:bg-slate-800 animate-pulse" />
                <div className="h-3 w-1/2 bg-slate-100 dark:bg-slate-800 animate-pulse" />
                <p className="text-[10px] text-slate-400 mt-2">تحلیل عمیق پس از اجرای بعدی در دسترس خواهد بود</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
