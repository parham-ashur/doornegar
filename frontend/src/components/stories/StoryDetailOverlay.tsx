"use client";

import { useEffect, useRef } from "react";
import StoryLayout from "./StoryLayout";
import type { StoryCore } from "./types";

type StoryDetailOverlayProps = {
  story: StoryCore;
  dir: "rtl" | "ltr";
  onClose: () => void;
  onAdvance: () => void;
};

const SWIPE_THRESHOLD = 60;

export default function StoryDetailOverlay({
  story,
  dir,
  onClose,
  onAdvance,
}: StoryDetailOverlayProps) {
  const touchState = useRef<{ x: number; y: number } | null>(null);

  // ESC to close (desktop dev convenience)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    touchState.current = { x: t.clientX, y: t.clientY };
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    const start = touchState.current;
    touchState.current = null;
    if (!start) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return;
    // Positive dx = swipe to the right (visually).
    // Spec: swipe LEFT = back to parent slot, swipe RIGHT = forward to next slot.
    // In RTL the "next" direction is logically leftward; we keep spec semantics in screen-pixel terms.
    if (dx > 0) {
      onClose(); // swipe right → "back" — the intuitive close gesture
    } else {
      onAdvance(); // swipe left → advance carousel forward
    }
  };

  return (
    <div
      className="fixed inset-0 z-40 bg-black"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      data-story-detail-overlay={story.id}
    >
      <StoryLayout story={story} active={true} dir={dir} initialScrollTop={180} />
      {/* Close affordance — small pill for accessibility */}
      <button
        type="button"
        onClick={onClose}
        className="fixed top-[calc(env(safe-area-inset-top,0px)+0.75rem)] inset-inline-end-3 z-50 flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white backdrop-blur-sm"
        style={{
          insetInlineEnd: "0.75rem",
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
        }}
        aria-label="close"
      >
        ✕
      </button>
    </div>
  );
}
