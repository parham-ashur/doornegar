"use client";

import { BarChart3, MessageCircle, VolumeX, Radio, TrendingUp, Eye, Info } from "lucide-react";
import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import type { StoryAnalysis } from "@/lib/types";
import { toFa } from "@/lib/utils";
import StoryTelegramSection from "./StoryTelegramSection";

export default function StatsPanel({
  analysis,
  storyId,
  articleCount,
  sourceCount,
  containerId = "telegram",
  initialTab: initialTabProp = null,
  highlightText: highlightTextProp = null,
}: {
  analysis: StoryAnalysis | null;
  storyId?: string;
  articleCount?: number;
  sourceCount?: number;
  containerId?: string;
  initialTab?: string | null;
  highlightText?: string | null;
}) {
  // Read tg/hl from the URL client-side so the enclosing page can stay
  // static-cacheable (the story page's server component no longer has
  // to accept searchParams, which would otherwise force dynamic mode).
  // Prop values still win if a caller (e.g. the rate page) passes them
  // explicitly — that keeps existing usages unchanged.
  const searchParams = useSearchParams();
  const initialTab = initialTabProp ?? searchParams?.get("tg") ?? null;
  const highlightText = highlightTextProp ?? searchParams?.get("hl") ?? null;

  const hasTelegramIntent = !!(initialTab || highlightText);
  const [showTelegram, setShowTelegram] = useState(hasTelegramIntent);

  useEffect(() => {
    if (hasTelegramIntent) {
      setShowTelegram(true);
      return;
    }
    if (typeof window !== "undefined" && window.location.hash === "#telegram") {
      setShowTelegram(true);
    }
  }, [hasTelegramIntent]);

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
            <p className="text-[15px] font-bold text-blue-700 dark:text-blue-300 group-hover:text-blue-900 dark:group-hover:text-blue-200 transition-colors">دیدن تحلیل تلگرام</p>
            <p className="text-[15px] text-slate-400 dark:text-slate-500">پیش‌بینی‌ها، ادعاها و تحلیل کانال‌ها</p>
          </div>
          <Eye className="h-4 w-4 text-blue-400 dark:text-blue-500 group-hover:text-blue-600 transition-colors shrink-0" />
        </button>
      )}
      {showTelegram && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="#2AABEE"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
              <h4 className="text-[15px] font-bold text-slate-900 dark:text-white">تحلیل روایت‌های تلگرام</h4>
            </div>
            <button onClick={() => setShowTelegram(false)} className="text-[15px] text-slate-400 hover:text-slate-600">بستن</button>
          </div>
          <StoryTelegramSection storyId={storyId!} initialTab={initialTab} highlightText={highlightText} scrollTargetId={containerId} />
        </div>
      )}

      {/* Delta — what's new */}
      {delta && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
            <h4 className="text-[15px] font-bold text-slate-900 dark:text-white">تغییرات جدید</h4>
          </div>
          <p className="text-[15px] leading-6 text-emerald-600 dark:text-emerald-400">{delta}</p>
        </div>
      )}

      {/* Narrative arc */}
      {narrativeArc?.evolution && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <h4 className="text-[15px] font-bold text-slate-900 dark:text-white mb-2">تحول روایت</h4>
          <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400">{narrativeArc.evolution}</p>
        </div>
      )}

      {/* Silence detection. Fires when ≥3 articles cover the story from
          one side AND exactly 0 from the other — a one-sided-coverage
          alert that's editorially load-bearing. */}
      {silenceAnalysis && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <VolumeX className="h-3.5 w-3.5 text-amber-500" />
            <h4 className="flex items-center gap-1 text-[15px] font-bold text-slate-900 dark:text-white">
              سکوت رسانه‌ای
              <span
                className="inline-flex items-center cursor-help text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                title={
                  "این نشانه زمانی فعال می‌شود که دست‌کم سه رسانه از یک سو خبر را پوشش داده‌اند و هیچ رسانه‌ای از سوی مقابل اشاره‌ای به آن نکرده است. " +
                  "هدف این است که نبودن پوشش به اندازهٔ بودن آن اهمیت دارد؛ خواننده ببیند چه خبری از نظر یک سو اصلاً وجود نداشته است."
                }
                aria-label="توضیح سکوت رسانه‌ای"
              >
                <Info className="h-3 w-3" />
              </span>
            </h4>
          </div>
          <p className="text-[15px] leading-6 text-amber-600 dark:text-amber-400">
            {typeof silenceAnalysis === "string"
              ? silenceAnalysis
              : silenceAnalysis.hypothesis_fa
                || `${silenceAnalysis.loud_count || 0} رسانهٔ ${silenceAnalysis.loud_side === "state" ? "درون‌مرزی" : "برون‌مرزی"} پوشش داده‌اند؛ رسانه‌های ${silenceAnalysis.silent_side === "state" ? "درون‌مرزی" : "برون‌مرزی"} سکوت کرده‌اند`}
          </p>
        </div>
      )}

      {/* Coordinated messaging. Fires when ≥3 sources in the same bundle
          publish within 6 hours of each other with embedding cosine > 0.85
          — i.e. near-identical phrasing clustered in time, a common
          astroturf / talking-point signal. */}
      {coordination && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <Radio className="h-3.5 w-3.5 text-red-500" />
            <h4 className="flex items-center gap-1 text-[15px] font-bold text-slate-900 dark:text-white">
              پیام هماهنگ
              <span
                className="inline-flex items-center cursor-help text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                title={
                  "این نشانه زمانی فعال می‌شود که دست‌کم سه رسانه از یک سو، در فاصلهٔ کمتر از شش ساعت، متن‌هایی با شباهت بسیار بالا منتشر کنند. " +
                  "چنین الگویی معمولاً نشانهٔ پیام‌رسانی هماهنگ یا خط رسانه‌ای مشترک است و به خواننده کمک می‌کند محتوا را با احتیاط بیشتری بخواند."
                }
                aria-label="توضیح پیام هماهنگ"
              >
                <Info className="h-3 w-3" />
              </span>
            </h4>
          </div>
          <p className="text-[15px] text-slate-500 dark:text-slate-400">
            {coordination.sources?.length || 0} رسانه {coordination.side === "state" ? "درون‌مرزی" : "برون‌مرزی"} پیام مشابه منتشر کردند
          </p>
          {coordination.sources && (
            <p className="text-[15px] text-slate-400 mt-1">{coordination.sources.join(" · ")}</p>
          )}
        </div>
      )}

      {/* Summary stats */}
      <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="h-4 w-4 text-slate-400" />
          <h4 className="text-[15px] font-bold text-slate-900 dark:text-white">آمار</h4>
        </div>

        <div className="space-y-3 text-[15px]">
          {/* Dispute score. The score is LLM-generated (not a deterministic
              formula); the tooltip lets a curious reader see the three
              reference points the model anchors on. */}
          {analysis?.dispute_score != null && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="flex items-center gap-1 text-slate-500">
                  میزان اختلاف روایت رسانه‌ها
                  <span
                    className="inline-flex items-center cursor-help text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                    title={
                      "این امتیاز توسط مدل زبانی محاسبه می‌شود، با سه نقطهٔ مرجع:\n" +
                      "۰.۰ — دو طرف بر سر واقعیت‌ها توافق دارند (فقط لحن فرق می‌کند)\n" +
                      "۰.۵ — اختلاف قابل‌توجه در چارچوب‌بندی و واقعیت‌های گزارش‌شده\n" +
                      "۱.۰ — تناقض کامل؛ ادعاها و واقعیت‌های متضاد\n\n" +
                      "مدل متن مقاله‌ها را از هر دو سو می‌خواند و بر اساس این معیارها یک عدد بر می‌گرداند."
                    }
                    aria-label="توضیح محاسبهٔ امتیاز"
                  >
                    <Info className="h-3 w-3" />
                  </span>
                </span>
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
                  <span className="text-[15px] font-black text-slate-800 dark:text-slate-200">{toFa(articleCount)}</span>
                  <span className="text-slate-400">مقاله</span>
                </div>
              )}
              {sourceCount != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[15px] font-black text-slate-800 dark:text-slate-200">{toFa(sourceCount)}</span>
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
            <p className="text-[15px] text-slate-400">آمار پس از اجرای تحلیل در دسترس خواهد بود</p>
          )}
        </div>
      </div>
    </div>
  );
}
