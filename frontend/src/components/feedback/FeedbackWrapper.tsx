"use client";

import { useSearchParams } from "next/navigation";
import RaterOnboarding from "@/components/improvement/RaterOnboarding";

export function FeedbackBanner() {
  const params = useSearchParams();
  if (params.get("feedback") !== "1") return null;

  return (
    <>
      <RaterOnboarding />
      <div dir="rtl" className="bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-900/50 px-4 py-3">
        <div className="mx-auto max-w-7xl">
          <p className="text-[13px] leading-6 text-slate-700 dark:text-slate-300">
            <span className="font-bold">حالت بازخورد</span> —
            دکمه‌های کوچک کنار هر خبر را ببینید: عنوان، تصویر، خلاصه، اولویت و ادغام. کلیک روی هر خبر آن را در حالت بازخورد باز می‌کند.
          </p>
        </div>
      </div>
    </>
  );
}

export function useIsFeedbackMode() {
  const params = useSearchParams();
  return params.get("feedback") === "1";
}
