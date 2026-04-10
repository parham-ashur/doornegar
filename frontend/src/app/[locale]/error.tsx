"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-6 py-24 flex flex-col items-center text-center">
      <div className="text-[80px] leading-none select-none mb-4">
        <svg width="120" height="120" viewBox="0 0 120 120" className="mx-auto">
          {/* Scattered lines that never quite form — something went wrong */}
          <line x1="20" y1="30" x2="55" y2="45" stroke="#b07d62" strokeWidth="2" strokeLinecap="round" opacity="0.5">
            <animateTransform attributeName="transform" type="translate" values="0,0; 3,-2; 0,0" dur="4s" repeatCount="indefinite" />
          </line>
          <line x1="65" y1="25" x2="90" y2="50" stroke="#7a9e8e" strokeWidth="2" strokeLinecap="round" opacity="0.5">
            <animateTransform attributeName="transform" type="translate" values="0,0; -2,3; 0,0" dur="5s" repeatCount="indefinite" />
          </line>
          <line x1="40" y1="60" x2="75" y2="55" stroke="#8a9ab5" strokeWidth="2" strokeLinecap="round" opacity="0.5">
            <animateTransform attributeName="transform" type="translate" values="0,0; 2,2; 0,0" dur="3.5s" repeatCount="indefinite" />
          </line>
          <line x1="30" y1="80" x2="60" y2="90" stroke="#b07d62" strokeWidth="2" strokeLinecap="round" opacity="0.4">
            <animateTransform attributeName="transform" type="translate" values="0,0; -3,1; 0,0" dur="4.5s" repeatCount="indefinite" />
          </line>
          <line x1="70" y1="75" x2="95" y2="85" stroke="#7a9e8e" strokeWidth="2" strokeLinecap="round" opacity="0.4">
            <animateTransform attributeName="transform" type="translate" values="0,0; 1,-3; 0,0" dur="5.5s" repeatCount="indefinite" />
          </line>
        </svg>
      </div>
      <h1 className="text-xl font-black text-slate-900 dark:text-white">
        مشکلی پیش آمد
      </h1>
      <p className="mt-3 text-sm text-slate-500 dark:text-slate-400 max-w-md">
        خطوط هنوز به هم نرسیده‌اند — تصویر کامل نشد.
        دوباره تلاش کنید.
      </p>
      <button
        onClick={() => reset()}
        className="mt-8 px-5 py-2.5 text-sm font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200 transition-colors"
      >
        تلاش دوباره
      </button>
    </div>
  );
}
