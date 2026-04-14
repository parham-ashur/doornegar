"use client";

import { toFa } from "@/lib/utils";
import type { StoryCore } from "./types";

const LABELS = {
  rtl: {
    progressive: "روایت اپوزیسیون",
    conservative: "روایت محافظه‌کار",
    telegram: "تحلیل تلگرام",
    sources: (n: number) => `از ${toFa(n)} منبع`,
  },
  ltr: {
    progressive: "Opposition framing",
    conservative: "Conservative framing",
    telegram: "Telegram discussion",
    sources: (n: number) => `From ${n} sources`,
  },
};

type StoryContentPanelProps = {
  story: StoryCore;
  dir: "rtl" | "ltr";
};

export default function StoryContentPanel({ story, dir }: StoryContentPanelProps) {
  const L = dir === "rtl" ? LABELS.rtl : LABELS.ltr;
  const hasAny =
    story.progressivePosition || story.conservativePosition || story.telegramSummary;

  return (
    <div
      className="relative min-h-[100dvh] w-full bg-black/80 px-6 pt-24 pb-24 text-white"
      dir={dir}
      style={{
        WebkitBackdropFilter: "blur(14px)",
        backdropFilter: "blur(14px)",
      }}
    >
      {!hasAny && (
        <p className="text-center text-sm text-white/60">
          {dir === "rtl" ? "داده‌ای برای نمایش نیست." : "No content yet."}
        </p>
      )}

      {story.progressivePosition && (
        <Section label={L.progressive} body={story.progressivePosition} dir={dir} />
      )}
      {story.progressivePosition && story.conservativePosition && <Divider />}

      {story.conservativePosition && (
        <Section label={L.conservative} body={story.conservativePosition} dir={dir} />
      )}
      {story.conservativePosition && story.telegramSummary && <Divider />}

      {story.telegramSummary && (
        <Section label={L.telegram} body={story.telegramSummary} dir={dir} />
      )}

      {story.sourceCount !== undefined && (
        <>
          <Divider />
          <p
            className="mt-8 text-[11px] uppercase tracking-[0.3em] text-white/55"
            style={{ textAlign: dir === "rtl" ? "right" : "left" }}
          >
            {L.sources(story.sourceCount)}
          </p>
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
    <section
      className="py-5"
      style={{ textAlign: dir === "rtl" ? "right" : "left" }}
    >
      <div className="mb-3 text-[11px] uppercase tracking-[0.28em] text-white/60">
        {label}
      </div>
      <p className="text-[16px] leading-8 text-white/90">{body}</p>
    </section>
  );
}

function Divider() {
  return <div className="my-2 h-px w-full bg-white/10" />;
}
