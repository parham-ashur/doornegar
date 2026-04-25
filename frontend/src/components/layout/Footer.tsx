import DoornegarAnimation from "@/components/common/DoornegarAnimation";

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0a0e1a]" dir="rtl">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="flex flex-col-reverse md:flex-row items-center justify-between gap-6 md:gap-8">
          {/* Right (RTL): Animation + name */}
          <div className="flex items-center gap-4 shrink-0">
            <DoornegarAnimation size="footer" />
            <p className="text-2xl md:text-3xl font-black text-slate-900 dark:text-white">
              دورنگر
            </p>
          </div>

          {/* Left (RTL): description + tags */}
          <div className="flex flex-col gap-2 text-center md:text-start">
            <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-500">
              سکوی شفافیت رسانه‌ای ایران — مقایسه پوشش خبری رسانه‌های داخل و خارج ایران.
              ببینید کدام رسانه چه خبری را پوشش داده و چه خبری را پنهان کرده.
            </p>
            <p className="text-[10px] leading-4 text-slate-400/60 dark:text-slate-600/60 mt-2">
              ما هیچ اطلاعاتی از بازدیدکنندگان ذخیره نمی‌کنیم. بدون کوکی ردیابی، بدون تحلیل رفتار، بدون اشتراک‌گذاری داده. حریم خصوصی شما برای ما مهم است.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
