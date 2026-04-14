"use client";

import { useEffect, useRef } from "react";
import StoryBackground from "./StoryBackground";
import StoryContentPanel from "./StoryContentPanel";
import type { StoryCore } from "./types";

type StoryLayoutProps = {
  story: StoryCore;
  active: boolean;
  dir?: "rtl" | "ltr";
  // When set, mount with the scroll container pre-scrolled past the A→B threshold.
  // Used for drilldown StoryDetail where we want State B immediately.
  initialScrollTop?: number;
};

// State A → State B transition thresholds (spec)
const SCROLL_END = 150;
const FONT_START = 34;
const FONT_END = 18;
const TOP_START_FRACTION = 0.65; // 65% of slot height — lower third
const TOP_END_PX = 52; // below integrated brand-mark bar
const BAR_MAX_OPACITY = 0.7;
const BAR_MAX_BLUR = 12;
const NOWRAP_THRESHOLD = 0.55; // above this progress, force single-line ellipsis

export default function StoryLayout({
  story,
  active,
  dir = "rtl",
  initialScrollTop,
}: StoryLayoutProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const scroller = scrollRef.current;
    const title = titleRef.current;
    const bar = barRef.current;
    if (!scroller || !title || !bar) return;

    const apply = () => {
      const sy = scroller.scrollTop;
      const p = Math.max(0, Math.min(1, sy / SCROLL_END));
      const h = scroller.clientHeight;
      const topStart = h * TOP_START_FRACTION;
      const fontSize = FONT_START - (FONT_START - FONT_END) * p;
      const topPx = topStart - (topStart - TOP_END_PX) * p;
      const barOpacity = p * BAR_MAX_OPACITY;
      const barBlur = BAR_MAX_BLUR * p;

      title.style.fontSize = `${fontSize}px`;
      title.style.top = `${topPx}px`;
      if (p > NOWRAP_THRESHOLD) {
        title.style.whiteSpace = "nowrap";
        title.style.overflow = "hidden";
        title.style.textOverflow = "ellipsis";
      } else {
        title.style.whiteSpace = "normal";
        title.style.overflow = "visible";
        title.style.textOverflow = "clip";
      }
      title.setAttribute("data-scroll-progress", p.toFixed(2));

      bar.style.opacity = String(barOpacity);
      bar.style.backdropFilter = `blur(${barBlur}px)`;
      // @ts-expect-error -- vendor-prefixed
      bar.style.webkitBackdropFilter = `blur(${barBlur}px)`;
    };

    const onScroll = () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = requestAnimationFrame(apply);
    };

    scroller.addEventListener("scroll", onScroll, { passive: true });
    // Jump to pre-seeded scroll position BEFORE running apply() for immediate State B
    if (initialScrollTop !== undefined) {
      scroller.scrollTop = initialScrollTop;
    }
    apply();
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [initialScrollTop]);

  // When the slot becomes inactive, reset scroll to top so State A shows on return
  // (but skip this reset when we were pre-seeded into State B for drilldown)
  useEffect(() => {
    if (!active && initialScrollTop === undefined) {
      scrollRef.current?.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
    }
  }, [active, initialScrollTop]);

  return (
    <div className="relative h-full w-full overflow-hidden" dir={dir}>
      <StoryBackground media={story.media} active={active} />

      {/* State B blur bar — behind the floating title, grows opacity on scroll */}
      <div
        ref={barRef}
        className="pointer-events-none absolute inset-x-0 top-0 z-20 h-[calc(env(safe-area-inset-top,0px)+80px)] bg-black/60"
        style={{ opacity: 0 }}
      />

      {/* Floating title — absolute-positioned, driven by scroll */}
      <h2
        ref={titleRef}
        className="pointer-events-none absolute inset-x-0 z-30 px-6 font-black text-white drop-shadow-[0_4px_20px_rgba(0,0,0,0.9)]"
        style={{
          top: `65%`,
          fontSize: `${FONT_START}px`,
          lineHeight: 1.22,
          textAlign: dir === "rtl" ? "right" : "left",
          transition: "none",
        }}
      >
        {story.title}
      </h2>

      {/* Scrollable container — holds the content panel. Spacer reserves room for State A title. */}
      <div
        ref={scrollRef}
        className="story-scroll relative z-10 h-full overflow-y-auto overflow-x-hidden overscroll-contain"
      >
        {/* State A empty zone */}
        <div className="h-[100dvh] w-full" aria-hidden="true" />
        {/* Fade from transparent to dark before the content panel begins */}
        <div className="h-24 w-full bg-gradient-to-t from-black/80 to-transparent" aria-hidden="true" />
        <StoryContentPanel story={story} dir={dir} />
      </div>

      <style>{`
        .story-scroll::-webkit-scrollbar { display: none; }
        .story-scroll { scrollbar-width: none; -ms-overflow-style: none; }
      `}</style>
    </div>
  );
}
