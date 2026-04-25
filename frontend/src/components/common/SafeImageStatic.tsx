// Server-component sibling of SafeImage. Same URL filtering, same Vercel
// optimizer bypass, but no runtime onError state — broken images stay
// broken until the next ISR regenerate. Used on homepage cards / related-
// stories slider where the runtime fallback wasn't worth a client island
// per image card. Keep `SafeImage` for places where the runtime swap
// genuinely matters (hero, anywhere visible to the eye on first paint).

import Image from "next/image";
import { Newspaper } from "lucide-react";
import {
  isGeoblockedFromVercel,
  isUnusableUrl,
  resolveUrl,
} from "@/lib/imageFilters";

export default function SafeImageStatic({
  src,
  alt = "تصویر خبر",
  className,
  placeholderClass,
  // Default sized for typical homepage / story-card slots (~200-256px on
  // desktop, half-viewport on mobile). The previous "100vw, 50vw" default
  // was making Vercel's optimizer fetch the 640w-or-wider variant for
  // 200px cards (3-5x oversized per Lighthouse). Callers that render at
  // hero size should pass `sizes="100vw"` explicitly.
  sizes = "(max-width: 640px) 50vw, 256px",
  priority = false,
  quality = 65,
}: {
  src: string | null;
  alt?: string;
  className?: string;
  placeholderClass?: string;
  sizes?: string;
  priority?: boolean;
  /** WebP quality. 65 is the sweet spot for cards on small displays — Lighthouse's
   *  "Improve image delivery" pass flagged the homepage cards as oversized; this
   *  trims ~10-15% per file vs the next/image default of 75 with no visible diff
   *  on phone screens. Hero stays at SafeImage's default (70). */
  quality?: number;
}) {
  if (isUnusableUrl(src)) {
    return (
      <div className={placeholderClass || "flex h-full w-full items-center justify-center bg-slate-100 dark:bg-slate-800"}>
        <Newspaper className="h-10 w-10 text-slate-300 dark:text-slate-700" />
      </div>
    );
  }

  const resolved = resolveUrl(src!);
  const skipOptimization = isGeoblockedFromVercel(resolved);

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
        unoptimized={skipOptimization}
      />
    </div>
  );
}
