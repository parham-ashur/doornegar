"use client";

import { useCallback, useState } from "react";
import StoriesCarousel from "./StoriesCarousel";
import StoryLayout from "./StoryLayout";
import StoryContentPanel, { StoryContentSection } from "./StoryContentPanel";
import BlindspotLayout from "./BlindspotLayout";
import MaxDisagreementLayout from "./MaxDisagreementLayout";
import TelegramLayout from "./TelegramLayout";
import StoryDetail from "./StoryDetail";
import OnboardingHints from "./OnboardingHints";
import type { MobileStorySlot } from "./types";

interface MobileStoriesExperienceProps {
  slots: MobileStorySlot[];
  isRtl?: boolean;
}

export default function MobileStoriesExperience({ slots, isRtl = true }: MobileStoriesExperienceProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const open = useCallback((i: number) => setOpenIndex(i), []);
  const close = useCallback(() => setOpenIndex(null), []);
  const goPrev = useCallback(() => {
    setOpenIndex((cur) => (cur === null ? cur : (cur - 1 + slots.length) % slots.length));
  }, [slots.length]);
  const goNext = useCallback(() => {
    setOpenIndex((cur) => (cur === null ? cur : (cur + 1) % slots.length));
  }, [slots.length]);

  const rendered = slots.map((slot, i) => {
    const isActive = i === activeIndex;
    const onOpen = () => open(i);
    switch (slot.kind) {
      case "blindspot":
        return (
          <BlindspotLayout key={slot.id} slot={slot} active={isActive} isRtl={isRtl} onOpen={onOpen} />
        );
      case "max_disagreement":
        return (
          <MaxDisagreementLayout key={slot.id} slot={slot} active={isActive} isRtl={isRtl} onOpen={onOpen} />
        );
      case "telegram":
        return <TelegramLayout key={slot.id} slot={slot} isRtl={isRtl} onOpen={onOpen} />;
      case "story":
      default:
        return (
          <StoryLayout
            key={slot.id}
            title={isRtl ? slot.title_fa : slot.title_en}
            summary={isRtl ? slot.summary_fa : slot.summary_en}
            imageUrl={slot.imageUrl}
            videoUrl={slot.videoUrl}
            active={isActive}
            isRtl={isRtl}
            onOpen={onOpen}
          >
            <StoryContentPanel>
              <StoryContentSection title={isRtl ? "خلاصه" : "Summary"}>
                {(isRtl ? slot.summary_fa : slot.summary_en) ||
                  (isRtl ? "خلاصه‌ای موجود نیست." : "No summary.")}
              </StoryContentSection>
              <StoryContentSection title={isRtl ? "نگاه رسانه‌ها" : "Media takes"}>
                {isRtl
                  ? "این بخش در نسخه واقعی، دیدگاه رسانه‌های مختلف را در کنار هم نشان می‌دهد."
                  : "In production this shows different outlets' framings side-by-side."}
              </StoryContentSection>
            </StoryContentPanel>
          </StoryLayout>
        );
    }
  });

  return (
    <>
      <StoriesCarousel slotCount={slots.length} rtl={isRtl} onSlotChange={setActiveIndex}>
        {rendered}
      </StoriesCarousel>
      {openIndex !== null && (
        <StoryDetail
          slot={slots[openIndex]}
          isRtl={isRtl}
          onClose={close}
          onPrev={goPrev}
          onNext={goNext}
        />
      )}
      <OnboardingHints isRtl={isRtl} />
    </>
  );
}
