"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Patterns where chrome (header, footer, atmosphere) should be HIDDEN entirely on all viewports.
const HIDE_EVERYWHERE = [/\/stories-beta(\/|$)/, /\/lab\/stories-carousel(\/|$)/];

export default function ChromeGate({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "";
  if (HIDE_EVERYWHERE.some((re) => re.test(pathname))) return null;
  return <>{children}</>;
}
