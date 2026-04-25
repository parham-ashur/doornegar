"use client";

import { useState } from "react";
import Image from "next/image";
import { Newspaper } from "lucide-react";
import {
  isGeoblockedFromVercel,
  isUnusableUrl,
  resolveUrl,
} from "@/lib/imageFilters";

export default function SafeImage({
  src,
  alt = "تصویر خبر",
  className,
  placeholderClass,
  sizes = "(max-width: 768px) 100vw, 50vw",
  priority = false,
  quality = 70,
}: {
  src: string | null;
  alt?: string;
  className?: string;
  placeholderClass?: string;
  /** Next.js Image sizes attribute — tune per call site for best srcset. */
  sizes?: string;
  /** Set true for above-the-fold hero images (disables lazy-loading + preloads). */
  priority?: boolean;
  /** WebP quality. 70 default for hero/visible-on-load cases. Cards use SafeImageStatic at 65. */
  quality?: number;
}) {
  const [failed, setFailed] = useState(false);

  if (!src || failed || isUnusableUrl(src)) {
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
        quality={quality}
        className={className || "object-cover"}
        onError={() => setFailed(true)}
        unoptimized={skipOptimization}
      />
    </div>
  );
}
