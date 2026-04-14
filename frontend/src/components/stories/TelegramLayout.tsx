"use client";

import { toFa } from "@/lib/utils";
import type { StoryCore, TelegramSlotData } from "./types";

const BRAND_ORANGE = "#E8913A";

type TelegramLayoutProps = {
  data: TelegramSlotData;
  active: boolean;
  dir: "rtl" | "ltr";
  onOpenClaimStory?: (story: StoryCore) => void;
};

const L = {
  eyebrow: "تحلیل تلگرام",
  predictions: "پیش‌بینی‌ها",
  claims: "ادعاهای کلیدی",
  analysts: "از تحلیلگران",
  verified: "تأیید شده",
  unverified: "تأیید نشده",
};

export default function TelegramLayout({ data, onOpenClaimStory }: TelegramLayoutProps) {
  const predictions = data.predictions.slice(0, 2);
  const claims = data.claims.slice(0, 2);

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      dir="rtl"
      style={{
        background: "linear-gradient(180deg, #0a0e1a 0%, #131218 40%, #1a1620 100%)",
      }}
    >
      {/* Dot pattern */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.10]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.3) 1px, transparent 0)",
          backgroundSize: "18px 18px",
        }}
      />
      {/* Warm ambient glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-56 opacity-25"
        style={{
          background: `radial-gradient(ellipse at top, ${BRAND_ORANGE}55, transparent 70%)`,
        }}
      />

      {/* Full-height flex column that distributes content to fill the viewport
          without overflow. */}
      <div
        className="relative z-10 flex h-full flex-col px-5 pb-5"
        style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 4.5rem)" }}
      >
        {/* Heading — right-aligned (دورنگر stays top-left in the carousel bar) */}
        <h2 className="mb-5 shrink-0 text-right text-[22px] font-black text-white">
          {L.eyebrow}
        </h2>

        {/* Predictions — flex-grow so predictions + claims share remaining space */}
        {predictions.length > 0 && (
          <section className="mb-4 flex flex-1 flex-col">
            <SectionHeader label={L.predictions} />
            <ul className="mt-3 flex flex-1 flex-col justify-around">
              {predictions.map((p, i) => (
                <PredictionItem key={i} text={p.text} analystPercent={p.analystPercent} />
              ))}
            </ul>
          </section>
        )}

        {/* Claims — also flex-grow, sharing space equally with predictions */}
        {claims.length > 0 && (
          <section className="flex flex-1 flex-col">
            <SectionHeader label={L.claims} />
            <ul className="mt-3 flex flex-1 flex-col justify-around">
              {claims.map((c, i) => (
                <ClaimItem
                  key={i}
                  source={c.source}
                  text={c.text}
                  verified={c.verified}
                  onOpen={c.story ? () => onOpenClaimStory?.(c.story!) : undefined}
                />
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function PredictionItem({ text, analystPercent }: { text: string; analystPercent?: number }) {
  return (
    <li>
      <p className="text-[14px] leading-[1.75] text-white/90 line-clamp-3">{text}</p>
      {analystPercent !== undefined && (
        // dir=ltr on the wrapper + justify-start pushes the label to the physical LEFT
        <div className="mt-1 flex" dir="ltr" style={{ justifyContent: "flex-start" }}>
          <span className="text-[11px] font-bold text-white/50" dir="ltr">
            {toFa(analystPercent)}٪ {L.analysts}
          </span>
        </div>
      )}
    </li>
  );
}

function ClaimItem({
  source,
  text,
  verified,
  onOpen,
}: {
  source: string;
  text: string;
  verified?: boolean;
  onOpen?: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="block w-full text-right disabled:cursor-default"
        disabled={!onOpen}
      >
        <p className="mb-0.5 text-[11px] font-bold text-white/60">{source}</p>
        <p className="text-[14px] leading-[1.75] text-white/90 line-clamp-3">{text}</p>
        {verified !== undefined && (
          // Badge anchored physically LEFT via dir=ltr + flex-start
          <div className="mt-1 flex" dir="ltr" style={{ justifyContent: "flex-start" }}>
            <span
              className="text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: verified ? "#34d399" : "#f87171" }}
            >
              {verified ? L.verified : L.unverified}
            </span>
          </div>
        )}
      </button>
    </li>
  );
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="flex shrink-0 items-center gap-2" dir="rtl">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: BRAND_ORANGE }} />
      <span
        className="text-[12px] font-black uppercase tracking-[0.28em]"
        style={{ color: BRAND_ORANGE }}
      >
        {label}
      </span>
      <span
        className="h-px flex-1"
        style={{ background: `linear-gradient(90deg, ${BRAND_ORANGE}55, transparent)` }}
      />
    </div>
  );
}
