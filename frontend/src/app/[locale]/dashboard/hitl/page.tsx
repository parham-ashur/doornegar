"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function HitlIndex() {
  const router = useRouter();
  const [storyId, setStoryId] = useState("");

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
    {
      href: "/fa/dashboard/hitl/sources",
      title: "دسته‌بندی رسانه‌ها",
      desc: "موقعیت تولید، همسویی حکومتی و جناح سیاسی هر رسانه — از همین جا ویرایش کنید تا زیرگروه ۴-تایی (اصول‌گرا/اصلاح‌طلب/میانه‌رو/رادیکال) دقیق بماند.",
    },
    {
      href: "/fa/dashboard/hitl/arcs",
      title: "قوس‌های روایت",
      desc: "پیشنهاد و ساخت قوس‌های روایتی — گروه‌بندی خبرهای مرتبط که در زمان پشت‌سرِ هم رخ داده‌اند.",
    },
  ];

  const extractId = (v: string): string | null => {
    const trimmed = v.trim();
    if (!trimmed) return null;
    const match = trimmed.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    return match ? match[0] : null;
  };

  const go = (kind: "stock-images" | "narrative") => {
    const id = extractId(storyId);
    if (!id) return;
    router.push(`/fa/dashboard/hitl/${kind}/${id}`);
  };

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

      <div className="mt-8 border border-slate-200 dark:border-slate-800 p-4">
        <h2 className="text-[13px] font-black text-slate-900 dark:text-white mb-1">
          ویرایش خبر خاص
        </h2>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-3 leading-6">
          شناسه خبر یا لینک کامل صفحهٔ خبر را بچسبانید — مستقیم به صفحهٔ انتخاب تصویر یا ویرایش روایت می‌رود.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            dir="ltr"
            value={storyId}
            onChange={(e) => setStoryId(e.target.value)}
            placeholder="https://doornegar.org/fa/stories/… یا UUID"
            className="flex-1 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-[13px] px-2 py-1.5"
          />
          <button
            type="button"
            onClick={() => go("stock-images")}
            disabled={!extractId(storyId)}
            className="text-[13px] font-bold px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
          >
            انتخاب تصویر
          </button>
          <button
            type="button"
            onClick={() => go("narrative")}
            disabled={!extractId(storyId)}
            className="text-[13px] font-bold px-3 py-1.5 border border-slate-300 dark:border-slate-700 disabled:opacity-40"
          >
            ویرایش روایت
          </button>
        </div>
      </div>
    </div>
  );
}
