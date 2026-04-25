"use client";

import { useEffect } from "react";
import StoryLayout from "./StoryLayout";
import StoryContentPanel, { StoryContentSection } from "./StoryContentPanel";
import type { MobileStorySlot } from "./types";

interface StoryDetailProps {
  slot: MobileStorySlot;
  isRtl?: boolean;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

export default function StoryDetail({ slot, isRtl = true, onClose, onPrev, onNext }: StoryDetailProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown" && onNext) onNext();
      if (e.key === "ArrowUp" && onPrev) onPrev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onPrev]);

  const title = isRtl ? slot.title_fa : slot.title_en;
  const summary = isRtl ? slot.summary_fa : slot.summary_en;

  return (
    <div className="fixed inset-0 z-50 bg-white dark:bg-[#0a0e1a]">
      <button
        onClick={onClose}
        className="absolute end-4 top-4 z-50 flex h-10 w-10 items-center justify-center rounded-full bg-black/70 text-white backdrop-blur-md"
        aria-label={isRtl ? "بستن" : "Close"}
      >
        ✕
      </button>
      <StoryLayout
        title={title}
        summary={summary}
        imageUrl={slot.imageUrl}
        videoUrl={slot.videoUrl}
        active
        isRtl={isRtl}
      >
        <StoryContentPanel>
          {slot.sides?.map((side, i) => (
            <StoryContentSection
              key={i}
              title={isRtl ? side.label_fa : side.label_en}
            >
              {isRtl ? side.body_fa : side.body_en}
            </StoryContentSection>
          ))}
          <StoryContentSection title={isRtl ? "خلاصه" : "Summary"}>
            {summary || (isRtl ? "خلاصه‌ای موجود نیست." : "No summary.")}
          </StoryContentSection>
          <div className="flex items-center justify-between gap-3 px-6 pt-6">
            <button
              onClick={onPrev}
              disabled={!onPrev}
              className="flex-1 border border-slate-300 px-4 py-2 text-[13px] font-bold text-slate-700 disabled:opacity-30 dark:border-slate-700 dark:text-slate-200"
            >
              {isRtl ? "خبر قبلی" : "Previous"}
            </button>
            <button
              onClick={onNext}
              disabled={!onNext}
              className="flex-1 border border-slate-300 px-4 py-2 text-[13px] font-bold text-slate-700 disabled:opacity-30 dark:border-slate-700 dark:text-slate-200"
            >
              {isRtl ? "خبر بعدی" : "Next"}
            </button>
          </div>
        </StoryContentPanel>
      </StoryLayout>
    </div>
  );
}
