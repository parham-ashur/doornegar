"use client";

import { useLocale } from "next-intl";
import { ShieldCheck } from "lucide-react";

interface FactCheckBarometerProps {
  score: number | null; // 0-1, null = not yet assessed
  className?: string;
}

export default function FactCheckBarometer({ score, className }: FactCheckBarometerProps) {
  const locale = useLocale();

  const labels = [
    { min: 0, max: 0.2, en: "Misleading", fa: "گمراه‌کننده", color: "bg-red-500", textColor: "text-red-600" },
    { min: 0.2, max: 0.4, en: "Mostly False", fa: "عمدتاً نادرست", color: "bg-orange-500", textColor: "text-orange-600" },
    { min: 0.4, max: 0.6, en: "Mixed", fa: "ترکیبی", color: "bg-amber-500", textColor: "text-amber-600" },
    { min: 0.6, max: 0.8, en: "Mostly True", fa: "عمدتاً صحیح", color: "bg-lime-500", textColor: "text-lime-600" },
    { min: 0.8, max: 1.0, en: "Verified", fa: "تأیید شده", color: "bg-emerald-500", textColor: "text-emerald-600" },
  ];

  const notAssessed = score === null || score === undefined;

  const currentLabel = notAssessed
    ? null
    : labels.find((l) => score >= l.min && score <= l.max) || labels[2];

  return (
    <div className={className}>
      <div className="flex items-center gap-2 mb-2">
        <ShieldCheck className="h-4 w-4 text-slate-500" />
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">
          {locale === "fa" ? "سنجه واقعیت" : "Fact Check Barometer"}
        </span>
      </div>

      {/* Barometer segments */}
      <div className="flex h-4 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        {labels.map((label, i) => (
          <div
            key={i}
            className={`flex-1 transition-opacity ${label.color} ${
              notAssessed
                ? "opacity-20"
                : currentLabel === label
                ? "opacity-100"
                : "opacity-20"
            }`}
          />
        ))}
      </div>

      {/* Needle / indicator */}
      {!notAssessed && (
        <div className="relative h-0">
          <div
            className="absolute -top-5 h-3 w-0.5 bg-slate-900 dark:bg-white"
            style={{ left: `${score * 100}%`, transform: "translateX(-50%)" }}
          />
        </div>
      )}

      {/* Label */}
      <div className="mt-2 flex justify-between text-[9px] text-slate-400">
        {labels.map((label, i) => (
          <span key={i} className={notAssessed ? "" : currentLabel === label ? `font-bold ${label.textColor}` : ""}>
            {locale === "fa" ? label.fa : label.en}
          </span>
        ))}
      </div>

      {notAssessed && (
        <p className="mt-1 text-center text-[10px] italic text-slate-400">
          {locale === "fa" ? "هنوز ارزیابی نشده" : "Not yet assessed"}
        </p>
      )}
    </div>
  );
}
