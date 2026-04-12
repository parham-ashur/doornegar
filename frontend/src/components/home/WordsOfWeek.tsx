"use client";

import { useState, useEffect } from "react";

const CONSERVATIVE_WORDS = [
  { word: "پیروزی بزرگ", count: 12 },
  { word: "محور مقاومت", count: 9 },
  { word: "تسلیم دشمن", count: 7 },
  { word: "بازدارندگی", count: 6 },
  { word: "شهدای مدافع", count: 5 },
];

const OPPOSITION_WORDS = [
  { word: "آتش‌بس شکننده", count: 14 },
  { word: "قطع اینترنت", count: 11 },
  { word: "تلفات غیرنظامی", count: 8 },
  { word: "سرکوب معترضان", count: 6 },
  { word: "بحران انسانی", count: 5 },
];

export default function WordsOfWeek() {
  const [showConservative, setShowConservative] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => setShowConservative(prev => !prev), 5000);
    return () => clearInterval(interval);
  }, []);

  const words = showConservative ? CONSERVATIVE_WORDS : OPPOSITION_WORDS;
  const color = showConservative ? "#3b82f6" : "#ea580c";
  const darkColor = showConservative ? "text-blue-300" : "text-orange-400";
  const label = showConservative ? "محافظه‌کار" : "اپوزیسیون";
  const maxCount = Math.max(...words.map(w => w.count));

  return (
    <div dir="rtl">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-[12px] font-black text-slate-900 dark:text-white">واژه‌های هفته</h4>
        <div className="flex gap-1">
          <button
            onClick={() => setShowConservative(true)}
            className={`w-2 h-2 rounded-full transition-colors ${showConservative ? "bg-[#1e3a5f] dark:bg-blue-400" : "bg-slate-300 dark:bg-slate-600"}`}
          />
          <button
            onClick={() => setShowConservative(false)}
            className={`w-2 h-2 rounded-full transition-colors ${!showConservative ? "bg-[#ea580c] dark:bg-orange-400" : "bg-slate-300 dark:bg-slate-600"}`}
          />
        </div>
      </div>

      <p className={`text-[11px] font-medium mb-2 ${showConservative ? "text-[#1e3a5f] dark:" + darkColor : "text-[#ea580c] dark:" + darkColor}`}
        style={{ color }}>
        {label}
      </p>

      <div className="space-y-1.5 transition-all duration-300">
        {words.map(w => (
          <div key={w.word} className="flex items-center gap-2">
            <span className="text-[12px] font-medium text-slate-700 dark:text-slate-300 shrink-0">«{w.word}»</span>
            <div className="flex-1 h-1 bg-slate-100 dark:bg-slate-800 overflow-hidden">
              <div className="h-full transition-all duration-500" style={{ width: `${(w.count / maxCount) * 100}%`, backgroundColor: color }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
