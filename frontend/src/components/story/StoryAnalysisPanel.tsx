"use client";

import { useState } from "react";
import type { StoryAnalysis } from "@/lib/types";

// ─── Tabs: مقایسه سوگیری | محافظه‌کار و اوپوزیسیون ────

type TabKey = "bias" | "conservative" | "opposition";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bias", label: "مقایسه سوگیری" },
  { key: "conservative", label: "حکومتی" },
  { key: "opposition", label: "اپوزیسیون" },
];

function ScoreBar({ label, value, max = 5 }: { label: string; value: number | null; max?: number }) {
  if (value === null || value === undefined) return null;
  const pct = Math.min(100, Math.max(0, (Math.abs(value) / max) * 100));
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-24 text-slate-500 dark:text-slate-400 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-200 dark:bg-slate-800 overflow-hidden">
        <div className="h-full bg-slate-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-6 text-left font-mono text-slate-400">{value}</span>
    </div>
  );
}

function FramingTags({ framing }: { framing: string | string[] | null }) {
  if (!framing) return null;
  const items = Array.isArray(framing) ? framing : [framing];
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-2">
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

  if (!analysis || !analysis.summary_fa) return null;

  return (
    <div dir="rtl" className="space-y-4">
      {/* Summary */}
      <div className="pb-4">
        <p className="text-[14px] leading-7 text-slate-700 dark:text-slate-300">{analysis.summary_fa}</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-0 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-5 py-2.5 text-[13px] font-bold border-b-2 transition-colors ${
              activeTab === tab.key
                ? "border-slate-900 dark:border-white text-slate-900 dark:text-white"
                : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="py-4">
        {activeTab === "bias" && (
          <div className="space-y-4">
            {/* Bias comparison as bullet points */}
            {analysis.bias_explanation_fa && (
              <div className="space-y-2">
                {analysis.bias_explanation_fa
                  .split(/[.؛]/)
                  .map((s) => s.trim())
                  .filter((s) => s.length > 10)
                  .map((point, i) => (
                    <div key={i} className="flex gap-2 text-[13px] leading-6">
                      <span className="text-slate-400 mt-1 shrink-0">•</span>
                      <span className="text-slate-600 dark:text-slate-400">{point}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "conservative" && (
          <div className="space-y-4">
            {analysis.state_summary_fa ? (
              <>
                <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">
                  {analysis.state_summary_fa}
                </p>
                {analysis.scores?.state && (
                  <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                    <ScoreBar label="لحن" value={analysis.scores.state.tone} max={2} />
                    <ScoreBar label="واقع‌گرایی" value={analysis.scores.state.factuality} />
                    <ScoreBar label="ادبیات احساسی" value={analysis.scores.state.emotional_language} />
                    <FramingTags framing={analysis.scores.state.framing} />
                  </div>
                )}
              </>
            ) : (
              <p className="text-[13px] text-slate-400">پوششی از سوی رسانه‌های حکومتی یافت نشد</p>
            )}
          </div>
        )}

        {activeTab === "opposition" && (
          <div className="space-y-4">
            {analysis.diaspora_summary_fa ? (
              <>
                <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">
                  {analysis.diaspora_summary_fa}
                </p>
                {analysis.scores?.diaspora && (
                  <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                    <ScoreBar label="لحن" value={analysis.scores.diaspora.tone} max={2} />
                    <ScoreBar label="واقع‌گرایی" value={analysis.scores.diaspora.factuality} />
                    <ScoreBar label="ادبیات احساسی" value={analysis.scores.diaspora.emotional_language} />
                    <FramingTags framing={analysis.scores.diaspora.framing} />
                  </div>
                )}
              </>
            ) : (
              <p className="text-[13px] text-slate-400">پوششی از سوی رسانه‌های اپوزیسیون یافت نشد</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
