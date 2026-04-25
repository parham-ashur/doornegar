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
  sizes = "(max-width: 768px) 100vw, 50vw",
  priority = false,
}: {
  src: string | null;
  alt?: string;
  className?: string;
  placeholderClass?: string;
  sizes?: string;
  priority?: boolean;
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
        className={className || "object-cover"}
        unoptimized={skipOptimization}
      />
    </div>
  );
}
