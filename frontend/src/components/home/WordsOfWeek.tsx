"use client";

import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FALLBACK_CONSERVATIVE = [
  { word: "پیروزی بزرگ", count: 12 },
  { word: "مقاومت", count: 9 },
  { word: "شهید", count: 7 },
  { word: "بازدارندگی", count: 6 },
  { word: "شروط ده‌گانه", count: 5 },
];

const FALLBACK_OPPOSITION = [
  { word: "شکست دیپلماتیک", count: 14 },
  { word: "سرکوب", count: 11 },
  { word: "تلفات غیرنظامی", count: 8 },
  { word: "آتش‌بس شکننده", count: 6 },
  { word: "بحران انسانی", count: 5 },
];

export default function WordsOfWeek({ prefetchedData }: { prefetchedData?: { conservative?: any[]; opposition?: any[] } | null }) {
  const [conservativeWords, setConservativeWords] = useState(() =>
    prefetchedData?.conservative?.length ? prefetchedData.conservative : FALLBACK_CONSERVATIVE
  );
  const [oppositionWords, setOppositionWords] = useState(() =>
    prefetchedData?.opposition?.length ? prefetchedData.opposition : FALLBACK_OPPOSITION
  );
  const [loading, setLoading] = useState(!prefetchedData);

  useEffect(() => {
    if (prefetchedData) return;
    let cancelled = false;
    async function fetchWords() {
      try {
        const res = await fetch(`${API}/api/v1/stories/insights/loaded-words`);
        if (!res.ok) throw new Error("API error");
        const data = await res.json();
        if (cancelled) return;
        if (data.conservative?.length) setConservativeWords(data.conservative);
        if (data.opposition?.length) setOppositionWords(data.opposition);
      } catch {
        // keep fallback data
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchWords();
    return () => { cancelled = true; };
  }, [prefetchedData]);

  const clean = (w: string) => w.replace(/[«»]/g, "");
  const pairs = Math.min(conservativeWords.length, oppositionWords.length, 5);

  return (
    <div dir="rtl">
      <h4 className="text-[14px] font-black text-slate-900 dark:text-white mb-3">واژه‌های روز</h4>

      <div className={`transition-all duration-300 ${loading ? "opacity-50 animate-pulse" : "opacity-100"}`}>
        {/* Column headers */}
        <div className="flex items-center justify-between mb-2 pb-2 border-b border-slate-200 dark:border-slate-700">
          <span className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300">درون‌مرزی</span>
          <span className="text-[13px] font-bold text-[#ea580c] dark:text-orange-400">برون‌مرزی</span>
        </div>

        {/* Contrast pairs */}
        <div className="space-y-1.5">
          {Array.from({ length: pairs }).map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="flex-1 text-[13px] text-[#1e3a5f] dark:text-blue-300 font-medium truncate">
                «{clean(conservativeWords[i].word)}»
              </span>
              <span className="text-slate-200 dark:text-slate-700 shrink-0 mx-1">·</span>
              <span className="flex-1 text-[13px] text-[#ea580c] dark:text-orange-400 font-medium truncate text-left">
                «{clean(oppositionWords[i].word)}»
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
