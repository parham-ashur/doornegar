"use client";

import SplitScreen from "./SplitScreen";
import type { BlindspotSlotData } from "./types";

type BlindspotLayoutProps = {
  data: BlindspotSlotData;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenStory?: (storyId: string) => void;
};
// onOpenStory is kept by id because the layout knows which of its two stories was tapped.

const LABELS = {
  rtl: { eyebrow: "نقطه‌ی کور" },
  ltr: { eyebrow: "Blind spot" },
};

export default function BlindspotLayout({ data, active, dir, onOpenStory }: BlindspotLayoutProps) {
  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;

  return (
    <div className="relative h-full w-full">
      {/* Top eyebrow — blends into the design */}
      <div
        className="pointer-events-none absolute top-[max(3rem,calc(env(safe-area-inset-top,0px)+3rem))] inset-x-0 z-30 text-center text-[11px] uppercase tracking-[0.35em] text-white/75"
        dir={dir}
      >
        {L.eyebrow}
      </div>

      <SplitScreen
        top={{
          media: data.top.story.media,
          active,
          dir,
          onTap: onOpenStory ? () => onOpenStory(data.top.story.id) : undefined,
          children: (
            <HalfCard
              sideLabel={data.top.sideLabel}
              title={data.top.story.title}
              excerpt={data.top.excerpt}
              dir={dir}
            />
          ),
        }}
        bottom={{
          media: data.bottom.story.media,
          active,
          dir,
          onTap: onOpenStory ? () => onOpenStory(data.bottom.story.id) : undefined,
          children: (
            <HalfCard
              sideLabel={data.bottom.sideLabel}
              title={data.bottom.story.title}
              excerpt={data.bottom.excerpt}
              dir={dir}
            />
          ),
        }}
      />
    </div>
  );
}

function HalfCard({
  sideLabel,
  title,
  excerpt,
  dir,
}: {
  sideLabel: string;
  title: string;
  excerpt: string;
  dir: "rtl" | "ltr";
}) {
  return (
    <div className="drop-shadow-[0_4px_20px_rgba(0,0,0,0.9)]">
      <div className="mb-2 text-[10px] uppercase tracking-[0.3em] text-white/80">
        {sideLabel}
      </div>
      <h3
        className="mb-2 text-[21px] font-black leading-snug text-white"
        style={{ textAlign: dir === "rtl" ? "right" : "left" }}
      >
        {title}
      </h3>
      <p className="line-clamp-2 text-[13px] leading-[1.7] text-white/75">
        {excerpt}
      </p>
    </div>
  );
}
