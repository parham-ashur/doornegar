"use client";

import Link from "next/link";
import { useLocale } from "next-intl";
import { Menu, X } from "lucide-react";
import { useState, useEffect } from "react";
import HeaderAnimation from "./HeaderAnimation";

function WorldClocks() {
  const [clocks, setClocks] = useState("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const time = new Intl.DateTimeFormat("fa-IR", {
        hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tehran", hour12: false,
      }).format(now);
      const day = new Intl.DateTimeFormat("fa-IR", {
        weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Tehran",
      }).format(now);
      setClocks(`تهران · ${day} · ${time}`);
    };
    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, []);

  if (!clocks) return null;
  return <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{clocks}</span>;
}

export default function Header() {
  const locale = useLocale();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [animating, setAnimating] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setAnimating(false), 3200);
    return () => clearTimeout(timer);
  }, []);

  const navLinks = [
    { href: `/${locale}`, label: "خانه" },
    { href: `/${locale}/stories`, label: "خبرها" },
    { href: `/${locale}/sources`, label: "رسانه‌ها" },
    { href: `/${locale}/blindspots`, label: "نگاه یک‌جانبه" },
    { href: `/${locale}/lab`, label: "آزمایشگاه" },
  ];

  return (
    <>
      <style>{`
        @keyframes doornegar-zoom {
          0%, 12% {
            transform: scale(16) translateX(120%);
          }
          100% {
            transform: scale(1) translateX(0%);
          }
        }
        .logo-animate {
          animation: doornegar-zoom 3s cubic-bezier(0.33, 0, 0.15, 1) forwards;
          transform-origin: 25% center;
        }
        @keyframes header-fade-in {
          0%, 60% { opacity: 0; }
          100% { opacity: 1; }
        }
        .header-fade {
          animation: header-fade-in 3.2s ease forwards;
        }
      `}</style>
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a0e1a] overflow-hidden">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4" dir="rtl">
        {/* Logo + tagline */}
        <div className="flex items-center gap-3">
          <Link
            href={`/${locale}`}
            className="text-xl font-black text-slate-900 dark:text-white tracking-tight inline-block logo-animate"
          >
            دورنگر
          </Link>
          <span className="text-[13px] text-slate-400 dark:text-slate-500 header-fade hidden sm:inline">
            اخبار رسانه‌های فارسی‌زبان را گردآوری و تحلیل می‌کند
          </span>
        </div>

        {/* Worker animation — saved in HeaderAnimation.saved.tsx, re-enable later */}
        {/* <HeaderAnimation /> */}

        {/* Desktop nav — kept disabled per Parham 2026-04-26.
            navLinks defined above so re-enabling is a paste-back of
            the <nav> + mobile hamburger + mobile <nav> blocks. */}

        {/* Tehran date/time — left side */}
        <div className="header-fade">
          <WorldClocks />
        </div>
      </div>
    </header>
    </>
  );
}
