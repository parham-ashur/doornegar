/**
 * Homepage loading skeleton.
 *
 * Next.js App Router auto-wraps `page.tsx` in <Suspense> when a
 * `loading.tsx` lives next to it. This file is served as the Suspense
 * fallback — shown to users immediately on navigation or cold SSR while
 * the page awaits its ~15 parallel data fetches (600-1200ms typical).
 *
 * Structure mirrors the real homepage grid so the content swap-in is
 * visually stable — no layout jump when the page arrives. The old
 * loading.tsx had a charming animated-lines header but a generic
 * 4-column grid below; visitors saw "something" but the transition to
 * the homepage caused every element to shift. Matching layout reduces
 * that jank to near-zero.
 *
 * No client JS, no data fetch — static Tailwind with subtle
 * animate-pulse and the original SVG animation preserved.
 */

export default function Loading() {
  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-0 md:px-6 lg:px-8">
      {/* Branded header: animated lines forming a shape — keeps the
          existing "در حال شکل‌گیری تصویر" affordance while the grid
          below teases the real homepage structure. */}
      <div className="flex flex-col items-center py-6">
        <svg width="56" height="56" viewBox="0 0 80 80">
          <line x1="10" y1="15" x2="40" y2="25" stroke="#b07d62" strokeWidth="1.5" strokeLinecap="round" opacity="0.6">
            <animate attributeName="x1" values="5;15;5" dur="3s" repeatCount="indefinite" />
            <animate attributeName="y1" values="10;20;10" dur="4s" repeatCount="indefinite" />
          </line>
          <line x1="40" y1="25" x2="70" y2="15" stroke="#7a9e8e" strokeWidth="1.5" strokeLinecap="round" opacity="0.6">
            <animate attributeName="x2" values="65;75;65" dur="3.5s" repeatCount="indefinite" />
            <animate attributeName="y2" values="10;20;10" dur="4.5s" repeatCount="indefinite" />
          </line>
          <line x1="25" y1="45" x2="55" y2="45" stroke="#8a9ab5" strokeWidth="1.5" strokeLinecap="round" opacity="0.5">
            <animate attributeName="y1" values="42;48;42" dur="3s" repeatCount="indefinite" />
            <animate attributeName="y2" values="48;42;48" dur="3s" repeatCount="indefinite" />
          </line>
          <line x1="20" y1="60" x2="40" y2="70" stroke="#b07d62" strokeWidth="1.5" strokeLinecap="round" opacity="0.4">
            <animate attributeName="x1" values="18;22;18" dur="4s" repeatCount="indefinite" />
          </line>
          <line x1="40" y1="70" x2="60" y2="60" stroke="#7a9e8e" strokeWidth="1.5" strokeLinecap="round" opacity="0.4">
            <animate attributeName="x2" values="58;62;58" dur="4s" repeatCount="indefinite" />
          </line>
        </svg>
        <p className="text-xs text-slate-400 dark:text-slate-500 mt-2">در حال شکل‌گیری تصویر...</p>
      </div>

      <div className="animate-pulse">
        {/* Row 1 — hero image + title + right column stack */}
        <div className="grid grid-cols-12 gap-0 border-b-2 border-slate-300 dark:border-slate-700">
          <div className="hidden lg:block col-span-1" />

          {/* Hero card */}
          <div className="col-span-12 lg:col-span-6 py-6 px-5">
            <SkelBox className="aspect-[16/9] w-full" />
            <SkelLine className="mt-4 h-7 w-11/12" />
            <SkelLine className="mt-2 h-7 w-4/5" />
            <SkelLine className="mt-4 h-4 w-1/2" />
            <div className="mt-5 grid grid-cols-2 gap-3">
              <SkelBlock className="h-16" />
              <SkelBlock className="h-16" />
            </div>
          </div>

          {/* Right column: 4 stacked text cards */}
          <div className="hidden lg:flex col-span-5 pl-6 py-6 flex-col gap-4 border-r border-slate-200 dark:border-slate-800">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="border-b border-slate-100 dark:border-slate-800/60 pb-4 last:border-0">
                <SkelLine className="h-5 w-11/12 mb-2" />
                <SkelLine className="h-5 w-4/5" />
                <SkelLine className="h-3 w-1/3 mt-3" />
              </div>
            ))}
          </div>
        </div>

        {/* Row 2 — blindspots + right column boxes */}
        <div className="grid grid-cols-12 gap-0 py-8 border-b border-slate-200 dark:border-slate-800">
          <div className="col-span-12 lg:col-span-7 pl-6 px-4 lg:px-0">
            <SkelLine className="h-5 w-40 mb-5" />
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i}>
                  <SkelBox className="aspect-[16/9] w-full" />
                  <SkelLine className="mt-2 h-5 w-11/12" />
                  <SkelLine className="mt-2 h-3 w-1/2" />
                </div>
              ))}
            </div>
          </div>
          <div className="hidden lg:flex col-span-5 pr-6 flex-col gap-4">
            {/* تقابل روایت‌ها */}
            <div className="relative flex-1 min-h-0 border border-slate-300 dark:border-slate-600 p-5 pt-8">
              <SkelLine className="h-5 w-11/12 mb-3" />
              <div className="grid grid-cols-2 gap-0 mb-4">
                <SkelBlock className="h-14" />
                <SkelBlock className="h-14" />
              </div>
              <SkelLine className="h-3 w-full mb-2" />
              <SkelLine className="h-3 w-11/12 mb-4" />
              <SkelLine className="h-5 w-10/12 mt-6 mb-3" />
              <div className="grid grid-cols-2 gap-0 mb-4">
                <SkelBlock className="h-14" />
                <SkelBlock className="h-14" />
              </div>
              <SkelLine className="h-3 w-full mb-2" />
              <SkelLine className="h-3 w-10/12" />
            </div>
            {/* بیشترین اختلاف نگاه */}
            <div className="relative flex-1 min-h-0 border border-slate-300 dark:border-slate-600 p-5 pt-8">
              <SkelLine className="h-5 w-10/12 mb-3" />
              <SkelLine className="h-3 w-full mb-1" />
              <SkelLine className="h-3 w-11/12 mb-1" />
              <SkelLine className="h-3 w-9/12 mb-4" />
              <SkelLine className="h-5 w-11/12 mb-3" />
              <SkelLine className="h-3 w-full mb-1" />
              <SkelLine className="h-3 w-10/12" />
            </div>
          </div>
        </div>

        {/* Row 3 — most visited strip */}
        <div className="py-10 px-8 md:px-14 border-b border-slate-200 dark:border-slate-800">
          <SkelLine className="h-5 w-32 mb-6 mx-auto" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i}>
                <SkelBox className="aspect-[16/9] w-full" />
                <SkelLine className="mt-2 h-4 w-11/12" />
                <SkelLine className="mt-1 h-4 w-3/4" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SkelLine({ className = "" }: { className?: string }) {
  return <div className={`bg-slate-200 dark:bg-slate-800 ${className}`} />;
}

function SkelBox({ className = "" }: { className?: string }) {
  return <div className={`bg-slate-200 dark:bg-slate-800 ${className}`} />;
}

function SkelBlock({ className = "" }: { className?: string }) {
  return <div className={`bg-slate-100 dark:bg-slate-800/60 ${className}`} />;
}
