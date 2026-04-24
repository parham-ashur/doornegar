"use client";

import Link from "next/link";

/**
 * Shared tab header for the two outlet-classification pages (RSS
 * sources + Telegram channels). Mounted at the top of both
 * /hitl/sources and /hitl/channels so the curator sees them as one
 * unified "outlets" area without a code-level merge — data shapes
 * and save endpoints are different enough that a single page would
 * get bloated.
 */
export default function OutletTabs({ active }: { active: "sources" | "channels" }) {
  return (
    <div className="flex items-center gap-0 border-b border-slate-200 dark:border-slate-800 mb-4 -mx-4 px-4">
      <Tab href="/fa/dashboard/hitl/sources" label="Sources (RSS)" active={active === "sources"} />
      <Tab href="/fa/dashboard/hitl/channels" label="Channels (Telegram)" active={active === "channels"} />
      <div className="ml-auto text-[11px] text-slate-400 self-center">
        Both feed the 4-subgroup taxonomy.
      </div>
    </div>
  );
}

function Tab({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className={`text-[13px] px-4 py-2 -mb-px border-b-2 ${
        active
          ? "border-blue-500 text-blue-600 dark:text-blue-400 font-black"
          : "border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-white"
      }`}
    >
      {label}
    </Link>
  );
}
