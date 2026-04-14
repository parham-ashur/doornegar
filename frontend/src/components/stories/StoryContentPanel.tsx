"use client";

import { toFa } from "@/lib/utils";
import type { StoryCore } from "./types";

const BRAND_ORANGE = "#E8913A";

const LABELS = {
  rtl: {
    coverage: "پوشش رسانه‌ای",
    conservativeSide: "محافظه‌کار",
    oppositionSide: "اپوزیسیون",
    progressive: "روایت اپوزیسیون",
    conservative: "روایت محافظه‌کار",
    telegram: "تحلیل تلگرام",
    predictions: "پیش‌بینی‌ها",
    claims: "ادعاهای کلیدی",
    unverified: "تأیید نشده",
    verified: "تأیید شده",
    sources: (n: number) => `از ${toFa(n)} منبع`,
  },
  ltr: {
    coverage: "Coverage",
    conservativeSide: "Conservative",
    oppositionSide: "Opposition",
    progressive: "Opposition framing",
    conservative: "Conservative framing",
    telegram: "Telegram discussion",
    predictions: "Predictions",
    claims: "Key claims",
    unverified: "Unverified",
    verified: "Verified",
    sources: (n: number) => `From ${n} sources`,
  },
};

type StoryContentPanelProps = {
  story: StoryCore;
  dir: "rtl" | "ltr";
};

