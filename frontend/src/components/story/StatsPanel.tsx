import { BarChart3, Brain, VolumeX, Radio, TrendingUp } from "lucide-react";
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

  const silenceAnalysis = (analysis as any)?.silence_analysis;
  const coordination = (analysis as any)?.coordinated_messaging;
  const narrativeArc = (analysis as any)?.narrative_arc;
  const delta = (analysis as any)?.delta;

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

      {/* Delta — what's new */}
      {delta && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
            <h4 className="text-[12px] font-bold text-slate-900 dark:text-white">تغییرات جدید</h4>
          </div>
          <p className="text-[12px] leading-5 text-emerald-600 dark:text-emerald-400">{delta}</p>
        </div>
      )}

      {/* Narrative arc */}
      {narrativeArc?.evolution && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <h4 className="text-[12px] font-bold text-slate-900 dark:text-white mb-2">تحول روایت</h4>
          <p className="text-[12px] leading-5 text-slate-500 dark:text-slate-400">{narrativeArc.evolution}</p>
          {narrativeArc.vocabulary_shift?.length >= 2 && (
            <p className="text-[11px] text-slate-400 mt-1">
              <span className="line-through text-slate-300">{narrativeArc.vocabulary_shift[0]}</span>
              {" → "}
              <span className="font-medium text-slate-700 dark:text-slate-300">{narrativeArc.vocabulary_shift[1]}</span>
            </p>
          )}
          {narrativeArc.direction && (
            <span className={`inline-block mt-1 text-[10px] px-2 py-0.5 border ${
              narrativeArc.direction === "escalating" ? "text-red-500 border-red-300 dark:border-red-800" :
              narrativeArc.direction === "de-escalating" ? "text-emerald-500 border-emerald-300 dark:border-emerald-800" :
              "text-slate-500 border-slate-300 dark:border-slate-700"
            }`}>
              {narrativeArc.direction === "escalating" ? "تشدید ↑" :
               narrativeArc.direction === "de-escalating" ? "کاهش ↓" :
               narrativeArc.direction === "shifting" ? "تغییر ↔" : "پایدار —"}
            </span>
          )}
        </div>
      )}

      {/* Silence detection */}
      {silenceAnalysis && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <VolumeX className="h-3.5 w-3.5 text-amber-500" />
            <h4 className="text-[12px] font-bold text-slate-900 dark:text-white">سکوت رسانه‌ای</h4>
          </div>
          <p className="text-[12px] leading-5 text-amber-600 dark:text-amber-400">{silenceAnalysis}</p>
        </div>
      )}

      {/* Coordinated messaging */}
      {coordination && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <Radio className="h-3.5 w-3.5 text-red-500" />
            <h4 className="text-[12px] font-bold text-slate-900 dark:text-white">پیام هماهنگ</h4>
          </div>
          <p className="text-[12px] text-slate-500 dark:text-slate-400">
            {coordination.sources?.length || 0} رسانه {coordination.side === "state" ? "محافظه‌کار" : "اپوزیسیون"} پیام مشابه منتشر کردند
          </p>
          {coordination.sources && (
            <p className="text-[11px] text-slate-400 mt-1">{coordination.sources.join(" · ")}</p>
          )}
        </div>
      )}

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
