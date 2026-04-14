"use client";

import { toFa } from "@/lib/utils";
import type { StoryCore, TelegramSlotData } from "./types";

type TelegramLayoutProps = {
  data: TelegramSlotData;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenClaimStory?: (story: StoryCore) => void;
};

const BRAND_ORANGE = "#E8913A";

const LABELS = {
  rtl: {
    eyebrow: "تحلیل روایت‌های تلگرام",
    predictions: "پیش‌بینی‌ها",
    claims: "ادعاهای کلیدی",
    analysts: "از تحلیلگران",
    verified: "تأیید شده",
    unverified: "تأیید نشده",
  },
  ltr: {
    eyebrow: "Telegram analysis",
    predictions: "Predictions",
    claims: "Key claims",
    analysts: "of analysts",
    verified: "Verified",
    unverified: "Unverified",
  },
};

export default function TelegramLayout({ data, active, dir, onOpenClaimStory }: TelegramLayoutProps) {
  // Always RTL per spec — but we still accept dir prop for consistency; ignore for Telegram UI layout.
  const L = LABELS.rtl;

  return (
    <div
      className="relative h-full w-full overflow-y-auto overflow-x-hidden bg-[#0a0e1a]"
      dir="rtl"
    >
      {/* Dark CSS pattern — subtle dot grid */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.15]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.3) 1px, transparent 0)",
          backgroundSize: "16px 16px",
        }}
      />
      {/* Warm ambient glow at top */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-48 opacity-30"
        style={{
          background: `radial-gradient(ellipse at top, ${BRAND_ORANGE}40, transparent 60%)`,
        }}
      />

      <div className="relative z-10 px-6 pt-[calc(env(safe-area-inset-top,0px)+5rem)] pb-16">
        <div className="mb-10 text-center text-[10px] uppercase tracking-[0.35em] text-white/60">
          {L.eyebrow}
        </div>

        {/* Predictions section */}
        {data.predictions.length > 0 && (
          <section className="mb-10">
            <SectionHeader label={L.predictions} />
            <div className="mt-5 space-y-5">
              {data.predictions.map((p, i) => (
                <div key={i}>
                  <p className="text-[15px] leading-[1.85] text-white/90">{p.text}</p>
                  {p.percent !== undefined && (
                    <p className="mt-1 text-[12px] tracking-wide text-white/50">
                      {toFa(p.percent)}٪ {L.analysts}
                    </p>
                  )}
                  {i < data.predictions.length - 1 && (
                    <div className="mt-5 h-px w-full bg-white/10" />
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Claims section */}
        {data.claims.length > 0 && (
          <section>
            <SectionHeader label={L.claims} />
            <div className="mt-5 space-y-5">
              {data.claims.map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={c.story ? () => onOpenClaimStory?.(c.story!) : undefined}
                  className="block w-full text-right"
                >
                  <p className="text-[13px] font-bold text-white/70">{c.source}</p>
                  <p className="mt-1 text-[15px] leading-[1.85] text-white/90">
                    <span className="line-clamp-3">{c.text}</span>
                  </p>
                  <div className="mt-2">
                    <VerificationBadge verified={c.verified} dir="rtl" />
                  </div>
                  {i < data.claims.length - 1 && (
                    <div className="mt-5 h-px w-full bg-white/10" />
                  )}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3" dir="rtl">
      <div
        className="h-2 w-2 rounded-full"
        style={{ background: BRAND_ORANGE }}
      />
      <span
        className="text-[11px] font-bold uppercase tracking-[0.35em]"
        style={{ color: BRAND_ORANGE }}
      >
        {label}
      </span>
      <div
        className="h-px flex-1"
        style={{ background: `linear-gradient(90deg, ${BRAND_ORANGE}80, transparent)` }}
      />
    </div>
  );
}

function VerificationBadge({ verified, dir }: { verified?: boolean; dir: "rtl" | "ltr" }) {
  const L = LABELS.rtl;
  if (verified === undefined) return null;
  const label = verified ? L.verified : L.unverified;
  const color = verified ? "#34d399" : "#f87171";
  return (
    <span
      className="inline-block text-[10px] font-bold uppercase tracking-[0.25em]"
      style={{ color }}
    >
      {label}
    </span>
  );
}
