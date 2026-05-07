"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Menu, X } from "lucide-react";
import { useState, useEffect } from "react";
import HeaderAnimation from "./HeaderAnimation";
import LocaleSwitcher from "./LocaleSwitcher";

// Locale → Intl format string. Tehran is the universal anchor (the
// Iranian-news beat runs on Tehran clock), but the rendering of the
// date/time follows the reader's locale.
const INTL_TAG: Record<string, string> = {
  fa: "fa-IR",
  en: "en-US",
  fr: "fr-FR",
};

const TEHRAN_LABEL: Record<string, string> = {
  fa: "تهران",
  en: "Tehran",
  fr: "Téhéran",
};

function WorldClocks({ locale }: { locale: string }) {
  const [clocks, setClocks] = useState("");
  const tag = INTL_TAG[locale] ?? "en-US";
  const cityLabel = TEHRAN_LABEL[locale] ?? "Tehran";

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const time = new Intl.DateTimeFormat(tag, {
        hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tehran", hour12: false,
      }).format(now);
      const day = new Intl.DateTimeFormat(tag, {
        weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Tehran",
      }).format(now);
      setClocks(`${cityLabel} · ${day} · ${time}`);
    };
    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, [tag, cityLabel]);

  if (!clocks) return null;
  return <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{clocks}</span>;
}

export default function Header() {
  const locale = useLocale();
  const isRtl = locale === "fa";
  const tApp = useTranslations("app");
  const tHeader = useTranslations("header");
  const tNav = useTranslations("nav");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [animating, setAnimating] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setAnimating(false), 3200);
    return () => clearTimeout(timer);
  }, []);

  // navLinks defined for re-enabling later (desktop nav is currently
  // disabled per Parham 2026-04-26). Labels go through the i18n
  // dictionary so re-enabling auto-translates per locale.
  const navLinks = [
    { href: `/${locale}`, label: tNav("home") },
    { href: `/${locale}/stories`, label: tNav("stories") },
    { href: `/${locale}/sources`, label: tNav("sources") },
    { href: `/${locale}/blindspots`, label: tNav("blindspots") },
    { href: `/${locale}/lab`, label: "Lab" },
  ];

  return (
    <>
      <style>{`
        /* Logo zoom — direction is locale-driven via the
           --logo-start-x and --logo-origin-x CSS variables set on
           the link element. RTL: starts shifted right, fans in from
           visual end (logical start). LTR: mirrored — starts shifted
           left, fans in from visual start (logical start, again). */
        @keyframes doornegar-zoom {
          0%, 12% {
            transform: scale(16) translateX(var(--logo-start-x, 120%));
          }
          100% {
            transform: scale(1) translateX(0%);
          }
        }
        .logo-animate {
          animation: doornegar-zoom 3s cubic-bezier(0.33, 0, 0.15, 1) forwards;
          transform-origin: var(--logo-origin-x, 25%) center;
        }
        @keyframes header-fade-in {
          0%, 60% { opacity: 0; }
          100% { opacity: 1; }
        }
        .header-fade {
          animation: header-fade-in 3.2s ease forwards;
        }
      `}</style>
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-anthracite overflow-hidden">
      <div
        className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4"
        dir={isRtl ? "rtl" : "ltr"}
      >
        {/* Brand + tagline (logical-start side) */}
        <div className="flex items-center gap-3">
          <Link
            href={`/${locale}`}
            className="text-xl font-black text-slate-900 dark:text-white tracking-tight inline-block logo-animate"
            style={{
              ["--logo-start-x" as any]: isRtl ? "120%" : "-120%",
              ["--logo-origin-x" as any]: isRtl ? "25%" : "75%",
            }}
          >
            {tApp("name")}
          </Link>
          <span className="text-[13px] text-slate-400 dark:text-slate-500 header-fade hidden sm:inline">
            {tHeader("subtitle")}
          </span>
        </div>

        {/* Worker animation — saved in HeaderAnimation.saved.tsx, re-enable later */}
        {/* <HeaderAnimation /> */}

        {/* Desktop nav — kept disabled per Parham 2026-04-26.
            navLinks defined above so re-enabling is a paste-back of
            the <nav> + mobile hamburger + mobile <nav> blocks. */}

        {/* Logical-end side: locale switcher + Tehran date/time */}
        <div className="header-fade flex items-center gap-3">
          <LocaleSwitcher />
          <span className="text-slate-300 dark:text-slate-700" aria-hidden>·</span>
          <WorldClocks locale={locale} />
        </div>
      </div>
    </header>
    </>
  );
}
