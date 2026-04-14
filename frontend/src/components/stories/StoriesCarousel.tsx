"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import StoryLayout from "./StoryLayout";
import BlindspotLayout from "./BlindspotLayout";
import MaxDisagreementLayout from "./MaxDisagreementLayout";
import TelegramLayout from "./TelegramLayout";
import StoryDetailOverlay from "./StoryDetailOverlay";
import OnboardingHints from "./OnboardingHints";
import type { StoryCore, StorySlot } from "./types";

const SEEN_KEY = "doornegar_stories_seen";
const SEEN_CAP = 200;
const SEEN_DELAY_MS = 2000;
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Bump backend view_count by GETting the story endpoint (backend increments on GET).
// Fire-and-forget with cache: no-store so the network hit actually happens.
function pingView(storyId: string) {
  try {
    fetch(`${API_BASE}/api/v1/stories/${storyId}`, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      keepalive: true,
    }).catch(() => {});
  } catch {}
}

function slotStoryIds(slot: StorySlot): string[] {
  switch (slot.kind) {
    case "story":
      return [slot.story.id];
    case "blindspot":
      return [slot.data.top.story.id, slot.data.bottom.story.id];
    case "maxDisagreement":
      return [slot.data.story.id];
    case "telegram":
      return slot.data.claims.flatMap((c) => (c.story ? [c.story.id] : []));
    default:
      return [];
  }
}

type StoriesCarouselProps = {
  slots: StorySlot[];
  dir?: "rtl" | "ltr";
};

export default function StoriesCarousel({ slots, dir = "rtl" }: StoriesCarouselProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [drilldown, setDrilldown] = useState<StoryCore | null>(null);
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set());

  const slotCount = slots.length;
  const virtualSlots: StorySlot[] = [slots[slotCount - 1], ...slots, slots[0]];

  // Load seen set from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(SEEN_KEY);
      if (raw) setSeenIds(new Set(JSON.parse(raw) as string[]));
    } catch {}
  }, []);

  // After SEEN_DELAY_MS on a slot, mark its story IDs as seen AND ping backend view_count
  useEffect(() => {
    const slot = slots[activeIndex];
    if (!slot) return;
    const ids = slotStoryIds(slot);
    if (ids.length === 0) return;
    const newIds = ids.filter((id) => !seenIds.has(id));
    if (newIds.length === 0) return;
    const timer = setTimeout(() => {
      setSeenIds((prev) => {
        const next = new Set(prev);
        newIds.forEach((id) => next.add(id));
        try {
          const arr = Array.from(next).slice(-SEEN_CAP);
          localStorage.setItem(SEEN_KEY, JSON.stringify(arr));
        } catch {}
        return next;
      });
      // Only bump backend view_count for stories we haven't seen before (first view per user)
      newIds.forEach(pingView);
    }, SEEN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [activeIndex, slots, seenIds]);

  const isSlotSeen = useCallback(
    (i: number) => {
      const ids = slotStoryIds(slots[i]);
      if (ids.length === 0) return false;
      return ids.every((id) => seenIds.has(id));
    },
    [slots, seenIds],
  );

  const openStory = (story: StoryCore) => setDrilldown(story);
  const closeStory = () => setDrilldown(null);
  const advanceAfterDrilldown = () => {
    setDrilldown(null);
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: el.clientWidth, behavior: "smooth" });
  };

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    // Use direct assignment — "instant" as ScrollBehavior is not supported in older Safari
    el.scrollLeft = el.clientWidth;
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;

    let rafId: number | null = null;

    const handleScroll = () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const width = el.clientWidth;
        if (width === 0) return;
        const raw = el.scrollLeft / width;
        const nearestVirtual = Math.round(raw);
        const drift = Math.abs(raw - nearestVirtual);
        if (drift > 0.02) return;

        if (nearestVirtual === 0) {
          el.scrollLeft = width * slotCount;
          setActiveIndex(slotCount - 1);
        } else if (nearestVirtual === slotCount + 1) {
          el.scrollLeft = width;
          setActiveIndex(0);
        } else {
          setActiveIndex(nearestVirtual - 1);
        }
      });
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", handleScroll);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [slotCount]);

  return (
    <div className="fixed inset-0 z-10 bg-black text-white" dir="ltr">
      <div
        ref={scrollerRef}
        className="h-[100dvh] w-full overflow-x-auto overflow-y-hidden whitespace-nowrap stories-scroller"
        style={{
          scrollSnapType: "x mandatory",
          WebkitOverflowScrolling: "touch",
          // Prevent iOS bounce back-swipe from navigating browser history
          overscrollBehaviorX: "contain",
        }}
        dir="ltr"
      >
        {virtualSlots.map((slot, i) => {
          const realIndex = (i - 1 + slotCount) % slotCount;
          const isActive = realIndex === activeIndex;
          return (
            <div
              key={i}
              className="relative inline-block h-full w-full whitespace-normal align-top"
              style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
              data-slot-index={realIndex}
              data-slot-kind={slot.kind}
            >
              <SlotRenderer slot={slot} active={isActive} dir={dir} onOpenStory={openStory} />
            </div>
          );
        })}
      </div>

      <div className="pointer-events-none fixed top-[max(0.5rem,env(safe-area-inset-top))] left-0 right-0 z-20 px-3">
        <div className="flex gap-1">
          {Array.from({ length: slotCount }).map((_, i) => {
            const state =
              i === activeIndex
                ? "bg-white"
                : isSlotSeen(i)
                  ? "bg-white/10"
                  : "bg-white/25";
            return (
              <div
                key={i}
                className={`h-[2px] flex-1 rounded-full transition-colors duration-200 ${state}`}
                data-seen={isSlotSeen(i) ? "1" : "0"}
              />
            );
          })}
        </div>
        <div className="mt-2 flex items-center justify-between text-[10px] tracking-[0.25em] text-white/70 uppercase">
          <span className="font-bold" dir={dir}>
            {dir === "rtl" ? "دورنگر" : "Doornegar"}
          </span>
          <span>
            {String(activeIndex + 1).padStart(2, "0")} / {String(slotCount).padStart(2, "0")}
          </span>
        </div>
      </div>

      {drilldown && (
        <StoryDetailOverlay
          story={drilldown}
          dir={dir}
          onClose={closeStory}
          onAdvance={advanceAfterDrilldown}
        />
      )}

      <OnboardingHints dir={dir} />


      <style>{`
        .stories-scroller::-webkit-scrollbar { display: none; }
        .stories-scroller { scrollbar-width: none; -ms-overflow-style: none; }
      `}</style>
    </div>
  );
}

