"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { Eye, Globe, Menu, X } from "lucide-react";
import { useState } from "react";

export default function Header() {
  const t = useTranslations();
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isRtl = locale === "fa";
  const otherLocale = locale === "fa" ? "en" : "fa";

  function switchLocale() {
    const segments = pathname.split("/");
    segments[1] = otherLocale;
    router.push(segments.join("/"));
  }

  const navLinks = [
    { href: `/${locale}`, label: t("nav.home") },
    { href: `/${locale}/stories`, label: t("nav.stories") },
    { href: `/${locale}/sources`, label: t("nav.sources") },
    { href: `/${locale}/blindspots`, label: t("nav.blindspots") },
    { href: `/${locale}/rate`, label: locale === "fa" ? "ارزیابی" : "Rate" },
    { href: `/${locale}/dashboard`, label: locale === "fa" ? "داشبورد" : "Dashboard" },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        {/* Logo */}
        <Link
          href={`/${locale}`}
          className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-white"
        >
          <Eye className="h-6 w-6 text-diaspora" />
          <span className={isRtl ? "font-persian" : "font-latin"}>
            {t("app.name")}
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Mobile menu */}
        <div className="flex items-center gap-2">
          {/* Language toggle hidden — Farsi only for now
          <button
            onClick={switchLocale}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <Globe className="h-4 w-4" />
            {t("common.language")}
          </button>
          */}

          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="rounded-lg p-2 text-slate-600 md:hidden dark:text-slate-400"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      {mobileOpen && (
        <nav className="border-t border-slate-200 bg-white px-4 py-3 md:hidden dark:border-slate-800 dark:bg-slate-950">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className="block rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
