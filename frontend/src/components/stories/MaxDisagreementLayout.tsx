"use client";

import { toFa } from "@/lib/utils";
import type { MaxDisagreementSlotData, StoryCore } from "./types";

// Deepest violet — distinct from blindspot's blue/orange.
const VIOLET = "#2E1065"; // violet-950
const VIOLET_DEEP = "#1E1B4B"; // indigo-950
const CONSERVATIVE_COLOR = "#60a5fa";
const OPPOSITION_COLOR = "#E8913A";

type MaxDisagreementLayoutProps = {
  data: MaxDisagreementSlotData;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenStory?: (storyId: string) => void;
};

const LABELS = {
  rtl: {
    eyebrow: "بیشترین اختلاف نگاه",
    disagreement: "اختلاف",
    conservativeLabel: "محافظه‌کار",
    oppositionLabel: "اپوزیسیون",
  },
  ltr: {
    eyebrow: "Max disagreement",
    disagreement: "Disagreement",
    conservativeLabel: "Conservative",
    oppositionLabel: "Opposition",
  },
};

export default function MaxDisagreementLayout({ data, dir, onOpenStory }: MaxDisagreementLayoutProps) {
  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      dir={dir}
      style={{
        background: "linear-gradient(180deg, #0a0e1a 0%, #140f20 60%, #0a0e1a 100%)",
      }}
    >
      {/* Section heading — physical top-right */}
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

      {/* Two stacked cards with violet borders */}
      <div className="absolute inset-x-0 bottom-[5%] top-[calc(env(safe-area-inset-top,0px)+9.5rem)] flex flex-col gap-4 px-5">
        <DisputeCard
          story={data.top.story}
          disputeScore={data.top.disputeScore}
          labels={L}
          dir={dir}
          onOpen={onOpenStory ? () => onOpenStory(data.top.story.id) : undefined}
        />
        <DisputeCard
          story={data.bottom.story}
          disputeScore={data.bottom.disputeScore}
          labels={L}
          dir={dir}
          onOpen={onOpenStory ? () => onOpenStory(data.bottom.story.id) : undefined}
        />
      </div>
    </div>
  );
}

function DisputeCard({
  story,
  labels,
  dir,
  onOpen,
}: {
  story: StoryCore;
  disputeScore: number;
  labels: typeof LABELS.rtl;
  dir: "rtl" | "ltr";
  onOpen?: () => void;
}) {
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
        border: `1.5px solid ${VIOLET}`,
        boxShadow: `0 1px 0 rgba(255,255,255,0.05), 0 20px 60px -20px ${VIOLET_DEEP}66`,
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

      <div className="relative z-10 mt-auto w-full p-5">
        <h3
          className="text-[22px] font-black leading-[1.3] text-white line-clamp-3"
          style={{ textShadow: "0 2px 12px rgba(0,0,0,0.9), 0 1px 3px rgba(0,0,0,0.9)" }}
        >
          {story.title}
        </h3>
        {/* Both percentages on the same line, matching font */}
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
