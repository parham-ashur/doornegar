"use client";

import { useEffect, useRef, useState } from "react";

export type StoryBackgroundMedia = {
  type: "video" | "image";
  src: string;
  poster?: string;
};

type StoryBackgroundProps = {
  media: StoryBackgroundMedia;
  active: boolean;
  className?: string;
};

export default function StoryBackground({ media, active, className = "" }: StoryBackgroundProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);

  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    if (active) {
      const p = el.play();
      if (p && typeof p.catch === "function") p.catch(() => {});
    } else {
      el.pause();
      try {
        el.currentTime = 0;
      } catch {}
    }
  }, [active, media.src]);

  const fallbackSrc = media.poster || media.src;
  const useImage = media.type === "image" || videoFailed;

  return (
    <div className={`absolute inset-0 overflow-hidden bg-black ${className}`}>
      {useImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={fallbackSrc}
          alt=""
          className="h-full w-full object-cover"
          draggable={false}
          loading="eager"
          decoding="async"
          fetchPriority="high"
        />
      ) : (
        <video
          ref={videoRef}
          src={media.src}
          poster={media.poster}
          muted
          loop
          playsInline
          preload="metadata"
          className="h-full w-full object-cover"
          onError={() => setVideoFailed(true)}
        />
      )}
      {/* No gradient overlay — the title uses mix-blend-difference and needs
          the raw image as its backdrop for correct auto-inverted color. */}
    </div>
  );
}
