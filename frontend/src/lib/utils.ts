import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { StateAlignment } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const alignmentColors: Record<StateAlignment, string> = {
  state: "bg-state text-white",
  semi_state: "bg-semi-state text-white",
  independent: "bg-independent text-white",
  diaspora: "bg-diaspora text-white",
};

export const alignmentBadgeClasses: Record<StateAlignment, string> = {
  state: "badge-state",
  semi_state: "badge-semi-state",
  independent: "badge-independent",
  diaspora: "badge-diaspora",
};

export const alignmentLabels: Record<StateAlignment, { en: string; fa: string }> = {
  state: { en: "State", fa: "دولتی" },
  semi_state: { en: "Semi-State", fa: "نیمه‌دولتی" },
  independent: { en: "Independent", fa: "مستقل" },
  diaspora: { en: "Diaspora", fa: "اپوزیسیون" },
};

/** Convert English digits to Farsi digits */
export function toFa(n: number | string): string {
  return String(n).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[parseInt(d)]);
}

export function formatRelativeTime(dateStr: string, locale: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (locale === "fa") {
    if (diffMin < 1) return "لحظاتی پیش";
    if (diffMin < 60) return `${toFa(diffMin)} دقیقه پیش`;
    if (diffHr < 24) return `${toFa(diffHr)} ساعت پیش`;
    if (diffDay < 7) return `${toFa(diffDay)} روز پیش`;
    return date.toLocaleDateString("fa-IR");
  }

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function biasAlignmentLabel(value: number, _locale?: string): string {
  if (value < -0.6) return "محافظه‌کار";
  if (value < -0.2) return "نزدیک به حکومت";
  if (value <= 0.2) return "میانه";
  if (value <= 0.6) return "نزدیک به اپوزیسیون";
  return "اپوزیسیون";
}
