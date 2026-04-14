"use client";

type DesktopPreviewLayoutProps = {
  url: string;
  dir: "rtl" | "ltr";
};

const L = {
  rtl: {
    heading: "نمای دسکتاپ",
    hint: "در صفحه بزرگ‌تر چگونه دیده می‌شود",
    open: "باز کردن نسخه کامل",
  },
  ltr: {
    heading: "Desktop view",
    hint: "How it looks on a larger screen",
    open: "Open full desktop",
  },
};

export default function DesktopPreviewLayout({ url, dir }: DesktopPreviewLayoutProps) {
  const labels = dir === "rtl" ? L.rtl : L.ltr;

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      dir={dir}
      style={{ background: "linear-gradient(180deg, #0a0e1a 0%, #131926 60%, #0a0e1a 100%)" }}
    >
      {/* Heading area — right-aligned in RTL */}
      <div
        className="absolute top-[calc(env(safe-area-inset-top,0px)+4.25rem)] inset-x-5 z-10"
        style={{ textAlign: dir === "rtl" ? "right" : "left" }}
      >
        <h2 className="text-[24px] font-black text-white" style={{ lineHeight: 1.2 }}>
          {labels.heading}
        </h2>
        <p className="mt-1 text-[13px] text-white/60">{labels.hint}</p>
      </div>

      {/* Scaled iframe in a framed container */}
      <div className="absolute inset-x-5 bottom-[6.5rem] top-[calc(env(safe-area-inset-top,0px)+8.5rem)] overflow-hidden rounded-sm border border-white/15 shadow-2xl">
        {/* Inner wrapper scales a 1280×900 desktop viewport down to fit */}
        <div
          className="relative h-full w-full overflow-hidden bg-white"
          style={{ contain: "layout paint" }}
        >
          <iframe
            src={url}
            title={labels.heading}
            className="origin-top-left"
            style={{
              width: "1280px",
              height: "900px",
              // Scale depends on actual card size; using CSS variable-like sizing via calc
              transform: "scale(0.30)",
              transformOrigin: dir === "rtl" ? "top right" : "top left",
              border: "none",
              pointerEvents: "none",
            }}
            // Sandbox keeps the iframe isolated; we don't need script exec for a preview
            sandbox="allow-same-origin allow-scripts"
          />
          {/* Transparent swipe-capture overlay so horizontal gestures on the
              iframe still reach the carousel's pointer handlers. */}
          <div className="absolute inset-0" aria-hidden="true" />
        </div>
      </div>

      {/* Open-full button anchored at the bottom */}
      <div className="absolute inset-x-5 bottom-5 z-20 flex">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="pointer-events-auto mx-auto inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-[13px] font-bold uppercase tracking-[0.18em] text-slate-900"
          style={{ boxShadow: "0 10px 30px rgba(0,0,0,0.35)" }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.75">
            <path d="M3 13 L13 3 M7 3 H13 V9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{labels.open}</span>
        </a>
      </div>
    </div>
  );
}