export default function StoryContentPanel({ story, dir }: StoryContentPanelProps) {
  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;
  const hasBias =
    (story.statePct !== undefined && story.statePct > 0) ||
    (story.diasporaPct !== undefined && story.diasporaPct > 0);
  const hasFraming = story.progressivePosition || story.conservativePosition;
  const hasTelegram =
    story.telegramSummary ||
    (story.telegramPredictions && story.telegramPredictions.length > 0) ||
    (story.telegramClaims && story.telegramClaims.length > 0);
  const hasAny = hasBias || hasFraming || hasTelegram;

  return (
    <div
      className="relative min-h-[100dvh] w-full px-6 pt-10 pb-28 text-white"
      dir={dir}
      style={{
        // Gradient transparency — very see-through at the top, darker below
        // so body text stays readable once the reader has scrolled.
        background:
          "linear-gradient(180deg, rgba(12,14,22,0.10) 0%, rgba(12,14,22,0.55) 30%, rgba(12,14,22,0.78) 60%, rgba(12,14,22,0.88) 100%)",
        WebkitBackdropFilter: "blur(28px) saturate(180%)",
        backdropFilter: "blur(28px) saturate(180%)",
      }}
    >
      {/* Feather above the panel so the glass effect bleeds into the image
          without a seam at the top edge. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 -top-48 h-48"
        style={{
          WebkitBackdropFilter: "blur(28px) saturate(180%)",
          backdropFilter: "blur(28px) saturate(180%)",
          background: "linear-gradient(to top, rgba(12,14,22,0.10), rgba(12,14,22,0))",
          maskImage: "linear-gradient(to top, black, transparent)",
          WebkitMaskImage: "linear-gradient(to top, black, transparent)",
        }}
      />
      {!hasAny && (
        <p className="text-center text-sm text-white/60">
          {dir === "rtl" ? "داده‌ای برای نمایش نیست." : "No content yet."}
        </p>
      )}

      {/* Coverage percentages are shown as an overlay on the story image
          (see StoryLayout) — the panel focuses on the narratives below. */}

      {story.progressivePosition && (
        <Section label={L.progressive} body={story.progressivePosition} dir={dir} />
      )}
      {story.progressivePosition && story.conservativePosition && <Divider />}

      {story.conservativePosition && (
        <Section label={L.conservative} body={story.conservativePosition} dir={dir} />
      )}
      {(story.conservativePosition || story.progressivePosition) && hasTelegram && <Divider />}

      {hasTelegram && (
        <TelegramSection
          labels={{
            heading: L.telegram,
            predictions: L.predictions,
            claims: L.claims,
            unverified: L.unverified,
            verified: L.verified,
          }}
          summary={story.telegramSummary}
          predictions={story.telegramPredictions ?? []}
          claims={story.telegramClaims ?? []}
          dir={dir}
        />
      )}

      {story.sourceCount !== undefined && (
        <>
          <Divider />
          <div
            className="mt-10 space-y-2"
            style={{ textAlign: dir === "rtl" ? "right" : "left" }}
          >
            <p className="text-[13px] font-bold uppercase tracking-[0.3em] text-white/60">
              {L.sources(story.sourceCount)}
            </p>
            {story.sourceNames && story.sourceNames.length > 0 && (
              <p className="text-[15px] leading-[1.9] text-white/80">
                {story.sourceNames.join("، ")}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Section({
  label,
  body,
  dir,
}: {
  label: string;
  body: string;
  dir: "rtl" | "ltr";
}) {
  return (
    <section className="py-6" style={{ textAlign: dir === "rtl" ? "right" : "left" }}>
      <div className="mb-4 text-[13px] font-bold uppercase tracking-[0.28em] text-white/70">
        {label}
      </div>
      <p className="text-[18px] leading-[1.95] text-white/92">{body}</p>
    </section>
  );
}

function CoverageSection({
  label,
  conservativeLabel,
  oppositionLabel,
  statePct,
  diasporaPct,
  dir,
}: {
  label: string;
  conservativeLabel: string;
  oppositionLabel: string;
  statePct: number;
  diasporaPct: number;
  dir: "rtl" | "ltr";
}) {
  const total = Math.max(1, statePct + diasporaPct);
  const leftPct = (statePct / total) * 100;
  const rightPct = (diasporaPct / total) * 100;
  const fmt = (n: number) => (dir === "rtl" ? `${toFa(Math.round(n))}٪` : `${Math.round(n)}%`);

  return (
    <section className="py-6" style={{ textAlign: dir === "rtl" ? "right" : "left" }}>
      <div className="mb-4 text-[13px] font-bold uppercase tracking-[0.28em] text-white/70">
        {label}
      </div>
      <div className="flex items-baseline justify-between text-[16px] font-bold mb-3">
        <span className="text-blue-300">
          {conservativeLabel} <span className="font-black text-[20px]">{fmt(statePct)}</span>
        </span>
        <span style={{ color: BRAND_ORANGE }}>
          <span className="font-black text-[20px]">{fmt(diasporaPct)}</span> {oppositionLabel}
        </span>
      </div>
      <div className="flex h-[8px] w-full overflow-hidden rounded-full bg-white/10">
        <div className="h-full bg-blue-400/80" style={{ width: `${leftPct}%` }} />
        <div className="h-full" style={{ width: `${rightPct}%`, background: BRAND_ORANGE }} />
      </div>
    </section>
  );
}

function TelegramSection({
  labels,
  summary,
  predictions,
  claims,
  dir,
}: {
  labels: {
    heading: string;
    predictions: string;
    claims: string;
    unverified: string;
    verified: string;
  };
  summary?: string;
  predictions: string[];
  claims: { source?: string; text: string; verified?: boolean }[];
  dir: "rtl" | "ltr";
}) {
  return (
    <section className="py-6" style={{ textAlign: dir === "rtl" ? "right" : "left" }}>
      <div className="mb-4 text-[13px] font-bold uppercase tracking-[0.28em] text-white/70">
        {labels.heading}
      </div>

      {summary && <p className="text-[18px] leading-[1.95] text-white/92">{summary}</p>}

      {predictions.length > 0 && (
        <div className="mt-8">
          <div className="mb-4 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: BRAND_ORANGE }} />
            <span
              className="text-[12px] font-black uppercase tracking-[0.28em]"
              style={{ color: BRAND_ORANGE }}
            >
              {labels.predictions}
            </span>
          </div>
          <ul className="space-y-4">
            {predictions.map((p, i) => (
              <li key={i} className="text-[16px] leading-[1.9] text-white/88">
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {claims.length > 0 && (
        <div className="mt-8">
          <div className="mb-4 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: BRAND_ORANGE }} />
            <span
              className="text-[12px] font-black uppercase tracking-[0.28em]"
              style={{ color: BRAND_ORANGE }}
            >
              {labels.claims}
            </span>
          </div>
          <ul className="space-y-6">
            {claims.map((c, i) => (
              <li key={i}>
                {c.source && (
                  <p className="mb-1.5 text-[14px] font-bold text-white/70">{c.source}</p>
                )}
                <p className="text-[16px] leading-[1.9] text-white/88">{c.text}</p>
                {/* Badge LEFT-aligned per request */}
                {c.verified !== undefined && (
                  <div className="mt-2 flex">
                    <span
                      className="text-[11px] font-bold uppercase tracking-[0.25em]"
                      style={{ color: c.verified ? "#34d399" : "#f87171" }}
                    >
                      {c.verified ? labels.verified : labels.unverified}
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Divider() {
  return <div className="my-2 h-px w-full bg-white/10" />;
}
