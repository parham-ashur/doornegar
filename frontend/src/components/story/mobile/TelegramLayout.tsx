"use client";

import type { MobileStorySlot } from "./types";

const CRED_LABEL_FA: Record<string, { text: string; cls: string }> = {
  verified: { text: "تأیید شده", cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  suspect: { text: "مشکوک", cls: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  unverified: { text: "تأیید نشده", cls: "bg-slate-500/20 text-slate-300 border-slate-500/40" },
};

const CRED_LABEL_EN: Record<string, { text: string; cls: string }> = {
  verified: { text: "verified", cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  suspect: { text: "suspect", cls: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  unverified: { text: "unverified", cls: "bg-slate-500/20 text-slate-300 border-slate-500/40" },
};

interface TelegramLayoutProps {
  slot: MobileStorySlot;
  isRtl?: boolean;
  onOpen?: () => void;
}

export default function TelegramLayout({ slot, isRtl = true, onOpen }: TelegramLayoutProps) {
  const t = slot.telegram;
  if (!t) return null;
  const title = isRtl ? slot.title_fa : slot.title_en;
  const credMap = isRtl ? CRED_LABEL_FA : CRED_LABEL_EN;

  return (
    <div
      className="relative h-full w-full overflow-y-auto bg-[#0a0e1a] px-6 py-10 text-slate-100"
      dir={isRtl ? "rtl" : "ltr"}
      onClick={onOpen}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
    >
      <span className="inline-block border border-sky-500/40 bg-sky-500/10 px-2 py-0.5 text-[10px] font-bold text-sky-300">
        {isRtl ? "تلگرام" : "Telegram"}
      </span>
      <h2 className="mt-3 text-[22px] font-black leading-tight">{title}</h2>

      <section className="mt-7">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
          {isRtl ? "پیش‌بینی‌ها" : "Predictions"}
        </h3>
        <ul className="mt-3 space-y-2">
          {t.predictions_fa.map((p, i) => (
            <li
              key={i}
              className="border-l-2 border-sky-500/60 bg-sky-500/5 px-3 py-2 text-[14px] leading-7"
            >
              {p}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-7 pb-12">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
          {isRtl ? "ادعاهای کلیدی" : "Key claims"}
        </h3>
        <ul className="mt-3 space-y-2">
          {t.claims.map((c, i) => {
            const cred = c.credibility ? credMap[c.credibility] : null;
            return (
              <li key={i} className="border border-slate-700/60 bg-slate-800/30 px-3 py-2.5">
                <p className="text-[14px] leading-7 text-slate-100">{c.text_fa}</p>
                {cred && (
                  <span className={`mt-2 inline-block border px-2 py-0.5 text-[10px] font-bold ${cred.cls}`}>
                    {cred.text}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
