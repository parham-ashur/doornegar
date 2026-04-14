"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import StoryLayout from "./StoryLayout";
import BlindspotLayout from "./BlindspotLayout";
import MaxDisagreementLayout from "./MaxDisagreementLayout";
import TelegramLayout from "./TelegramLayout";
import DesktopPreviewLayout from "./DesktopPreviewLayout";
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
      return [slot.data.top.story.id, slot.data.bottom.story.id];
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
  // Mouse-drag state (only used for pointerType=mouse; native touch handles phones)
  const dragState = useRef<{ startX: number; startScroll: number; active: boolean }>({
    startX: 0,
    startScroll: 0,
    active: false,
  });

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

  // Drag-to-scroll handlers — fire for ALL pointer types (mouse, touch, pen).
  // The outer scroller has `touch-action: pan-y` which disables native horizontal
  // panning, so our JS is the single source of horizontal scroll, working identically
  // in Chrome devtools, a real phone, and desktop mouse.
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = scrollerRef.current;
    if (!el) return;
    dragState.current = {
      startX: e.clientX,
      startScroll: el.scrollLeft,
      active: true,
    };
    try {
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    } catch {}
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragState.current.active) return;
    const el = scrollerRef.current;
    if (!el) return;
    // Clamp the drag to ±0.9 slot width so users can only ever reveal at most
    // one slot in either direction. This eliminates "skip a slot" on fast drags.
    const width = el.clientWidth;
    const maxDrag = width * 0.9;
    const rawDx = e.clientX - dragState.current.startX;
    const dx = Math.max(-maxDrag, Math.min(maxDrag, rawDx));
    el.scrollLeft = dragState.current.startScroll - dx;
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragState.current.active) return;
    const el = scrollerRef.current;
    const dx = e.clientX - dragState.current.startX;
    dragState.current.active = false;
    if (!el) return;
    const width = el.clientWidth;
    // If the drag was substantial in one direction, advance/retreat one slot.
    // Otherwise snap back to the starting slot.
    const startIndex = Math.round(dragState.current.startScroll / width);
    let target = startIndex;
    if (Math.abs(dx) > 40) {
      target = startIndex + (dx < 0 ? 1 : -1);
    }
    el.scrollTo({ left: target * width, behavior: "smooth" });
    try {
      (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    } catch {}
  };

  // Trackpad horizontal swipe — fires wheel events with deltaX.
  // scroll-snap-type: x mandatory snaps programmatic scrollLeft back to the nearest
  // snap point, so we can't just accumulate pixels. Instead, each dominant-horizontal
  // wheel burst advances exactly one slot via scrollBy, with a cooldown to prevent
  // runaway trackpad inertia from skipping multiple slots.
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    let locked = false;
    let unlockTimer: ReturnType<typeof setTimeout> | null = null;

    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
      e.preventDefault();
      if (locked) return;
      if (Math.abs(e.deltaX) < 8) return; // ignore tiny jitter
      locked = true;
      const direction = e.deltaX > 0 ? 1 : -1;
      el.scrollBy({ left: direction * el.clientWidth, behavior: "smooth" });
      if (unlockTimer) clearTimeout(unlockTimer);
      unlockTimer = setTimeout(() => {
        locked = false;
      }, 450);
    };

    // Keyboard ←/→ for desktop accessibility (bonus)
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      if (locked) return;
      locked = true;
      const direction = e.key === "ArrowRight" ? 1 : -1;
      el.scrollBy({ left: direction * el.clientWidth, behavior: "smooth" });
      if (unlockTimer) clearTimeout(unlockTimer);
      unlockTimer = setTimeout(() => {
        locked = false;
      }, 450);
    };
    window.addEventListener("keydown", onKey);

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
      window.removeEventListener("keydown", onKey);
      if (unlockTimer) clearTimeout(unlockTimer);
    };
  }, []);

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
        // Don't wrap mid-drag — the user is actively moving, let them finish
        if (dragState.current.active) {
          if (nearestVirtual >= 1 && nearestVirtual <= slotCount) {
            setActiveIndex(nearestVirtual - 1);
          }
          return;
        }
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
    <div className="fixed inset-0 z-10 text-white" dir="ltr">
      <div
        ref={scrollerRef}
        className="h-[100dvh] w-full overflow-x-auto overflow-y-hidden whitespace-nowrap stories-scroller"
        style={{
          scrollSnapType: "x mandatory",
          WebkitOverflowScrolling: "touch",
          // pan-y: native browser only handles vertical scrolling on children (inner
          // story panel). Horizontal intent is fully owned by our pointer handlers,
          // which works in Chrome devtools mouse-drag, trackpad, and real touch.
          touchAction: "pan-y",
          overscrollBehaviorX: "contain",
        }}
        dir="ltr"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
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

      <div className="pointer-events-none fixed top-[max(0.75rem,env(safe-area-inset-top))] left-0 right-0 z-20 px-4">
        <div className="flex gap-1" dir="ltr">
          {Array.from({ length: slotCount }).map((_, i) => {
            const bg =
              i === activeIndex
                ? "rgba(255,255,255,1)"
                : isSlotSeen(i)
                  ? "rgba(255,255,255,0.25)"
                  : "rgba(255,255,255,0.55)";
            return (
              <div
                key={i}
                className="h-[2.5px] flex-1 rounded-full transition-colors duration-200"
                style={{
                  background: bg,
                  boxShadow: "0 1px 3px rgba(0,0,0,0.6)",
                }}
                data-seen={isSlotSeen(i) ? "1" : "0"}
              />
            );
          })}
        </div>
        {/* Top bar: دورنگر pinned to physical top-left.
            mix-blend-mode: difference auto-inverts against the image background. */}
        <div className="mt-3 flex" dir="ltr">
          <span
            className="text-[17px] font-black tracking-[0.02em]"
            dir={dir}
            style={{
              color: "#ffffff",
              mixBlendMode: "difference",
            }}
          >
            {dir === "rtl" ? "دورنگر" : "Doornegar"}
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
          onOpenStory={(id) => {
            const story = id === slot.data.top.story.id ? slot.data.top.story : slot.data.bottom.story;
            onOpenStory(story);
          }}
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
    case "desktopPreview":
      return <DesktopPreviewLayout url={slot.url} dir={dir} />;
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
