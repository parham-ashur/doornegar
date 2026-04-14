"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const HIDE_CHROME_PATTERNS = [/\/stories-beta(\/|$)/];

export default function ChromeGate({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "";
  if (HIDE_CHROME_PATTERNS.some((re) => re.test(pathname))) return null;
  return <>{children}</>;
}
