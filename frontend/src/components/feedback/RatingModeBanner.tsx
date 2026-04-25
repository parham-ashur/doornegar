"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

// Top banner shown on story pages when the URL carries `?feedback=1`.
// Mirrors the blue strip rendered by the home FeedbackProvider on
// /rate so a rater clicking through from /rate sees consistent UI.
export default function RatingModeBanner({ locale }: { locale: string }) {
  const sp = useSearchParams();
  if (sp.get("feedback") !== "1") return null;
  return (
    <div
      dir="rtl"
      className="bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-900/50 px-4 py-3"
    >
      <div className="mx-auto max-w-7xl flex items-center justify-between gap-3">
        <p className="text-[13px] leading-6 text-slate-700 dark:text-slate-300">
          <span className="font-bold">حالت بازخورد</span> —
          {" "}روی هر بخش (عنوان، تصویر، خلاصه، دسته‌بندی) بازخورد بگذارید. منوی شناور سمت چپ گزینه‌های بیشتر دارد.
        </p>
        <Link
          href={`/${locale}/rate`}
          className="text-[12px] font-bold text-blue-700 dark:text-blue-300 hover:underline shrink-0"
        >
          ← بازگشت به فهرست
        </Link>
      </div>
    </div>
  );
}
