"use client";

import { toFa } from "@/lib/utils";
import SplitScreen from "./SplitScreen";
import type { MaxDisagreementSlotData } from "./types";

type MaxDisagreementLayoutProps = {
  data: MaxDisagreementSlotData;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenStory?: () => void;
};

const BRAND_ORANGE = "#E8913A";

const LABELS = {
  rtl: { eyebrow: "بیشترین اختلاف نگاه", divider: "در مقابل" },
  ltr: { eyebrow: "Max disagreement", divider: "In contrast" },
};

export default function MaxDisagreementLayout({
  data,
  active,
  dir,
  onOpenStory,
}: MaxDisagreementLayoutProps) {
  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;
  const openStory = () => onOpenStory?.();

  return (
    <div className="relative h-full w-full">
      {/* Integrated eyebrow — label for this layout type */}
      <div
        className="pointer-events-none absolute top-[max(3rem,calc(env(safe-area-inset-top,0px)+3rem))] inset-x-0 z-30 text-center text-[11px] uppercase tracking-[0.35em] text-white/75"
        dir={dir}
      >
        {L.eyebrow}
      </div>

      <SplitScreen
        top={{
          media: data.story.media,
          active,
          dir,
          onTap: openStory,
          children: (
            <HalfCard
              title={data.story.title}
              sideLabel={data.top.sideLabel}
              percent={data.top.percent}
              framing={data.top.framing}
              showTitle
              dir={dir}
            />
          ),
        }}
        bottom={{
          media: data.story.media,
          active,
          dir,
          onTap: openStory,
          children: (
            <HalfCard
              sideLabel={data.bottom.sideLabel}
              percent={data.bottom.percent}
              framing={data.bottom.framing}
              dir={dir}
            />
          ),
        }}
        divider={
          <div
            className="relative flex items-center justify-center bg-black py-2"
            dir={dir}
          >
            <div
              className="absolute inset-x-0 top-0 h-px"
              style={{ background: `linear-gradient(90deg, transparent, ${BRAND_ORANGE}80, transparent)` }}
            />
            <span
              className="px-3 text-[11px] font-bold uppercase tracking-[0.35em]"
              style={{ color: BRAND_ORANGE }}
            >
              {L.divider}
            </span>
            <div
              className="absolute inset-x-0 bottom-0 h-px"
              style={{ background: `linear-gradient(90deg, transparent, ${BRAND_ORANGE}80, transparent)` }}
            />
          </div>
        }
      />
    </div>
  );
}

function HalfCard({
  title,
  sideLabel,
  percent,
  framing,
  showTitle = false,
  dir,
}: {
  title?: string;
  sideLabel: string;
  percent: number;
  framing: string;
  showTitle?: boolean;
  dir: "rtl" | "ltr";
}) {
  const pctDisplay = dir === "rtl" ? `${toFa(percent)}٪` : `${percent}%`;
  return (
    <div className="drop-shadow-[0_4px_20px_rgba(0,0,0,0.9)]">
      {showTitle && title && (
        <h3
          className="mb-3 text-[20px] font-black leading-snug text-white"
          style={{ textAlign: dir === "rtl" ? "right" : "left" }}
        >
          {title}
        </h3>
      )}
      <div
        className="mb-1 flex items-baseline gap-2"
        style={{ flexDirection: dir === "rtl" ? "row-reverse" : "row" }}
      >
        <span className="text-[11px] uppercase tracking-[0.28em] text-white/75">
          {sideLabel}
        </span>
        <span
          className="text-[18px] font-black"
          style={{ color: BRAND_ORANGE }}
        >
          {pctDisplay}
        </span>
      </div>
      <p className="line-clamp-2 text-[13px] leading-[1.7] text-white/80">
        {framing}
      </p>
    </div>
  );
}
