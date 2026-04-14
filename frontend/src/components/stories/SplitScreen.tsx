"use client";

import type { ReactNode } from "react";
import type { StoryBackgroundMedia } from "./StoryBackground";
import StoryBackground from "./StoryBackground";

type SplitScreenHalfProps = {
  media: StoryBackgroundMedia;
  active: boolean;
  children: ReactNode;
  dir: "rtl" | "ltr";
  onTap?: () => void;
};

type SplitScreenProps = {
  top: SplitScreenHalfProps;
  bottom: SplitScreenHalfProps;
  divider?: ReactNode;
};

export default function SplitScreen({ top, bottom, divider }: SplitScreenProps) {
  return (
    <div className="relative flex h-full w-full flex-col">
      <Half {...top} />
      <div className="relative z-20">
        {divider ?? <div className="h-px w-full bg-white/15" />}
      </div>
      <Half {...bottom} />
    </div>
  );
}

function Half({ media, active, children, dir, onTap }: SplitScreenHalfProps) {
  return (
    <button
      type="button"
      onClick={onTap}
      className="group relative flex h-1/2 w-full overflow-hidden text-left"
      dir={dir}
      aria-label={typeof onTap === "function" ? "open story" : undefined}
    >
      <StoryBackground media={media} active={active} />
      <div
        className="relative z-10 flex h-full w-full flex-col justify-end px-6 py-6"
        style={{ textAlign: dir === "rtl" ? "right" : "left" }}
      >
        {children}
      </div>
    </button>
  );
}
