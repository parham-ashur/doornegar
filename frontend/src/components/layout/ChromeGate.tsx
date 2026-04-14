"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Patterns where chrome (header, footer, atmosphere) should be HIDDEN entirely on all viewports.
const HIDE_EVERYWHERE = [/\/stories-beta(\/|$)/];

// Patterns where chrome should be hidden on MOBILE only — the mobile stories carousel
// takes over the viewport with its own integrated brand bar, but desktop still needs
// the normal header/footer.
const HIDE_ON_MOBILE = [/^\/(?:fa|en)?\/?$/];

export default function ChromeGate({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "";
  if (HIDE_EVERYWHERE.some((re) => re.test(pathname))) return null;
  if (HIDE_ON_MOBILE.some((re) => re.test(pathname))) {
    // Tailwind: hidden on mobile, revert to default display at md+
    return <div className="hidden md:contents">{children}</div>;
  }
  return <>{children}</>;
}
