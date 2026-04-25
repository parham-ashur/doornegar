"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "doornegar.mobileStories.onboardingDismissed";

interface OnboardingHintsProps {
  isRtl?: boolean;
}

export default function OnboardingHints({ isRtl = true }: OnboardingHintsProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY) !== "1") setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {}
    setVisible(false);
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-black/80 p-8 text-center backdrop-blur-md"
      onClick={dismiss}
      role="button"
      tabIndex={0}
      dir={isRtl ? "rtl" : "ltr"}
      style={{ WebkitBackdropFilter: "blur(8px)" }}
    >
      <div className="mb-6 text-5xl text-white/90">{isRtl ? "←" : "→"}</div>
      <p className="text-[17px] font-extrabold leading-7 text-white">
        {isRtl ? "برای رفتن به خبر بعدی بکشید" : "Swipe to move between stories"}
      </p>
      <p className="mt-2 text-[13px] leading-6 text-white/70">
        {isRtl
          ? "روی هر خبر بزنید تا جزئیات و دیدگاه‌ها را ببینید."
          : "Tap a story to see details and viewpoints."}
      </p>
      <button
        onClick={(e) => {
          e.stopPropagation();
          dismiss();
        }}
        className="mt-8 border border-white/40 bg-white/10 px-6 py-2 text-[13px] font-bold text-white"
      >
        {isRtl ? "متوجه شدم" : "Got it"}
      </button>
    </div>
  );
}
