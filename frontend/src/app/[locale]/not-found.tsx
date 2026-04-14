import Link from "next/link";

export default function NotFound() {
  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-6 py-24 flex flex-col items-center text-center">
      <div className="text-[120px] font-black text-slate-200 dark:text-slate-800 leading-none select-none">
        ۴۰۴
      </div>
      <h1 className="mt-4 text-xl font-black text-slate-900 dark:text-white">
        صفحه‌ای پیدا نشد
      </h1>
      <p className="mt-3 text-sm text-slate-500 dark:text-slate-400 max-w-md">
        مثل یک نگاه یک‌جانبه در پوشش خبری — این صفحه وجود ندارد یا جابجا شده.
        شاید از زاویه دیگری نگاه کنید.
      </p>
      <div className="mt-8 flex items-center gap-4">
        <Link
          href="/fa"
          className="px-5 py-2.5 text-sm font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200 transition-colors"
        >
          صفحه اصلی
        </Link>
        <Link
          href="/fa/stories"
          className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-700 hover:border-slate-500 dark:hover:border-slate-500 transition-colors"
        >
          خبرها
        </Link>
      </div>
    </div>
  );
}
