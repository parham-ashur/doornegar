"use client";

import { toFa } from "@/lib/utils";
import type { BlindspotSlotData, StoryCore } from "./types";

const CONSERVATIVE_COLOR = "#60a5fa"; // blue-400
const OPPOSITION_COLOR = "#E8913A"; // brand orange

type BlindspotLayoutProps = {
  data: BlindspotSlotData;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenStory?: (storyId: string) => void;
};

const LABELS = {
  rtl: {
    eyebrow: "نگاه یک‌جانبه",
    conservativeLabel: "درون‌مرزی",
    oppositionLabel: "برون‌مرزی",
    onlyConservative: "فقط در رسانه‌های درون‌مرزی",
    onlyOpposition: "فقط در رسانه‌های برون‌مرزی",
  },
  ltr: {
    eyebrow: "Blind spot",
    conservativeLabel: "Conservative",
    oppositionLabel: "Opposition",
    onlyConservative: "Only in conservative media",
    onlyOpposition: "Only in opposition media",
  },
};

export default function BlindspotLayout({ data, dir, onOpenStory }: BlindspotLayoutProps) {
  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      dir={dir}
      style={{
        background: "linear-gradient(180deg, #0a0e1a 0%, #131926 60%, #0a0e1a 100%)",
      }}
    >
      {/* Section heading — anchored physically to top-right (دورنگر is top-left) */}
      <div
        className="pointer-events-none absolute top-[calc(env(safe-area-inset-top,0px)+4.25rem)] z-10 right-5"
        dir="ltr"
      >
        <h2
          className="text-right text-[24px] font-black text-white"
          style={{ textWrap: "balance", lineHeight: 1.2 }}
          dir={dir}
        >
          {L.eyebrow}
        </h2>
      </div>

      {/* Two stacked cards — text overlaid on images */}
      <div className="absolute inset-x-0 bottom-[5%] top-[calc(env(safe-area-inset-top,0px)+9.5rem)] flex flex-col gap-4 px-5">
        <BlindspotCard
          story={data.top.story}
          side={data.top.sideLabel.includes("محافظه") ? "conservative" : "opposition"}
          sideText={L.onlyConservative.includes("محافظه") && data.top.sideLabel.includes("محافظه") ? L.onlyConservative : L.onlyOpposition}
          labels={L}
          dir={dir}
          onOpen={onOpenStory ? () => onOpenStory(data.top.story.id) : undefined}
        />
        <BlindspotCard
          story={data.bottom.story}
          side={data.bottom.sideLabel.includes("دیاسپورا") || data.bottom.sideLabel.includes("اپوز") ? "opposition" : "conservative"}
          sideText={L.onlyOpposition}
          labels={L}
          dir={dir}
          onOpen={onOpenStory ? () => onOpenStory(data.bottom.story.id) : undefined}
        />
      </div>
    </div>
  );
}

function BlindspotCard({
  story,
  side,
  sideText,
  labels,
  dir,
  onOpen,
}: {
  story: StoryCore;
  side: "conservative" | "opposition";
  sideText: string;
  labels: typeof LABELS.rtl;
  dir: "rtl" | "ltr";
  onOpen?: () => void;
}) {
  const borderColor = side === "conservative" ? CONSERVATIVE_COLOR : OPPOSITION_COLOR;
  const statePct = Math.round(story.statePct ?? 0);
  const diasporaPct = Math.round(story.diasporaPct ?? 0);
  const fmt = (n: number) => (dir === "rtl" ? `${toFa(n)}٪` : `${n}%`);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="relative flex min-h-0 flex-1 w-full overflow-hidden text-left"
      style={{
        textAlign: dir === "rtl" ? "right" : "left",
        border: `1.5px solid ${borderColor}`,
        boxShadow: `0 1px 0 rgba(255,255,255,0.05), 0 20px 60px -20px ${borderColor}55`,
      }}
      dir={dir}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={story.media.src}
        alt=""
        className="absolute inset-0 h-full w-full object-cover"
        draggable={false}
        loading="eager"
        decoding="async"
        fetchPriority="high"
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.55) 55%, rgba(0,0,0,0.88) 100%)",
        }}
      />

      {/* Text overlaid at bottom */}
      <div className="relative z-10 mt-auto w-full p-5">
        <div
          className="mb-2 text-[11px] font-bold uppercase tracking-[0.22em]"
          style={{ color: borderColor }}
        >
          {sideText}
        </div>
        <h3
          className="text-[22px] font-black leading-[1.3] text-white line-clamp-3"
          style={{ textShadow: "0 2px 12px rgba(0,0,0,0.9), 0 1px 3px rgba(0,0,0,0.9)" }}
        >
          {story.title}
        </h3>
        {/* Both percentages + media name on ONE line, same font */}
        <div
          className="mt-2.5 flex items-baseline gap-3 text-[13px] font-bold"
          style={{ flexDirection: dir === "rtl" ? "row-reverse" : "row" }}
        >
          <span style={{ color: CONSERVATIVE_COLOR }}>
            {labels.conservativeLabel} {fmt(statePct)}
          </span>
          <span className="text-white/35">·</span>
          <span style={{ color: OPPOSITION_COLOR }}>
            {labels.oppositionLabel} {fmt(diasporaPct)}
          </span>
        </div>
      </div>
    </button>
  );
}
