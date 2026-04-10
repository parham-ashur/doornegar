"use client";

import { useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";

export interface ScrollArticle {
  title: string;
  source: string;
}

interface StoryRevealProps {
  story: {
    id: string;
    title_fa: string;
    image_url?: string | null;
    source_count: number;
    article_count: number;
    state_pct?: number;
    diaspora_pct?: number;
    independent_pct?: number;
  };
  scrollArticles: ScrollArticle[];
  locale: string;
  summary?: string | null;
}

export default function StoryReveal({ story, scrollArticles, locale, summary }: StoryRevealProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const tickerRef = useRef<HTMLDivElement>(null);
  const thumbRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number>(0);

  const items: ScrollArticle[] = [];
  for (let r = 0; r < 4; r++) {
    for (const a of scrollArticles) items.push(a);
  }

  // Timing — thumbnail emerges while articles are still rolling
  const RUSH_DURATION = 1100;
  const FADE_OUT_START = 400;
  const FADE_OUT_DURATION = 700;
  const FADE_IN_START = 300;
  const FADE_IN_DURATION = 900;

  const animate = useCallback((now: number) => {
    if (!startRef.current) startRef.current = now;
    const elapsed = now - startRef.current;

    const ticker = tickerRef.current;
    const thumb = thumbRef.current;
    if (!ticker || !thumb) return;

    // Scroll — fast start, sharp deceleration like a slot machine / rolodex
    const rushT = Math.min(elapsed / RUSH_DURATION, 1);
    // Exponential ease-out: snaps fast then brakes hard
    const rushEased = 1 - Math.pow(1 - rushT, 4);
    ticker.style.transform = `translateY(${15 - 110 * rushEased}%)`;

    // Ticker fades out
    if (elapsed >= FADE_OUT_START) {
      const t = Math.min((elapsed - FADE_OUT_START) / FADE_OUT_DURATION, 1);
      const e = t * t * (3 - 2 * t);
      ticker.style.opacity = `${1 - e}`;
    } else {
      ticker.style.opacity = "1";
    }

    // Thumbnail fades in
    if (elapsed >= FADE_IN_START) {
      const t = Math.min((elapsed - FADE_IN_START) / FADE_IN_DURATION, 1);
      const e = t * t * (3 - 2 * t);
      thumb.style.opacity = `${e}`;
      thumb.style.transform = `translateY(${(1 - e) * 6}px)`;
    } else {
      thumb.style.opacity = "0";
      thumb.style.transform = "translateY(6px)";
    }

    if (elapsed < FADE_IN_START + FADE_IN_DURATION) {
      rafRef.current = requestAnimationFrame(animate);
    } else {
      ticker.style.opacity = "0";
      thumb.style.opacity = "1";
      thumb.style.transform = "translateY(0)";
    }
  }, []);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animate]);

  const { state_pct = 0, independent_pct = 0, diaspora_pct = 0 } = story;
  const hasSides = state_pct > 0 || independent_pct > 0 || diaspora_pct > 0;

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden">
      {/* Fade edges */}
      <div className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: "linear-gradient(to bottom, var(--reveal-bg) 0%, transparent 10%, transparent 80%, var(--reveal-bg) 100%)",
        }}
      />

      {/* Rushing articles */}
      <div
        ref={tickerRef}
        className="absolute inset-x-0 top-0 px-1"
        style={{ willChange: "transform, opacity" }}
      >
        {items.map((article, i) => (
          <div key={i} className="py-1.5 border-b border-slate-100 dark:border-slate-800/40">
            <div className="text-[9px] text-slate-300 dark:text-slate-600 truncate mb-0.5">
              {article.source}
            </div>
            <div className="text-[11px] leading-snug font-bold text-slate-400 dark:text-slate-500 line-clamp-1">
              {article.title}
            </div>
          </div>
        ))}
      </div>

      {/* Thumbnail */}
      <div
        ref={thumbRef}
        className="absolute inset-0 flex flex-col z-20"
        style={{ opacity: 0, willChange: "transform, opacity" }}
      >
        <Link href={`/${locale}/stories/${story.id}`} className="group flex flex-col h-full">
          <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800">
            <SafeImage src={story.image_url} className="h-full w-full object-cover" />
          </div>
          <div className="mt-2">
            <h3 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
              {story.title_fa}
            </h3>
            <p className="mt-1 text-[10px] text-slate-400">
              {story.source_count} رسانه · {story.article_count} مقاله
            </p>
            {hasSides && (
              <div className="mt-1.5 flex items-center gap-2">
                {state_pct > 0 && <span className="text-[9px] font-medium text-red-500">حکومتی {state_pct}٪</span>}
                {independent_pct > 0 && <span className="text-[9px] font-medium text-emerald-600">مستقل {independent_pct}٪</span>}
                {diaspora_pct > 0 && <span className="text-[9px] font-medium text-blue-600">برون‌مرزی {diaspora_pct}٪</span>}
              </div>
            )}
            {summary && (
              <p className="mt-1.5 text-[11px] leading-[18px] text-slate-400 dark:text-slate-500 line-clamp-3">
                {summary}
              </p>
            )}
          </div>
        </Link>
      </div>

      <style>{`
        :root { --reveal-bg: white; }
        @media (prefers-color-scheme: dark) { :root { --reveal-bg: #0a0e1a; } }
      `}</style>
    </div>
  );
}
