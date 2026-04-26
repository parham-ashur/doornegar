"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  words: string[];
  className?: string;
  // Stagger different cards so they don't all flip at the same instant.
  delayMs?: number;
  intervalMs?: number;
  fadeMs?: number;
  // Match the existing «...» quote wrapping in تقابل روایت‌ها cards so the
  // visual is identical to the static version when there's only one word.
  quoted?: boolean;
}

export default function RotatingWord({
  words,
  className = "",
  delayMs = 0,
  intervalMs = 3500,
  fadeMs = 350,
  quoted = true,
}: Props) {
  const [idx, setIdx] = useState(0);
  const [opacity, setOpacity] = useState(1);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (words.length <= 1) return;
    const startId = window.setTimeout(() => {
      intervalRef.current = window.setInterval(() => {
        setOpacity(0);
        window.setTimeout(() => {
          setIdx((i) => (i + 1) % words.length);
          setOpacity(1);
        }, fadeMs);
      }, intervalMs);
    }, delayMs);
    return () => {
      window.clearTimeout(startId);
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [words, delayMs, intervalMs, fadeMs]);

  if (words.length === 0) return null;
  const word = words[idx] || "";
  const display = quoted ? `«${word}»` : word;

  return (
    <span
      style={{
        opacity,
        transition: `opacity ${fadeMs}ms ease-in-out`,
        display: "inline-block",
      }}
      className={className}
    >
      {display}
    </span>
  );
}
