import { BarChart3, Brain } from "lucide-react";
// Analyst first, then stats
import type { StoryAnalysis } from "@/lib/types";

export default function StatsPanel({ analysis }: { analysis: StoryAnalysis | null }) {
  const stateFraming = analysis?.scores?.state?.framing;
  const diasporaFraming = analysis?.scores?.diaspora?.framing;
  const hasAnalyst = !!(analysis as any)?.analyst;
  const neutralityData = analysis?.source_neutrality;
  const neutralityValues = neutralityData ? Object.values(neutralityData) : [];
  const avgNeutrality = neutralityValues.length > 0
    ? neutralityValues.reduce((a, b) => a + b, 0) / neutralityValues.length
    : null;

  return (
    <div dir="rtl" className="space-y-5">
      {/* Analyst (top) */}
      <div>
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
            <p className="text-[11px] text-slate-400 mt-2">تحلیل عمیق پس از اجرای بعدی در دسترس خواهد بود</p>
          </div>
        )}
      </div>

      {/* Summary stats (below analyst) */}
      <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="h-4 w-4 text-slate-400" />
          <h4 className="text-[12px] font-bold text-slate-900 dark:text-white">آمار خلاصه</h4>
        </div>
        <div className="space-y-2 text-[11px]">
          {stateFraming && (
            <div className="flex items-center justify-between">
              <span className="text-slate-500">روایت محافظه‌کار</span>
              <span className="text-slate-700 dark:text-slate-300 font-medium">
                {(Array.isArray(stateFraming) ? stateFraming : [stateFraming]).join("، ")}
              </span>
            </div>
          )}
          {diasporaFraming && (
            <div className="flex items-center justify-between">
              <span className="text-slate-500">روایت اپوزیسیون</span>
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
                  <div key={slug} className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-400 truncate max-w-[60%]">{slug}</span>
                    <span className={`font-mono ${score > 0 ? "text-emerald-500" : score < -0.3 ? "text-red-400" : "text-slate-500"}`}>
                      {score > 0 ? "+" : ""}{score.toFixed(1)}
                    </span>
                  </div>
                ))}
            </div>
          )}
          {!stateFraming && !diasporaFraming && avgNeutrality === null && (
            <p className="text-[11px] text-slate-400">آمار پس از اجرای تحلیل در دسترس خواهد بود</p>
          )}
        </div>
      </div>
    </div>
  );
}
