"use client";

import { useState } from "react";
import type { Source } from "@/lib/types";

const DIMENSIONS: { key: string; label: string; description: string; low: string; high: string }[] = [
  { key: "editorial_independence", label: "استقلال تحریریه", description: "میزان آزادی تحریریه در انتخاب موضوع و زاویه پوشش، بدون دخالت دولت، نهاد نظامی یا مالک", low: "کاملاً تحت کنترل", high: "کاملاً مستقل" },
  { key: "funding_transparency", label: "شفافیت مالی", description: "شفافیت منابع مالی رسانه — آیا مشخص است چه کسی هزینه‌ها را تأمین می‌کند و آیا این وابستگی بر محتوا اثر می‌گذارد", low: "مبهم و پنهان", high: "شفاف و مشخص" },
  { key: "operational_constraint", label: "محدودیت عملیاتی", description: "محدودیت‌های فیزیکی و قانونی — سانسور، فیلترینگ، ممنوعیت فعالیت خبرنگاران، و فشار امنیتی بر تحریریه", low: "محدودیت شدید", high: "آزادی عمل کامل" },
  { key: "source_diversity", label: "تنوع منابع", description: "تنوع منابع خبری مورد استفاده — آیا فقط از منابع رسمی نقل می‌کند یا صداهای مختلف (مردم، کارشناسان، مخالفان) را هم پوشش می‌دهد", low: "فقط منابع رسمی", high: "صداهای متنوع" },
  { key: "viewpoint_pluralism", label: "تکثر دیدگاه", description: "آیا رسانه دیدگاه‌های مختلف سیاسی و اجتماعی را بازتاب می‌دهد یا فقط یک روایت را تقویت می‌کند", low: "تک‌صدا", high: "چندصدایی" },
  { key: "factional_capture", label: "تصرف جناحی", description: "میزان وابستگی رسانه به یک جناح سیاسی خاص — اصولگرا، اصلاح‌طلب، سپاه، یا گروه‌های برون‌مرزی", low: "وابسته به یک جناح", high: "فراجناحی" },
  { key: "audience_accountability", label: "پاسخگویی به مخاطب", description: "آیا رسانه مکانیزم بازخورد، تصحیح خطا، و پاسخگویی به مخاطبان دارد — یا یک‌جانبه پیام ارسال می‌کند", low: "بدون پاسخگویی", high: "پاسخگوی فعال" },
  { key: "crisis_behavior", label: "رفتار در بحران", description: "عملکرد رسانه در بحران‌ها (اعتراضات، سیل، جنگ) — آیا اطلاع‌رسانی می‌کند یا سانسور و تبلیغات پخش می‌کند", low: "سانسور و تبلیغات", high: "اطلاع‌رسانی صادقانه" },
];

const ALIGNMENT_COLORS: Record<string, { dot: string; text: string }> = {
  state: { dot: "bg-red-500", text: "text-red-600 dark:text-red-400" },
  semi_state: { dot: "bg-red-400", text: "text-red-500 dark:text-red-300" },
  independent: { dot: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400" },
  diaspora: { dot: "bg-blue-500", text: "text-blue-600 dark:text-blue-400" },
};

export default function DimensionPlot({ sources }: { sources: Source[] }) {
  const [activeDim, setActiveDim] = useState(DIMENSIONS[0].key);

  // Only sources with media_dimensions
  const scored = sources.filter((s) => s.media_dimensions);
  if (scored.length === 0) return null;

  // Group sources by their score on the active dimension
  const byScore: Record<number, Source[]> = { 1: [], 2: [], 3: [], 4: [], 5: [] };
  for (const s of scored) {
    const score = s.media_dimensions?.[activeDim];
    if (score && score >= 1 && score <= 5) {
      byScore[score].push(s);
    }
  }

  const activeDimObj = DIMENSIONS.find((d) => d.key === activeDim)!;

  return (
    <div>
      <h3 className="text-sm font-black text-slate-900 dark:text-white mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
        ابعاد رسانه‌ای
      </h3>

      {/* Dimension toggle buttons */}
      <div className="flex flex-wrap gap-1 mb-4">
        {DIMENSIONS.map((dim) => (
          <button
            key={dim.key}
            onClick={() => setActiveDim(dim.key)}
            className={`px-2 py-1 text-[10px] font-medium border transition-colors ${
              activeDim === dim.key
                ? "border-slate-900 dark:border-white text-slate-900 dark:text-white bg-slate-100 dark:bg-slate-800"
                : "border-slate-300 dark:border-slate-700 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            }`}
          >
            {dim.label}
          </button>
        ))}
      </div>

      {/* Active dimension description */}
      <div className="mb-4">
        <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300 mb-1">{activeDimObj.label}</p>
        <p className="text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
          {activeDimObj.description}
        </p>
      </div>

      {/* Scale endpoints */}
      <div className="flex items-center justify-between mb-2 px-5">
        <span className="text-[9px] text-slate-400 dark:text-slate-500">۵ = {activeDimObj.high}</span>
        <span className="text-[9px] text-slate-400 dark:text-slate-500">۱ = {activeDimObj.low}</span>
      </div>

      {/* Dot plot — horizontal rows per score */}
      <div className="relative space-y-0">
        {[5, 4, 3, 2, 1].map((score) => (
          <div key={score} className="flex items-start gap-2 py-1.5 border-b border-slate-100 dark:border-slate-800/50 last:border-0">
            <span className="text-[10px] text-slate-400 dark:text-slate-500 w-3 shrink-0 text-center pt-0.5">
              {"۱۲۳۴۵"[score - 1]}
            </span>
            <div className="flex flex-wrap gap-x-3 gap-y-1 min-h-[18px]">
              {byScore[score].map((s) => {
                const colors = ALIGNMENT_COLORS[s.state_alignment] || ALIGNMENT_COLORS.independent;
                return (
                  <div key={s.slug} className="flex items-center gap-1">
                    <div className={`w-2 h-2 shrink-0 ${colors.dot}`} />
                    <span className={`text-[10px] leading-tight whitespace-nowrap ${colors.text}`}>
                      {s.name_fa}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/50">
        <span className="flex items-center gap-1 text-[9px] text-red-500">
          <span className="inline-block w-1.5 h-1.5 bg-red-500" /> درون‌مرزی
        </span>
        <span className="flex items-center gap-1 text-[9px] text-emerald-500">
          <span className="inline-block w-1.5 h-1.5 bg-emerald-500" /> مستقل
        </span>
        <span className="flex items-center gap-1 text-[9px] text-blue-500">
          <span className="inline-block w-1.5 h-1.5 bg-blue-500" /> برون‌مرزی
        </span>
      </div>
    </div>
  );
}
