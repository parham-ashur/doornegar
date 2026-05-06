"use client";

import Link from "next/link";
import { useLocale } from "next-intl";
import { usePathname } from "next/navigation";
import { advertisedLocales, type Locale } from "@/i18n";

const LABELS: Record<Locale, string> = {
  fa: "فارسی",
  en: "English",
  fr: "Français",
};

export default function LocaleSwitcher() {
  const locale = useLocale();
  const pathname = usePathname() || "/";
  const pathWithoutLocale = pathname.replace(/^\/(fa|en|fr)(?=\/|$)/, "");

  return (
    <nav aria-label="Language" className="flex items-center gap-2 text-xs">
      {advertisedLocales.map((loc, i) => (
        <span key={loc} className="flex items-center gap-2">
          {i > 0 && (
            <span className="text-slate-300 dark:text-slate-700" aria-hidden>
              ·
            </span>
          )}
          {loc === locale ? (
            <span className="font-medium text-slate-900 dark:text-slate-100">
              {LABELS[loc]}
            </span>
          ) : (
            <Link
              href={`/${loc}${pathWithoutLocale}`}
              hrefLang={loc}
              className="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              {LABELS[loc]}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
