"use client";

import Link from "next/link";
import { useLocale } from "next-intl";
import { Menu, X } from "lucide-react";
import { useState } from "react";

export default function Header() {
  const locale = useLocale();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navLinks = [
    { href: `/${locale}`, label: "خانه" },
    { href: `/${locale}/stories`, label: "خبرها" },
    { href: `/${locale}/sources`, label: "رسانه‌ها" },
    { href: `/${locale}/blindspots`, label: "نقاط کور" },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a0e1a]">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4" dir="rtl">
        {/* Logo */}
        <Link
          href={`/${locale}`}
          className="text-xl font-black text-slate-900 dark:text-white tracking-tight"
        >
          دورنگر
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="px-3 py-1.5 text-[13px] font-medium text-slate-500 transition-colors hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Mobile toggle */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="p-2 text-slate-500 dark:text-slate-400 md:hidden"
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile nav */}
      {mobileOpen && (
        <nav className="border-t border-slate-200 bg-white px-4 py-2 md:hidden dark:border-slate-800 dark:bg-[#0a0e1a]" dir="rtl">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className="block px-3 py-2.5 text-sm font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
