"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "doornegar_stories_onboarding_seen";

const LABELS = {
  rtl: {
    swipe: "برای مشاهده بیشتر بکشید",
    up: "برای خواندن بیشتر بالا بکشید",
    tap: "برای مطالعه روی خبر بزنید",
    dismiss: "باشد",
  },
  ltr: {
    swipe: "Swipe left or right to explore",
    up: "Swipe up to read more",
    tap: "Tap a story to dive in",
    dismiss: "Got it",
  },
};

type OnboardingHintsProps = {
  dir: "rtl" | "ltr";
  forceShow?: boolean;
};

export default function OnboardingHints({ dir, forceShow }: OnboardingHintsProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (forceShow) {
        setVisible(true);
        return;
      }
      const seen = typeof window !== "undefined" && localStorage.getItem(STORAGE_KEY);
      if (!seen) {
        // Small delay so the user sees the first slot briefly first
        const t = setTimeout(() => setVisible(true), 600);
        return () => clearTimeout(t);
      }
    } catch {}
  }, [forceShow]);

  const dismiss = () => {
    setVisible(false);
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {}
  };

  if (!visible) return null;

  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;

  return (
    <div
      className="pointer-events-auto fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md"
      onClick={dismiss}
      dir={dir}
      data-onboarding-hints
      style={{
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div
        className="max-w-xs px-8 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-10 space-y-10 text-white">
          <Hint icon={<SwipeIcon />} text={L.swipe} />
          <Hint icon={<SwipeUpIcon />} text={L.up} />
          <Hint icon={<TapIcon />} text={L.tap} />
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="inline-block bg-white px-8 py-3 text-[13px] font-bold uppercase tracking-[0.2em] text-black"
        >
          {L.dismiss}
        </button>
      </div>
    </div>
  );
}

function Hint({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="text-white/80">{icon}</div>
      <p className="text-[14px] leading-[1.6] text-white/85">{text}</p>
    </div>
  );
}

function SwipeIcon() {
  return (
    <svg width="48" height="24" viewBox="0 0 48 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M6 12 H42" />
      <path d="M10 7 L6 12 L10 17" />
      <path d="M38 7 L42 12 L38 17" />
    </svg>
  );
}

function SwipeUpIcon() {
  return (
    <svg width="24" height="36" viewBox="0 0 24 36" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M12 30 V6" />
      <path d="M7 10 L12 6 L17 10" />
    </svg>
  );
}

function TapIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="16" cy="16" r="5" />
      <circle cx="16" cy="16" r="10" strokeDasharray="2 3" />
    </svg>
  );
}
