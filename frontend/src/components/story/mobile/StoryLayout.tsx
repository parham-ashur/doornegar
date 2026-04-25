"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import StoryBackground from "./StoryBackground";

interface StoryLayoutProps {
  title: string;
  summary?: string;
  imageUrl?: string;
  videoUrl?: string;
  active?: boolean;
  isRtl?: boolean;
  onOpen?: () => void;
  children?: ReactNode;
}

export default function StoryLayout({
  title,
  summary,
  imageUrl,
  videoUrl,
  active = true,
  isRtl = true,
  onOpen,
  children,
}: StoryLayoutProps) {
  const heroRef = useRef<HTMLDivElement | null>(null);
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const node = heroRef.current;
    if (!node) return;
    const obs = new IntersectionObserver(
      ([entry]) => setStuck(entry.intersectionRatio < 0.35),
      { threshold: [0, 0.35, 1] },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, []);

  return (
    <div
      className="relative h-full w-full overflow-y-auto overflow-x-hidden"
      dir={isRtl ? "rtl" : "ltr"}
    >
      <StickyTitle title={title} visible={stuck} />
      <section
        ref={heroRef}
        className="relative flex h-[100dvh] w-full flex-col justify-end px-6 pb-24"
        onClick={onOpen}
        role={onOpen ? "button" : undefined}
        tabIndex={onOpen ? 0 : undefined}
      >
        <StoryBackground imageUrl={imageUrl} videoUrl={videoUrl} active={active} />
        <div className="relative z-10 max-w-2xl">
          <h1 className="text-[28px] font-black leading-tight text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.6)]">
            {title}
          </h1>
          {summary && (
            <p className="mt-3 text-[14px] leading-7 text-white/85 drop-shadow-[0_1px_8px_rgba(0,0,0,0.6)]">
              {summary}
            </p>
          )}
        </div>
      </section>
      {children && <div className="relative z-0 bg-white text-slate-900 dark:bg-[#0a0e1a] dark:text-slate-100">{children}</div>}
    </div>
  );
}

function StickyTitle({ title, visible }: { title: string; visible: boolean }) {
  return (
    <div
      className={`pointer-events-none sticky top-0 z-30 transition-all duration-300 ${
        visible ? "opacity-100 translate-y-0" : "-translate-y-full opacity-0"
      }`}
    >
      <div
        className="bg-black/70 px-5 py-3 backdrop-blur-md"
        style={{ WebkitBackdropFilter: "blur(8px)" }}
      >
        <p className="truncate text-[14px] font-extrabold text-white">{title}</p>
      </div>
    </div>
  );
}
