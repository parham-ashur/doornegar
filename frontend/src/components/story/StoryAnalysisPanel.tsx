import type { StoryAnalysis } from "@/lib/types";

function SidePanel({ title, summary, scores, color }: {
  title: string;
  summary: string | null;
  scores: { tone: number | null; factuality: number | null; emotional_language: number | null; framing: string | string[] | null } | null;
  color: string;
}) {
  if (!summary) return null;
  return (
    <div className="border-t border-slate-200 dark:border-slate-800 pt-4 flex flex-col">
      <h4 className={`text-xs font-bold mb-2 ${color}`}>{title}</h4>
      {summary && (
        <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">{summary}</p>
      )}
      {scores?.framing && (
        <div className="mt-auto pt-3 flex items-center gap-1.5 flex-wrap text-[11px]">
          <span className="text-slate-500 dark:text-slate-400">چارچوب‌بندی:</span>
          {(Array.isArray(scores.framing) ? scores.framing : [scores.framing]).map((f, i) => (
            <span key={i} className="px-2 py-0.5 border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300">
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function StoryAnalysisPanel({ analysis }: { analysis: StoryAnalysis | null }) {
  if (!analysis) return null;

  const hasSummary = analysis.summary_fa;

  if (!hasSummary) return null;

  return (
    <div className="border-t border-b border-slate-200 dark:border-slate-800 py-6 space-y-5" dir="rtl">
      {/* Overall summary */}
      <div>
        <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">خلاصه</h3>
        <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.summary_fa}</p>
      </div>

      {/* Per-side summaries with scores */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SidePanel
          title="دیدگاه حکومتی"
          summary={analysis.state_summary_fa}
          scores={analysis.scores?.state || null}
          color="text-red-600 dark:text-red-400"
        />
        <SidePanel
          title="دیدگاه مستقل"
          summary={analysis.independent_summary_fa}
          scores={analysis.scores?.independent || null}
          color="text-emerald-600 dark:text-emerald-400"
        />
        <SidePanel
          title="دیدگاه برون‌مرزی"
          summary={analysis.diaspora_summary_fa}
          scores={analysis.scores?.diaspora || null}
          color="text-blue-600 dark:text-blue-400"
        />
      </div>

      {/* Bias comparison */}
      {analysis.bias_explanation_fa && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">مقایسه سوگیری</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.bias_explanation_fa}</p>
        </div>
      )}
    </div>
  );
}
