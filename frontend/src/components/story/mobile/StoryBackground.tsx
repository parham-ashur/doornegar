"use client";

import { useEffect, useRef, useState } from "react";

interface StoryBackgroundProps {
  imageUrl?: string;
  videoUrl?: string;
  active?: boolean;
  alt?: string;
}

export default function StoryBackground({ imageUrl, videoUrl, active = true, alt }: StoryBackgroundProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !videoUrl || videoFailed) return;
    if (active) {
      v.play().catch(() => setVideoFailed(true));
    } else {
      v.pause();
      v.currentTime = 0;
    }
  }, [active, videoUrl, videoFailed]);

  const showVideo = videoUrl && !videoFailed;

  return (
    <div className="absolute inset-0 z-0 overflow-hidden bg-black">
      {showVideo ? (
        <video
          ref={videoRef}
          className="absolute inset-0 h-full w-full object-cover"
          src={videoUrl}
          poster={imageUrl}
          muted
          playsInline
          loop
          preload="metadata"
          onError={() => setVideoFailed(true)}
        />
      ) : imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt={alt ?? ""}
          className="absolute inset-0 h-full w-full object-cover"
          loading="lazy"
          decoding="async"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-transparent to-black/70" />
    </div>
  );
}
