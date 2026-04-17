"use client";

import { useEffect, useRef, useState } from "react";
import { toFa } from "@/lib/utils";
import StoryBackground from "./StoryBackground";
import StoryContentPanel from "./StoryContentPanel";
import type { StoryCore } from "./types";

type StoryLayoutProps = {
  story: StoryCore;
  active: boolean;
  dir?: "rtl" | "ltr";
  initialScrollTop?: number;
};

const CONSERVATIVE_COLOR = "#60a5fa";
const OPPOSITION_COLOR = "#E8913A";

export default function StoryLayout({
  story,
  active,
  dir = "rtl",
  initialScrollTop,
}: StoryLayoutProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    if (!active && initialScrollTop === undefined && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [active, initialScrollTop]);

  useEffect(() => {
    if (initialScrollTop !== undefined && scrollRef.current) {
      scrollRef.current.scrollTop = initialScrollTop;
    }
  }, [initialScrollTop]);

  // Detect whether the user has scrolled — used to hide the swipe-up arrow
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setScrolled(el.scrollTop > 40);
    el.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const statePct = Math.round(story.statePct ?? 0);
  const diasporaPct = Math.round(story.diasporaPct ?? 0);
  const hasBias = statePct > 0 || diasporaPct > 0;
  const fmt = (n: number) => (dir === "rtl" ? `${toFa(n)}٪` : `${n}%`);
  const L = dir === "rtl"
    ? { conservative: "درون‌مرزی", opposition: "برون‌مرزی", swipeHint: "برای ادامه بالا بکشید" }
    : { conservative: "Conservative", opposition: "Opposition", swipeHint: "Swipe up to read more" };

  return (
    <div className="relative h-full w-full overflow-hidden" dir={dir}>
      <StoryBackground media={story.media} active={active} />

      {/* Title + percentages block — sticky at top, both right-aligned.
          mix-blend-difference on the whole block gives auto contrast.
          A subtle vertical mask underneath provides a "content fades under title"
          effect when the content panel scrolls behind it. */}
      <div
        className="pointer-events-none absolute inset-x-0 z-30 px-6"
        style={{
          top: "calc(env(safe-area-inset-top, 0px) + 3.5rem)",
          textAlign: dir === "rtl" ? "right" : "left",
          color: "#ffffff",
          mixBlendMode: "difference",
        }}
      >
        <h2
          className="font-black"
          style={{
            fontSize: "34px",
            lineHeight: 1.25,
            textWrap: "balance",
          }}
        >
          {story.title}
        </h2>

        {/* Percentages — directly below the title, same right-alignment */}
        {hasBias && (
          <div
            className="mt-3 flex items-baseline gap-3 text-[14px] font-black"
            style={{
              flexDirection: dir === "rtl" ? "row-reverse" : "row",
              justifyContent: dir === "rtl" ? "flex-start" : "flex-start",
            }}
          >
            <span>{L.conservative} {fmt(statePct)}</span>
            <span style={{ opacity: 0.6 }}>·</span>
            <span>{L.opposition} {fmt(diasporaPct)}</span>
          </div>
        )}
      </div>

      {/* Animated swipe-up arrow hint — bottom of viewport, hidden after first scroll */}
      {!scrolled && (
        <div
          className="pointer-events-none absolute inset-x-0 bottom-[6%] z-30 flex justify-center"
          style={{ color: "#ffffff", mixBlendMode: "difference" }}
        >
          <div className="swipe-hint flex flex-col items-center gap-2">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 19 V5" />
              <path d="M5 12 L12 5 L19 12" />
            </svg>
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
              {L.swipeHint}
            </span>
          </div>
        </div>
      )}

      {/* Scroll container — narratives rise from below and scroll up behind
          the title. The spacer keeps content off-screen at scroll=0. */}
      <div
        ref={scrollRef}
        className="story-scroll relative z-10 h-full overflow-y-auto overflow-x-hidden overscroll-contain"
        style={{
          WebkitOverflowScrolling: "touch",
          touchAction: "pan-y",
        }}
      >
        <div className="h-[100dvh] w-full" aria-hidden="true" />
        <StoryContentPanel story={story} dir={dir} />
      </div>

      {/* Dark fade at the very top of the viewport — content scrolls BEHIND
          this, making text disappear smoothly as it reaches the title area.
          It sits ABOVE the scroll container (z-20) but BELOW the title (z-30),
          and has no solid boundary, so it reads as a soft vignette, not a bar. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 z-20"
        style={{
          height: "calc(env(safe-area-inset-top, 0px) + 11rem)",
          background:
            "linear-gradient(180deg, rgba(12,14,22,0.92) 0%, rgba(12,14,22,0.85) 55%, rgba(12,14,22,0.5) 85%, rgba(12,14,22,0) 100%)",
          WebkitBackdropFilter: "blur(6px)",
          backdropFilter: "blur(6px)",
          opacity: scrolled ? 1 : 0,
          transition: "opacity 200ms ease-out",
        }}
      />

      <style>{`
        .story-scroll::-webkit-scrollbar { display: none; }
        .story-scroll { scrollbar-width: none; -ms-overflow-style: none; }
        .swipe-hint {
          animation: swipe-hint-bob 2.2s ease-in-out infinite;
        }
        @keyframes swipe-hint-bob {
          0%, 100% { transform: translateY(0); opacity: 0.85; }
          50% { transform: translateY(-8px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
