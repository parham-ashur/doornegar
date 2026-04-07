"use client";

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a0e1a]" dir="rtl">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <p className="text-base font-black text-slate-900 dark:text-white">
            دورنگر
          </p>
          <p className="max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-500">
            پلتفرم شفافیت رسانه‌ای ایران — مقایسه پوشش خبری رسانه‌های داخل و خارج ایران.
            ببینید کدام رسانه چه خبری را پوشش داده و چه خبری را پنهان کرده.
          </p>
          <div className="flex items-center gap-4 text-[11px] text-slate-400 dark:text-slate-600">
            <span>متن‌باز</span>
            <span>·</span>
            <span>همیشه رایگان</span>
            <span>·</span>
            <span>ساخته‌شده برای شفافیت</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
