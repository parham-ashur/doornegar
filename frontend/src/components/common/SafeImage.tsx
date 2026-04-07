"use client";

import { useState } from "react";
import { Newspaper } from "lucide-react";

export default function SafeImage({
  src,
  className,
  placeholderClass,
}: {
  src: string | null;
  className?: string;
  placeholderClass?: string;
}) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className={placeholderClass || "flex h-full w-full items-center justify-center bg-slate-100 dark:bg-slate-800"}>
        <Newspaper className="h-10 w-10 text-slate-300 dark:text-slate-700" />
      </div>
    );
  }

  return (
    <img
      src={src}
      alt=""
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
