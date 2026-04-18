import Link from "next/link";

export default function HitlIndex() {
  const tiles = [
    {
      href: "/fa/dashboard/hitl/submissions",
      title: "ارسال‌های کاربران",
      desc: "بررسی محتوای ارسال‌شده از فرم /submit و اتصال به خبر مناسب.",
    },
    {
      href: "/fa/dashboard/hitl/telegram-triage",
      title: "صف بررسی پست‌های تلگرام",
      desc: "پست‌های مرزی (۰.۳۰ تا ۰.۴۰) که خودکار متصل نشدند. انتخاب دستی بهترین خبر.",
    },
    {
      href: "/fa/dashboard/hitl/channels",
      title: "دسته‌بندی کانال‌ها",
      desc: "مرور نمونه پست‌های هر کانال و اصلاح نوع آن (خبری، تحلیلگر، بازنشر و غیره).",
    },
  ];
  return (
    <div>
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-4">
        ابزارهای انسانی در حلقه (HITL)
      </h1>
      <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-6 leading-6">
        این ابزارها جاهایی را پوشش می‌دهند که خودکارسازی اشتباه می‌کند یا مطمئن نیست.
        هر نقطه تماس یک صف کوچک دارد — چند دقیقه در روز مرور کنید.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tiles.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="block border border-slate-200 dark:border-slate-800 p-4 hover:border-blue-400 transition-colors"
          >
            <h2 className="text-[13px] font-black text-slate-900 dark:text-white mb-1">
              {t.title}
            </h2>
            <p className="text-[13px] text-slate-500 dark:text-slate-400 leading-6">
              {t.desc}
            </p>
          </Link>
        ))}
      </div>
      <p className="mt-6 text-[13px] text-slate-400 dark:text-slate-500">
        ویرایش روایت‌های هر خبر و انتخاب تصویر پوشش از صفحهٔ جزئیات هر خبر انجام می‌شود
        (لینک‌های «ویرایش روایت» و «انتخاب تصویر» در نوار ابزار خبر).
      </p>
    </div>
  );
}
