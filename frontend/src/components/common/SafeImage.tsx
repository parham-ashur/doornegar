"use client";

import { useState, useCallback } from "react";
import Image from "next/image";
import { Newspaper } from "lucide-react";

// Images smaller than this are considered low quality (tracking pixels, tiny icons).
const MIN_WIDTH = 120;
const MIN_HEIGHT = 80;

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Iran-hosted media that geo-block Vercel's US/EU edge IPs. Vercel's
// `/_next/image` proxy-fetches the source from its own servers to
// optimize; when the source blocks Vercel, the endpoint returns a
// 400 and the image renders as a placeholder even though users can
// reach it directly from their browsers. For these hostnames we
// bypass Vercel's optimizer and emit a plain <img> — browsers load
// the image directly from the source.
const GEOBLOCKED_FROM_VERCEL = [
  "irna.ir",
  "tasnimnews.com",
  "farsnews.ir",
  "farsnews.com",
  "mehrnews.com",
  "mashreghnews.ir",
  "nournews.ir",
  "iribnews.ir",
  "isna.ir",
  "etemadnewspaper.ir",
  "khabaronline.ir",
  "yjc.ir",
  "tabnak.ir",
  "asriran.com",
  "sharghdaily.com",
  "ilna.ir",
  "entekhab.ir",
  "rajanews.com",
  "hamshahrionline.ir",
];

function resolveUrl(src: string): string {
  // Relative /images/... paths served by the backend
  if (src.startsWith("/images/")) return `${API_BASE}${src}`;
  return src;
}

function isGeoblockedFromVercel(src: string): boolean {
  try {
    const host = new URL(src).hostname.toLowerCase();
    return GEOBLOCKED_FROM_VERCEL.some(
      (d) => host === d || host.endsWith("." + d),
    );
  } catch {
    return false;
  }
}

export default function SafeImage({
  src,
  alt = "تصویر خبر",
  className,
  placeholderClass,
  sizes = "(max-width: 768px) 100vw, 50vw",
  priority = false,
}: {
  src: string | null;
  alt?: string;
  className?: string;
  placeholderClass?: string;
  /** Next.js Image sizes attribute — tune per call site for best srcset. */
  sizes?: string;
  /** Set true for above-the-fold hero images (disables lazy-loading + preloads). */
  priority?: boolean;
}) {
  const [failed, setFailed] = useState(false);

  const handleLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (img.naturalWidth && img.naturalHeight) {
      if (img.naturalWidth < MIN_WIDTH || img.naturalHeight < MIN_HEIGHT) {
        setFailed(true);
      }
    }
  }, []);

  if (!src || failed) {
    return (
      <div className={placeholderClass || "flex h-full w-full items-center justify-center bg-slate-100 dark:bg-slate-800"}>
        <Newspaper className="h-10 w-10 text-slate-300 dark:text-slate-700" />
      </div>
    );
  }

  const resolved = resolveUrl(src);
  const skipOptimization = isGeoblockedFromVercel(resolved);

  // next/image fill mode needs a position:relative parent. We render our own
  // so callers don't have to add `relative` to every aspect-ratio wrapper.
  return (
    <div className="relative h-full w-full">
      <Image
        src={resolved}
        alt={alt}
        fill
        sizes={sizes}
        priority={priority}
        className={className || "object-cover"}
        onError={() => setFailed(true)}
        onLoad={handleLoad}
        unoptimized={skipOptimization}
      />
    </div>
  );
}