function SlotRenderer({
  slot,
  active,
  dir,
  onOpenStory,
}: {
  slot: StorySlot;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenStory: (story: StoryCore) => void;
}) {
  switch (slot.kind) {
    case "story":
      return <StoryLayout story={slot.story} active={active} dir={dir} />;
    case "blindspot":
      return (
        <BlindspotLayout
          data={slot.data}
          active={active}
          dir={dir}
          onOpenStory={(id) => {
            const story = id === slot.data.top.story.id ? slot.data.top.story : slot.data.bottom.story;
            onOpenStory(story);
          }}
        />
      );
    case "maxDisagreement":
      return (
        <MaxDisagreementLayout
          data={slot.data}
          active={active}
          dir={dir}
          onOpenStory={() => onOpenStory(slot.data.story)}
        />
      );
    case "telegram":
      return (
        <TelegramLayout
          data={slot.data}
          active={active}
          dir={dir}
          onOpenClaimStory={(story) => onOpenStory(story)}
        />
      );
    case "placeholder":
    default:
      return <PlaceholderSlot slot={slot} dir={dir} />;
  }
}

function PlaceholderSlot({ slot, dir }: { slot: StorySlot; dir: "rtl" | "ltr" }) {
  const bg =
    slot.kind === "placeholder"
      ? slot.bg ?? "bg-gradient-to-br from-slate-700 to-slate-900"
      : slot.kind === "telegram"
      ? "bg-gradient-to-br from-indigo-900 via-indigo-950 to-black"
      : slot.kind === "blindspot"
      ? "bg-gradient-to-br from-emerald-900 via-emerald-950 to-black"
      : "bg-gradient-to-br from-fuchsia-900 via-fuchsia-950 to-black";

  const label =
    slot.kind === "placeholder"
      ? slot.label
      : slot.kind === "telegram"
      ? (dir === "rtl" ? "تحلیل تلگرام" : "Telegram Analysis")
      : slot.kind === "blindspot"
      ? (dir === "rtl" ? "نقطه‌ی کور" : "Blindspot")
      : (dir === "rtl" ? "بیشترین اختلاف نگاه" : "Max disagreement");

  return (
    <div className={`relative h-full w-full ${bg}`} dir={dir}>
      <div className="relative z-10 flex h-full w-full items-center justify-center">
        <div className="px-6 text-center drop-shadow-[0_2px_12px_rgba(0,0,0,0.8)]">
          <div className="text-3xl font-bold">{label}</div>
        </div>
      </div>
    </div>
  );
}
