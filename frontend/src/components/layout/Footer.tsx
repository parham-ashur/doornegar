import Link from "next/link";
import DoornegarAnimation from "@/components/common/DoornegarAnimation";

// Source-spectrum legend per DESIGN.md's Source Spectrum North Star.
// The 4-color taxonomy is the design's identity; making it legible to
// first-time visitors (especially skeptical academics + diaspora readers
// who haven't seen the badges in context yet) is one of the cheapest
// trust wins on the page.
const SPECTRUM = [
  { color: "bg-state", label_fa: "دولتی", label_en: "State" },
  { color: "bg-semi-state", label_fa: "نیمه‌دولتی", label_en: "Semi-State" },
  { color: "bg-independent", label_fa: "مستقل", label_en: "Independent" },
  { color: "bg-diaspora", label_fa: "برون‌مرزی", label_en: "Diaspora" },
];

export default function Footer({ locale }: { locale?: string }) {
  const isFa = locale !== "en";
  return (
    <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-anthracite" dir="rtl">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="flex flex-col-reverse md:flex-row items-center justify-between gap-6 md:gap-8">
          {/* Right (RTL): Animation + name */}
          <div className="flex items-center gap-4 shrink-0">
            <DoornegarAnimation size="footer" />
            <p className="text-2xl md:text-3xl font-black text-slate-900 dark:text-white">
              دورنگر
            </p>
          </div>

          {/* Left (RTL): description + spectrum legend + tags */}
          <div className="flex flex-col gap-3 text-center md:text-start">
            <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-500">
              سکوی شفافیت رسانه‌ای ایران — مقایسه پوشش خبری رسانه‌های داخل و خارج ایران.
              ببینید کدام رسانه چه خبری را پوشش داده و چه خبری را پنهان کرده.{" "}
              <Link href={`/${isFa ? "fa" : "en"}/sources`} className="underline decoration-slate-300 dark:decoration-slate-600 underline-offset-2 hover:text-slate-700 dark:hover:text-slate-300">
                روش‌شناسی و فهرست رسانه‌ها
              </Link>
            </p>

            {/* Source-spectrum legend — DESIGN.md's North Star made
                visible. Squares (no rounded — per spec). 8px box with
                12px label, hairline border for OLED legibility. */}
            <div className="flex items-center justify-center md:justify-start gap-3 flex-wrap text-[11px] text-slate-500 dark:text-slate-500" aria-label="طیف رسانه‌ای">
              {SPECTRUM.map((s) => (
                <span key={s.label_fa} className="inline-flex items-center gap-1.5">
                  <span className={`inline-block h-2 w-2 ${s.color}`} aria-hidden="true" />
                  {isFa ? s.label_fa : s.label_en}
                </span>
              ))}
            </div>

            <p className="text-[10px] leading-4 text-slate-400/60 dark:text-slate-600/60">
              ما هیچ اطلاعاتی از بازدیدکنندگان ذخیره نمی‌کنیم. بدون کوکی ردیابی، بدون تحلیل رفتار، بدون اشتراک‌گذاری داده. حریم خصوصی شما برای ما مهم است.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
