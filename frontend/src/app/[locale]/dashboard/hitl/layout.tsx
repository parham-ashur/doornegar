import Link from "next/link";

// HITL dashboard shared chrome: admin nav + auth reminder. The token
// itself is handled per-page (stored in localStorage and attached to
// every fetch). Keeping the nav client-less means each page can set
// its own title/meta without a useEffect.
export default function HitlLayout({ children }: { children: React.ReactNode }) {
  return (
    <div dir="rtl" className="min-h-screen bg-white dark:bg-slate-950">
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 sticky top-0 z-10">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
          <Link href="/fa/dashboard" className="text-[13px] font-black text-slate-900 dark:text-white">
            داشبورد دورنگر
          </Link>
          <nav className="flex gap-4 text-[13px]">
            <Link href="/fa/dashboard/hitl/submissions" className="text-slate-600 dark:text-slate-400 hover:text-blue-600">
              ارسال‌ها
            </Link>
            <Link href="/fa/dashboard/hitl/telegram-triage" className="text-slate-600 dark:text-slate-400 hover:text-blue-600">
              صف تلگرام
            </Link>
            <Link href="/fa/dashboard/hitl/channels" className="text-slate-600 dark:text-slate-400 hover:text-blue-600">
              دسته‌بندی کانال‌ها
            </Link>
            <Link href="/fa/dashboard/hitl" className="text-slate-600 dark:text-slate-400 hover:text-blue-600">
              نمای کلی
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
