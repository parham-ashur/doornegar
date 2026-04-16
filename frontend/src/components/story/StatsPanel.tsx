"use client";

import { BarChart3, MessageCircle, VolumeX, Radio, TrendingUp, Eye } from "lucide-react";
import { useState, useEffect } from "react";
import type { StoryAnalysis } from "@/lib/types";
import { toFa } from "@/lib/utils";
import StoryTelegramSection from "./StoryTelegramSection";

export default function StatsPanel({ analysis, storyId, articleCount, sourceCount, containerId = "telegram" }: { analysis: StoryAnalysis | null; storyId?: string; articleCount?: number; sourceCount?: number; containerId?: string }) {
  // Read URL params synchronously for initial state
  const isTelegramLink = typeof window !== "undefined" && window.location.hash === "#telegram";
  const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const initialTab = urlParams?.get("tg") || null;
  const highlightText = urlParams?.get("hl") ? decodeURIComponent(urlParams.get("hl")!) : null;

  const [showTelegram, setShowTelegram] = useState(isTelegramLink);

  useEffect(() => {
    if (isTelegramLink) {
      setShowTelegram(true);
      setTimeout(() => {
        document.getElementById(containerId)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 800);
    }
  }, [isTelegramLink, containerId]);

  const stateFraming = analysis?.scores?.state?.framing;
  const diasporaFraming = analysis?.scores?.diaspora?.framing;
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
    <div id={containerId} dir="rtl" className="space-y-5">
      {/* Telegram analysis — button to expand */}
      {storyId && !showTelegram && (
        <button
          onClick={() => setShowTelegram(true)}
          className="w-full group flex items-center gap-3 px-4 py-3 bg-gradient-to-l from-blue-50 to-white dark:from-blue-950/30 dark:to-slate-900 border border-blue-200 dark:border-blue-800 hover:border-blue-400 dark:hover:border-blue-600 transition-all"
        >
          <div className="shrink-0 w-8 h-8 rounded-full bg-[#2AABEE]/15 dark:bg-[#2AABEE]/20 flex items-center justify-center">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="#2AABEE"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
          </div>
          <div className="text-right flex-1">
            <p className="text-[13px] font-bold text-blue-700 dark:text-blue-300 group-hover:text-blue-900 dark:group-hover:text-blue-200 transition-colors">دیدن تحلیل تلگرام</p>
            <p className="text-[13px] text-slate-400 dark:text-slate-500">پیش‌بینی‌ها، ادعاها و تحلیل کانال‌ها</p>
          </div>
          <Eye className="h-4 w-4 text-blue-400 dark:text-blue-500 group-hover:text-blue-600 transition-colors shrink-0" />
        </button>
      )}
      {showTelegram && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="#2AABEE"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
              <h4 className="text-[14px] font-bold text-slate-900 dark:text-white">تحلیل روایت‌های تلگرام</h4>
            </div>
            <button onClick={() => setShowTelegram(false)} className="text-[13px] text-slate-400 hover:text-slate-600">بستن</button>
          </div>
          <StoryTelegramSection storyId={storyId!} initialTab={initialTab} highlightText={highlightText} />
        </div>
      )}

      {/* Delta — what's new */}
      {delta && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
            <h4 className="text-[14px] font-bold text-slate-900 dark:text-white">تغییرات جدید</h4>
          </div>
          <p className="text-[14px] leading-5 text-emerald-600 dark:text-emerald-400">{delta}</p>
        </div>
      )}

      {/* Narrative arc */}
      {narrativeArc?.evolution && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <h4 className="text-[14px] font-bold text-slate-900 dark:text-white mb-2">تحول روایت</h4>
          <p className="text-[14px] leading-5 text-slate-500 dark:text-slate-400">{narrativeArc.evolution}</p>
        </div>
      )}

      {/* Silence detection */}
      {silenceAnalysis && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <VolumeX className="h-3.5 w-3.5 text-amber-500" />
            <h4 className="text-[14px] font-bold text-slate-900 dark:text-white">سکوت رسانه‌ای</h4>
          </div>
          <p className="text-[14px] leading-5 text-amber-600 dark:text-amber-400">
            {typeof silenceAnalysis === "string"
              ? silenceAnalysis
              : silenceAnalysis.hypothesis_fa
                || `${silenceAnalysis.loud_count || 0} رسانهٔ ${silenceAnalysis.loud_side === "state" ? "محافظه‌کار" : "اپوزیسیون"} پوشش داده‌اند؛ رسانه‌های ${silenceAnalysis.silent_side === "state" ? "محافظه‌کار" : "اپوزیسیون"} سکوت کرده‌اند`}
          </p>
        </div>
      )}

      {/* Coordinated messaging */}
      {coordination && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <Radio className="h-3.5 w-3.5 text-red-500" />
            <h4 className="text-[14px] font-bold text-slate-900 dark:text-white">پیام هماهنگ</h4>
          </div>
          <p className="text-[14px] text-slate-500 dark:text-slate-400">
            {coordination.sources?.length || 0} رسانه {coordination.side === "state" ? "محافظه‌کار" : "اپوزیسیون"} پیام مشابه منتشر کردند
          </p>
          {coordination.sources && (
            <p className="text-[13px] text-slate-400 mt-1">{coordination.sources.join(" · ")}</p>
          )}
        </div>
      )}

      {/* Summary stats */}
      <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="h-4 w-4 text-slate-400" />
          <h4 className="text-[14px] font-bold text-slate-900 dark:text-white">آمار</h4>
        </div>

        <div className="space-y-3 text-[13px]">
          {/* Dispute score */}
          {analysis?.dispute_score != null && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-slate-500">میزان اختلاف روایت رسانه‌ها</span>
                <span className={`font-bold ${
                  analysis.dispute_score > 0.7 ? "text-red-500" :
                  analysis.dispute_score > 0.4 ? "text-amber-500" : "text-emerald-500"
                }`}>
                  {analysis.dispute_score > 0.7 ? "بسیار بالا" :
                   analysis.dispute_score > 0.4 ? "متوسط" : "پایین"}
                </span>
              </div>
              <div className="w-full h-1.5 bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    analysis.dispute_score > 0.7 ? "bg-red-500" :
                    analysis.dispute_score > 0.4 ? "bg-amber-500" : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.round(analysis.dispute_score * 100)}%` }}
                />
              </div>
            </div>
          )}

          {/* Article + source counts */}
          {(articleCount || sourceCount) && (
            <div className="flex items-center gap-4">
              {articleCount != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[14px] font-black text-slate-800 dark:text-slate-200">{toFa(articleCount)}</span>
                  <span className="text-slate-400">مقاله</span>
                </div>
              )}
              {sourceCount != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[14px] font-black text-slate-800 dark:text-slate-200">{toFa(sourceCount)}</span>
                  <span className="text-slate-400">رسانه</span>
                </div>
              )}
            </div>
          )}

          {/* Framing tags */}
          {(stateFraming || diasporaFraming) && (
            <div className="space-y-1.5">
              {stateFraming && (
                <div className="flex items-start gap-2">
                  <span className="shrink-0 w-1.5 h-1.5 mt-1.5 bg-[#1e3a5f] rounded-full" />
                  <span className="text-slate-500">
                    {(Array.isArray(stateFraming) ? stateFraming : [stateFraming]).join("، ")}
                  </span>
                </div>
              )}
              {diasporaFraming && (
                <div className="flex items-start gap-2">
                  <span className="shrink-0 w-1.5 h-1.5 mt-1.5 bg-[#ea580c] rounded-full" />
                  <span className="text-slate-500">
                    {(Array.isArray(diasporaFraming) ? diasporaFraming : [diasporaFraming]).join("، ")}
                  </span>
                </div>
              )}
            </div>
          )}

          {!stateFraming && !diasporaFraming && analysis?.dispute_score == null && (
            <p className="text-[13px] text-slate-400">آمار پس از اجرای تحلیل در دسترس خواهد بود</p>
          )}
        </div>
      </div>
    </div>
  );
}
