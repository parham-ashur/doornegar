"use client";

import { useState } from "react";
import Image from "next/image";
import { Newspaper } from "lucide-react";

// URL-level filter for icons and logos the ingester sometimes picks up
// as the article image when no real og:image is present (happens on
// radiofarda, some Iranian sites that only return a favicon-sized
// app icon). These are 192×192 or similar — they pass the MIN_WIDTH
// check but look like placeholders because they're just site logos
// upscaled into a 16:9 card. Reject at URL level before fetching.
const ICON_URL_PATTERNS = [
  /\/ico-\d+x\d+\.(png|jpg|webp|svg)(\?|$)/i,  // ico-192x192.png
  /\/favicon[.\-]/i,
  /\/icon[.\-]\d+/i,
  /\/apple-touch-icon/i,
  /\/webApp\/ico-/i,
  /\/manifest-icon/i,
];

function isLikelyIcon(src: string): boolean {
  return ICON_URL_PATTERNS.some((re) => re.test(src));
}

// Iran International's Sanity CDN returns 400 "Invalid filename" when
// the bare image hash is requested without a transform+extension
// suffix like `-800x531.jpg`. Our ingester currently captures both the
// valid (hash-WxH.ext) and the invalid (bare hash, or hash-WxH without
// extension) variants depending on which tag in the article HTML
// wins. Valid looks like: …/production/<hash>-800x531.jpg. Invalid
// looks like: …/production/<hash> or …/production/<hash>-2979x1986
// (no extension). Detect and reject the invalid shape up front so we
// don't send a request we know will fail.
function isBrokenIranInternationalUrl(src: string): boolean {
  try {
    const u = new URL(src);
    if (u.hostname !== "i.iranintl.com") return false;
    // Valid form ends with -{w}x{h}.{ext} — any of jpg/jpeg/png/webp
    return !/-\d+x\d+\.(jpg|jpeg|png|webp)(\?|$)/i.test(u.pathname);
  } catch {
    return false;
  }
}

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

  if (!src || failed || isLikelyIcon(src) || isBrokenIranInternationalUrl(src)) {
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
        unoptimized={skipOptimization}
      />
    </div>
  );
}
