"use client";

import { useEffect, useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import type { StoryAnalysis } from "@/lib/types";

const framingLabels: Record<string, string> = {
  "مقاومت": "مقاومت",
  "پیروزی": "پیروزی",
  "قربانی": "قربانی",
  "تهدید": "تهدید",
  "بحران": "بحران",
  "خنثی": "خنثی",
};

function ScoreBar({ label, value, max, color }: { label: string; value: number | null; max: number; color: string }) {
  if (value === null || value === undefined) return null;
  const pct = Math.max(0, Math.min(100, ((value + (max === 4 ? 2 : 0)) / max) * 100));
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-20 text-slate-500 dark:text-slate-400">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-200 dark:bg-slate-800">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-6 text-left text-slate-600 dark:text-slate-300 font-medium">{value}</span>
    </div>
  );
}

function SidePanel({ title, summary, scores, color }: {
  title: string;
  summary: string | null;
  scores: { tone: number | null; factuality: number | null; emotional_language: number | null; framing: string | null } | null;
  color: string;
}) {
  if (!summary && !scores) return null;
  return (
    <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
      <h4 className={`text-xs font-bold mb-2 ${color}`}>{title}</h4>
      {summary && (
        <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400 mb-3">{summary}</p>
      )}
      {scores && (
        <div className="space-y-1.5">
          <ScoreBar label="لحن" value={scores.tone} max={4} color="bg-amber-500" />
          <ScoreBar label="مستندسازی" value={scores.factuality} max={5} color="bg-emerald-500" />
          <ScoreBar label="احساسی‌بودن" value={scores.emotional_language} max={5} color="bg-red-400" />
          {scores.framing && (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="w-20 text-slate-500 dark:text-slate-400">چارچوب</span>
              <span className="px-2 py-0.5 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-medium">
                {scores.framing}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function StoryAnalysisPanel({ storyId }: { storyId: string }) {
  const [analysis, setAnalysis] = useState<StoryAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [generating, setGenerating] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    fetch(`${apiBase}/api/v1/stories/${storyId}/analysis`)
      .then((res) => { if (!res.ok) throw new Error("failed"); return res.json(); })
      .then((data: StoryAnalysis) => { setAnalysis(data); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [storyId, apiBase]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/stories/${storyId}/summarize`, { method: "POST" });
      if (!res.ok) throw new Error("failed");
      const data = await res.json();
      setAnalysis(data);
    } catch { /* user can retry */ }
    finally { setGenerating(false); }
  };

  if (loading) {
    return (
      <div className="border-t border-b border-slate-200 dark:border-slate-800 py-6 space-y-3">
        <div className="h-4 w-24 bg-slate-200 dark:bg-slate-700 animate-pulse" />
        <div className="h-3 w-full bg-slate-100 dark:bg-slate-800 animate-pulse" />
        <div className="h-3 w-5/6 bg-slate-100 dark:bg-slate-800 animate-pulse" />
        <div className="h-3 w-4/6 bg-slate-100 dark:bg-slate-800 animate-pulse" />
      </div>
    );
  }

  if (error) return null;

  const hasSummary = analysis?.summary_fa;

  return (
    <div className="border-t border-b border-slate-200 dark:border-slate-800 py-6 space-y-5" dir="rtl">
      {/* Overall summary */}
      {hasSummary ? (
        <div>
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">خلاصه</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis!.summary_fa}</p>
        </div>
      ) : (
        <div>
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">خلاصه</h3>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-600 transition-colors disabled:opacity-50"
          >
            {generating ? (
              <><Loader2 className="h-4 w-4 animate-spin" />در حال تحلیل...</>
            ) : (
              <><Sparkles className="h-4 w-4" />تولید تحلیل</>
            )}
          </button>
        </div>
      )}

      {/* Per-side summaries with scores */}
      {hasSummary && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SidePanel
            title="دیدگاه حکومتی"
            summary={analysis!.state_summary_fa}
            scores={analysis!.scores?.state || null}
            color="text-red-600 dark:text-red-400"
          />
          <SidePanel
            title="دیدگاه مستقل"
            summary={analysis!.independent_summary_fa}
            scores={analysis!.scores?.independent || null}
            color="text-emerald-600 dark:text-emerald-400"
          />
          <SidePanel
            title="دیدگاه برون‌مرزی"
            summary={analysis!.diaspora_summary_fa}
            scores={analysis!.scores?.diaspora || null}
            color="text-blue-600 dark:text-blue-400"
          />
        </div>
      )}

      {/* Bias comparison */}
      {analysis?.bias_explanation_fa && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">مقایسه سوگیری</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.bias_explanation_fa}</p>
        </div>
      )}
    </div>
  );
}
