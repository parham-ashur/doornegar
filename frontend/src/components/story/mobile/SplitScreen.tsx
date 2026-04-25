"use client";

import type { ReactNode } from "react";

interface SplitHalf {
  background: ReactNode;
  label: string;
  body: ReactNode;
  tone?: "state" | "diaspora" | "independent";
  onTap?: () => void;
}

interface SplitScreenProps {
  top: SplitHalf;
  bottom: SplitHalf;
  divider?: ReactNode;
  isRtl?: boolean;
}

const TONE_BADGE: Record<NonNullable<SplitHalf["tone"]>, string> = {
  state: "bg-rose-500/90 text-white",
  diaspora: "bg-sky-500/90 text-white",
  independent: "bg-emerald-500/90 text-white",
};

export default function SplitScreen({ top, bottom, divider, isRtl = true }: SplitScreenProps) {
  return (
    <div className="relative flex h-full w-full flex-col" dir={isRtl ? "rtl" : "ltr"}>
      <Half half={top} position="top" />
      {divider && (
        <div className="pointer-events-none absolute inset-x-0 top-1/2 z-30 -translate-y-1/2">
          <div className="mx-auto inline-flex w-full items-center justify-center">
            <span className="rounded-full bg-black/80 px-4 py-1.5 text-[12px] font-extrabold tracking-wide text-white shadow-[0_4px_24px_rgba(0,0,0,0.4)]">
              {divider}
            </span>
          </div>
        </div>
      )}
      <Half half={bottom} position="bottom" />
    </div>
  );
}

function Half({ half, position }: { half: SplitHalf; position: "top" | "bottom" }) {
  const interactive = !!half.onTap;
  return (
    <div
      className={`relative flex flex-1 basis-1/2 overflow-hidden ${
        position === "top" ? "items-end" : "items-start"
      }`}
      onClick={half.onTap}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={(e) => {
        if (interactive && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          half.onTap?.();
        }
      }}
    >
      <div className="absolute inset-0 z-0">{half.background}</div>
      <div
        className={`absolute inset-0 z-[1] bg-gradient-to-${
          position === "top" ? "t" : "b"
        } from-black/75 via-black/30 to-transparent`}
      />
      <div className="relative z-10 w-full px-6 pb-8 pt-8">
        {half.tone && (
          <span
            className={`inline-block px-2 py-0.5 text-[10px] font-bold ${TONE_BADGE[half.tone]}`}
          >
            {half.label}
          </span>
        )}
        {!half.tone && (
          <span className="inline-block bg-white/15 px-2 py-0.5 text-[10px] font-bold text-white">
            {half.label}
          </span>
        )}
        <div className="mt-2 text-[15px] leading-7 text-white drop-shadow-[0_1px_8px_rgba(0,0,0,0.6)]">
          {half.body}
        </div>
      </div>
    </div>
  );
}
