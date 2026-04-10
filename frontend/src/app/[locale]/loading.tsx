export default function Loading() {
  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-6 py-16 flex flex-col items-center">
      {/* Animated lines slowly forming — like the footer animation */}
      <svg width="80" height="80" viewBox="0 0 80 80" className="mb-6">
        {/* Lines drift inward and connect, forming a shape */}
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
      <p className="text-sm text-slate-400 dark:text-slate-500">در حال شکل‌گیری تصویر...</p>

      {/* Skeleton content */}
      <div className="w-full mt-10 space-y-6 max-w-4xl">
        <div className="h-6 w-2/3 bg-slate-100 dark:bg-slate-800 animate-pulse" />
        <div className="h-4 w-full bg-slate-100 dark:bg-slate-800 animate-pulse" />
        <div className="h-4 w-5/6 bg-slate-100 dark:bg-slate-800 animate-pulse" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mt-8">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="space-y-3">
              <div className="aspect-[4/3] bg-slate-100 dark:bg-slate-800 animate-pulse" />
              <div className="h-4 w-3/4 bg-slate-100 dark:bg-slate-800 animate-pulse" />
              <div className="h-3 w-1/2 bg-slate-100 dark:bg-slate-800 animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
