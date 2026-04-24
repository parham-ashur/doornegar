"use client";

import Link from "next/link";

/**
 * Shared tab header for the two user-feedback queues:
 *   - Issue reports (improvements): bugs + wrong titles + bad images
 *     posted from rate pages against specific stories/articles
 *   - New-outlet suggestions (suggestions): "please add this RSS feed
 *     or Telegram channel" proposals from the /submit form
 *
 * Mounted at the top of both pages so the curator sees them as one
 * unified feedback area. Data shapes differ, so they stay as two
 * distinct routes — this header just bridges the UX.
 */
export default function FeedbackTabs({ active }: { active: "issues" | "suggestions" }) {
  return (
    <div className="flex items-center gap-0 border-b border-slate-200 dark:border-slate-800 mb-4 -mx-4 px-4">
      <Tab
        href="/fa/dashboard/improvements"
        label="Issue reports"
        active={active === "issues"}
      />
      <Tab
        href="/fa/dashboard/suggestions"
        label="New-outlet suggestions"
        active={active === "suggestions"}
      />
      <div className="ml-auto text-[11px] text-slate-400 self-center">
        Both come from user feedback forms.
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
