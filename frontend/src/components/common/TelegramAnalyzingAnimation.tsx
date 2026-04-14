"use client";

import { useState, useEffect } from "react";
import { Check } from "lucide-react";

/**
 * Analyzing animation with 3 progress lines that complete sequentially,
 * each showing a checkmark when done.
 * @param durationMs - total animation duration before onComplete fires
 */
export default function TelegramAnalyzingAnimation({
  durationMs = 1000,
  onComplete,
}: {
  durationMs?: number;
  onComplete?: () => void;
}) {
  const [completedLines, setCompletedLines] = useState(0);
  const [dots, setDots] = useState("");

  const lineDelay = Math.floor(durationMs / 3);

  useEffect(() => {
    const interval = setInterval(() => setDots(d => d.length >= 3 ? "" : d + "."), 300);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const t1 = setTimeout(() => setCompletedLines(1), lineDelay);
    const t2 = setTimeout(() => setCompletedLines(2), lineDelay * 2);
    const t3 = setTimeout(() => {
      setCompletedLines(3);
      // Immediately reveal after last checkmark
      setTimeout(() => onComplete?.(), 50);
    }, lineDelay * 3);

    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [lineDelay, onComplete]);

  const lines = [
    { label: "جمع‌آوری پست‌ها", width: "75%" },
    { label: "تحلیل روایت‌ها", width: "55%" },
    { label: "استخراج بینش", width: "85%" },
  ];

  return (
    <div className="space-y-3 py-1">
      <div className="flex items-center gap-2">
        {completedLines < 3 ? (
          <svg className="animate-spin h-3.5 w-3.5 text-blue-500 shrink-0" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <Check className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
        )}
        <span className="text-[13px] text-blue-600 dark:text-blue-400 font-medium">
          {completedLines < 3 ? `در حال تحلیل پست‌های تلگرامی${dots}` : "تحلیل آماده است"}
        </span>
      </div>
      <div className="space-y-2">
        {lines.map((line, i) => {
          const done = completedLines > i;
          return (
            <div key={i} className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div
                  className={`h-full transition-all ${done ? "bg-emerald-300 dark:bg-emerald-700" : "bg-blue-200 dark:bg-blue-900/50 animate-[shimmer_1.5s_ease-in-out_infinite]"}`}
                  style={{ width: done ? "100%" : line.width, transitionDuration: `${lineDelay * 0.6}ms` }}
                />
              </div>
              {done ? (
                <Check className="h-3 w-3 text-emerald-500 shrink-0" />
              ) : (
                <div className="w-3 h-3 shrink-0" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
