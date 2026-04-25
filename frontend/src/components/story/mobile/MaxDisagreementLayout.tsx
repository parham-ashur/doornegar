"use client";

import StoryBackground from "./StoryBackground";
import SplitScreen from "./SplitScreen";
import type { MobileStorySlot } from "./types";

interface MaxDisagreementLayoutProps {
  slot: MobileStorySlot;
  active?: boolean;
  isRtl?: boolean;
  onOpen?: () => void;
}

export default function MaxDisagreementLayout({
  slot,
  active = true,
  isRtl = true,
  onOpen,
}: MaxDisagreementLayoutProps) {
  if (!slot.sides) return null;
  const [a, b] = slot.sides;
  const title = isRtl ? slot.title_fa : slot.title_en;

  return (
    <div className="relative h-full w-full">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 px-6 pt-5">
        <span className="inline-block bg-black/70 px-3 py-1 text-[11px] font-bold text-white backdrop-blur-md">
          {isRtl ? "بیشترین اختلاف" : "Max disagreement"}
        </span>
        <h2 className="mt-2 text-[20px] font-black leading-tight text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.6)]">
          {title}
        </h2>
      </div>
      <SplitScreen
        isRtl={isRtl}
        divider={isRtl ? "در مقابل" : "vs."}
        top={{
          background: <StoryBackground imageUrl={slot.imageUrl} active={active} />,
          label: isRtl ? a.label_fa : a.label_en,
          body: isRtl ? a.body_fa : a.body_en,
          tone: a.tone,
          onTap: onOpen,
        }}
        bottom={{
          background: <StoryBackground imageUrl={slot.imageUrl} active={active} />,
          label: isRtl ? b.label_fa : b.label_en,
          body: isRtl ? b.body_fa : b.body_en,
          tone: b.tone,
          onTap: onOpen,
        }}
      />
    </div>
  );
}
