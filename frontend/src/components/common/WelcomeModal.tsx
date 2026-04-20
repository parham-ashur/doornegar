"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";

const STORAGE_KEY = "doornegar_welcome_seen";

export default function WelcomeModal() {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);

  const isHomepage = pathname === "/" || pathname === "/fa" || pathname === "/en";

  useEffect(() => {
    setMounted(true);
    if (!isHomepage) return;
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("welcome") === "1") {
        setTimeout(() => setVisible(true), 400);
        return;
      }
      const seen = localStorage.getItem(STORAGE_KEY);
      if (!seen) {
        setTimeout(() => setVisible(true), 800);
      }
    } catch {}
  }, [isHomepage]);

  const close = () => {
    setVisible(false);
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {}
  };

  if (!mounted || !visible) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      onClick={close}
      dir="rtl"
    >
      <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm welcome-fade" />

      <div
        className="relative w-full max-w-2xl bg-white dark:bg-[#0a0e1a] border border-slate-200 dark:border-slate-800 shadow-2xl welcome-slide"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={close}
          aria-label="بستن"
          className="absolute top-3 left-3 p-2 text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors z-10"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="px-8 py-10 md:px-12 md:py-12">
          {/* Logo */}
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mb-2">
            دورنگر
          </h2>
          <p className="text-sm text-slate-400 dark:text-slate-500 mb-6">
            شفافیت رسانه‌ای ایران
          </p>

          {/* Mission + Ethos */}
          <div className="space-y-5 mb-10">
            <p className="text-base leading-7 text-slate-700 dark:text-slate-300">
              دورنگر یک پلتفرم مستقل برای مقایسه پوشش خبری رسانه‌های داخل و خارج ایران است. هدف ما این است که ببینید یک خبر چگونه از زوایای مختلف گزارش می‌شود.
            </p>
            <p className="text-[13px] leading-7 text-slate-500 dark:text-slate-400 border-r-2 border-slate-300 dark:border-slate-700 pr-4">
              ما به این باور داریم که حقیقت اغلب در میان روایت‌هاست، نه در یکی از آن‌ها. دورنگر نه طرفدار جناحی است و نه مخالف آن — فقط می‌خواهد چشم‌اندازی روشن از آنچه گفته می‌شود و آنچه پنهان می‌ماند به شما بدهد. هدف، دادن قدرت قضاوت به خود شما است، نه اینکه به جای شما قضاوت کنیم.
            </p>
          </div>

          {/* Bottom row: animation (left) + CTA (right) */}
          <div className="flex items-end justify-between gap-6">
            {/* Animation — small, bottom-left */}
            <div className="flex-shrink-0">
              <svg width="220" height="60" viewBox="0 0 220 60" className="overflow-visible">
                {/* Phase 1: scattered cards across full width */}
                <g className="stage-scatter">
                  <rect x="10" y="18" width="12" height="16" fill="#e2e8f0" className="card card-1" />
                  <rect x="28" y="14" width="12" height="16" fill="#cbd5e1" className="card card-2" />
                  <rect x="46" y="20" width="12" height="16" fill="#e2e8f0" className="card card-3" />
                  <rect x="64" y="12" width="12" height="16" fill="#cbd5e1" className="card card-4" />
                  <rect x="82" y="18" width="12" height="16" fill="#e2e8f0" className="card card-5" />
                  <rect x="100" y="14" width="12" height="16" fill="#cbd5e1" className="card card-6" />
                  <rect x="118" y="20" width="12" height="16" fill="#e2e8f0" className="card card-7" />
                  <rect x="136" y="12" width="12" height="16" fill="#cbd5e1" className="card card-8" />
                </g>

                {/* Phase 2: stacked cards on the right (RTL start) */}
                <g className="stage-stack">
                  <rect x="40" y="20" width="36" height="26" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="0.8" className="stack-1" />
                  <rect x="44" y="16" width="36" height="26" fill="#cbd5e1" stroke="#94a3b8" strokeWidth="0.8" className="stack-2" />
                  <rect x="48" y="12" width="36" height="26" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="0.8" className="stack-3" />
                </g>

                {/* Phase 3: summary lines — to the left of the stack, same width (36px) */}
                <g className="stage-summary">
                  <line x1="130" y1="18" x2="166" y2="18" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" className="summary-line-1" />
                  <line x1="130" y1="26" x2="166" y2="26" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" className="summary-line-2" />
                  <line x1="130" y1="34" x2="160" y2="34" stroke="#cbd5e1" strokeWidth="1.5" strokeLinecap="round" className="summary-line-3" />
                </g>
              </svg>
            </div>

            {/* CTA */}
            <button
              onClick={close}
              className="px-6 py-2.5 text-sm font-bold text-white bg-slate-900 dark:bg-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200 transition-colors whitespace-nowrap"
            >
              متوجه شدم
            </button>
          </div>
        </div>
      </div>

      <style>{`
        .welcome-fade {
          animation: welcome-fade-in 0.4s ease-out forwards;
        }
        .welcome-slide {
          animation: welcome-slide-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
          opacity: 0;
        }
        @keyframes welcome-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes welcome-slide-up {
          from { opacity: 0; transform: translateY(20px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }

        /* Each cycle is 5 seconds, loops infinitely */
        .card {
          opacity: 0;
          animation: card-cycle 5s ease-in-out infinite;
        }
        .card-1 { animation-delay: 0.0s; }
        .card-2 { animation-delay: 0.05s; }
        .card-3 { animation-delay: 0.1s; }
        .card-4 { animation-delay: 0.15s; }
        .card-5 { animation-delay: 0.2s; }
        .card-6 { animation-delay: 0.25s; }
        .card-7 { animation-delay: 0.3s; }
        .card-8 { animation-delay: 0.35s; }

        @keyframes card-cycle {
          0% { opacity: 0; transform: translateY(-6px); }
          8% { opacity: 1; transform: translateY(0); }
          35% { opacity: 1; transform: translateY(0); }
          45% { opacity: 0; transform: translateY(0); }
          100% { opacity: 0; }
        }

        .stack-1, .stack-2, .stack-3 {
          opacity: 0;
          animation: stack-cycle 5s cubic-bezier(0.16, 1, 0.3, 1) infinite;
        }
        .stack-1 { animation-delay: 0s; }
        .stack-2 { animation-delay: 0.1s; }
        .stack-3 { animation-delay: 0.2s; }

        @keyframes stack-cycle {
          0%, 45% { opacity: 0; transform: translateY(-8px) scale(0.9); }
          55% { opacity: 1; transform: translateY(0) scale(1); }
          80% { opacity: 1; transform: translateY(0) scale(1); }
          90%, 100% { opacity: 0; transform: translateY(0) scale(1); }
        }

        .summary-line-1, .summary-line-2, .summary-line-3 {
          stroke-dasharray: 50;
          animation: line-cycle 5s ease-in-out infinite;
        }
        .summary-line-1 { animation-delay: 0s; }
        .summary-line-2 { animation-delay: 0.15s; }
        .summary-line-3 { animation-delay: 0.3s; }

        @keyframes line-cycle {
          0%, 65% { stroke-dashoffset: 50; opacity: 1; }
          80% { stroke-dashoffset: 0; opacity: 1; }
          92% { stroke-dashoffset: 0; opacity: 1; }
          100% { stroke-dashoffset: 0; opacity: 0; }
        }
      `}</style>
    </div>
  );
}
