"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import useEmblaCarousel from "embla-carousel-react";

interface StoriesCarouselProps {
  children?: ReactNode[];
  slotCount?: number;
  rtl?: boolean;
  onSlotChange?: (index: number) => void;
}

export default function StoriesCarousel({
  children,
  slotCount = 6,
  rtl = true,
  onSlotChange,
}: StoriesCarouselProps) {
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: true,
    direction: rtl ? "rtl" : "ltr",
    align: "start",
    containScroll: false,
    duration: 22,
  });
  const [selected, setSelected] = useState(0);

  const handleSelect = useCallback(() => {
    if (!emblaApi) return;
    const idx = emblaApi.selectedScrollSnap();
    setSelected(idx);
    onSlotChange?.(idx);
  }, [emblaApi, onSlotChange]);

  useEffect(() => {
    if (!emblaApi) return;
    handleSelect();
    emblaApi.on("select", handleSelect);
    emblaApi.on("reInit", handleSelect);
    return () => {
      emblaApi.off("select", handleSelect);
      emblaApi.off("reInit", handleSelect);
    };
  }, [emblaApi, handleSelect]);

  const slots = children?.length ? children : Array.from({ length: slotCount }, (_, i) => (
    <PlaceholderSlot key={i} index={i} total={slotCount} />
  ));

  return (
    <div className="relative h-[100dvh] w-full overflow-hidden bg-black text-white select-none">
      <div className="h-full" ref={emblaRef}>
        <div className="flex h-full">
          {slots.map((slot, i) => (
            <div key={i} className="relative h-full min-w-0 flex-[0_0_100%]">
              {slot}
            </div>
          ))}
        </div>
      </div>
      <div
        className="pointer-events-none absolute inset-x-0 top-3 flex justify-center gap-1 px-4"
        dir="ltr"
      >
        {slots.map((_, i) => (
          <span
            key={i}
            className={`h-[3px] flex-1 rounded-full transition-colors ${
              i === selected ? "bg-white" : "bg-white/25"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

function PlaceholderSlot({ index, total }: { index: number; total: number }) {
  const hue = (index * 360) / total;
  return (
    <div
      className="flex h-full w-full items-center justify-center"
      style={{ background: `hsl(${hue} 60% 18%)` }}
    >
      <span className="text-2xl font-black tracking-wide text-white/80">
        {index + 1} / {total}
      </span>
    </div>
  );
}
