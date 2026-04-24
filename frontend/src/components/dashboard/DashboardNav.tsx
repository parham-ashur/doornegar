"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Top-nav for the admin dashboard. Keeps the routing flat: every page
 * is one click deep. Grouped loosely by frequency — Overview +
 * Review Queue are the daily working pages, the HITL subpages sit
 * behind "HITL" since they're more specialized, and the observability
 * pages (cost, fetch-stats, actions) cluster on the right.
 *
 * Text is English per the dashboard-English rule. Story titles and
 * other DB content rendered on a page may still be in Farsi.
 */
const NAV: { href: string; label: string; group?: "left" | "right" }[] = [
  { href: "/fa/dashboard/hub", label: "Overview" },
  { href: "/fa/dashboard/review-queue", label: "Review Queue" },
  { href: "/fa/dashboard/hitl", label: "HITL" },
  { href: "/fa/dashboard/edit-stories", label: "Story Editor" },
  { href: "/fa/dashboard/cost", label: "Cost", group: "right" },
  { href: "/fa/dashboard/fetch-stats", label: "Ingest", group: "right" },
  { href: "/fa/dashboard/actions", label: "Actions", group: "right" },
  { href: "/fa/dashboard", label: "Advanced", group: "right" },
];

export default function DashboardNav() {
  const pathname = usePathname();
  const isActive = (href: string) => {
    // Exact-match on /dashboard (now "Advanced") so it doesn't eat every
    // subpage. Prefix-match on everything else so deep pages keep their
    // parent tab highlighted.
    if (href === "/fa/dashboard") return pathname === "/fa/dashboard";
    return pathname === href || pathname.startsWith(href + "/");
  };
  const left = NAV.filter((n) => n.group !== "right");
  const right = NAV.filter((n) => n.group === "right");

  return (
    <nav
      dir="ltr"
      className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 sticky top-0 z-20"
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between px-4 h-11">
        <div className="flex items-center gap-1">
          <Link
            href="/fa/dashboard"
            className="text-[13px] font-black mr-3 text-slate-900 dark:text-white"
          >
            Doornegar Admin
          </Link>
          {left.map((n) => (
            <Item key={n.href} {...n} active={isActive(n.href)} />
          ))}
        </div>
        <div className="flex items-center gap-1">
          {right.map((n) => (
            <Item key={n.href} {...n} active={isActive(n.href)} />
          ))}
        </div>
      </div>
    </nav>
  );
}

function Item({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className={`text-[12px] px-2.5 py-1 border ${
        active
          ? "border-blue-500 text-blue-600 dark:text-blue-400 dark:border-blue-400"
          : "border-transparent text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700 hover:text-slate-900 dark:hover:text-white"
      }`}
    >
      {label}
    </Link>
  );
}
