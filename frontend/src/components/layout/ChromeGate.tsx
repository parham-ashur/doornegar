"use client";

import type { ReactNode } from "react";

// Cycle-1 audit (Parham 2026-05-07): the only routes that hid chrome
// were the stories-carousel experiment (`/stories-beta` and
// `/lab/stories-carousel`). Both were removed; this gate now passes
// through unconditionally. Keeping the component as a stable mount
// point in case a new "chrome-less" experiment lands later.
export default function ChromeGate({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
