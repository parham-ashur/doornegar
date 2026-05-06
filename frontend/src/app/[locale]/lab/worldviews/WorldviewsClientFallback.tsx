"use client";

// Browser-side fallback for /fa/lab/worldviews when the SSR fetch from
// Vercel→Railway returns a sustained 5xx. The browser→Railway path
// works for real users even when Vercel's egress is being rate-limited
// or briefly blocked (this happened on 2026-05-06 and the page sat on
// a cached 502 for ~30 min until each deploy bumped the cache).
//
// Renders the same 2×2 card layout as the server page. Kept in sync
// with WorldviewCardBox in page.tsx — when one changes, the other
// usually should too.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Bundle = "principlist" | "reformist" | "moderate_diaspora" | "radical_diaspora";

interface BeliefWithEvidence {
  text?: string;
  topic?: string;
  note?: string;
  article_count?: number;
  source_count?: number;
  example_article_ids?: string[];
}

interface ToneProfile {
  dominant?: string;
  alt?: string;
  description?: string;
}

interface Synthesis {
  core_beliefs?: BeliefWithEvidence[];
  emphasized?: BeliefWithEvidence[];
  absent?: BeliefWithEvidence[];
  tone_profile?: ToneProfile;
  predictions_primed?: BeliefWithEvidence[];
}

interface WorldviewCard {
  bundle: Bundle;
  bundle_label_fa: string;
  window_start: string;
  window_end: string;
  status: "ok" | "insufficient";
  article_count: number;
  source_count: number;
  coverage_pct: number;
  synthesis_fa: Synthesis | null;
  model_used: string | null;
  generated_at: string;
}

interface CurrentResponse {
  window_start: string | null;
  window_end: string | null;
  cards: WorldviewCard[];
}

const BUNDLE_THEME: Record<Bundle, { label: string; side: string; accentBorder: string; accentDot: string }> = {
  principlist: {
    label: "اصول‌گرا",
    side: "درون‌مرزی",
    accentBorder: "border-t-[#1e3a5f] dark:border-t-[#93c5fd]",
    accentDot: "bg-[#1e3a5f] dark:bg-[#93c5fd]",
  },
  reformist: {
    label: "اصلاح‌طلب",
    side: "درون‌مرزی",
    accentBorder: "border-t-[#4f7cac] dark:border-t-[#7ba3cf]",
    accentDot: "bg-[#4f7cac] dark:bg-[#7ba3cf]",
  },
  moderate_diaspora: {
    label: "میانه‌رو",
    side: "برون‌مرزی",
    accentBorder: "border-t-[#f97316] dark:border-t-[#fdba74]",
    accentDot: "bg-[#f97316] dark:bg-[#fdba74]",
  },
  radical_diaspora: {
    label: "رادیکال",
    side: "برون‌مرزی",
    accentBorder: "border-t-[#c2410c] dark:border-t-[#fb923c]",
    accentDot: "bg-[#c2410c] dark:bg-[#fb923c]",
  },
};

const GRID_ORDER: Bundle[] = ["principlist", "moderate_diaspora", "reformist", "radical_diaspora"];

function toFaDigits(n: number | string): string {
  const map = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  return String(n).replace(/[0-9]/g, (d) => map[Number(d)]);
}

async function clientFetch(): Promise<{ ok: true; data: CurrentResponse } | { ok: false; error: string }> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(`${API}/api/v1/worldviews/current`, { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as CurrentResponse;
        return { ok: true, data };
      }
      if (res.status < 500 || attempt === 2) {
        return { ok: false, error: `HTTP ${res.status} from API` };
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (attempt === 2) return { ok: false, error: `fetch failed: ${msg}` };
    }
    await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
  }
  return { ok: false, error: "exhausted retries" };
}

function CardSkeleton({ bundle }: { bundle: Bundle }) {
  const theme = BUNDLE_THEME[bundle];
  return (
    <div className={`border-t-[2px] ${theme.accentBorder} bg-white dark:bg-slate-900 p-5 animate-pulse`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 ${theme.accentDot}`} />
        <div className="h-6 w-32 bg-slate-200 dark:bg-slate-800" />
      </div>
      <div className="mt-3 ms-[18px] h-3 w-48 bg-slate-100 dark:bg-slate-800/60" />
      <div className="mt-8 space-y-2">
        <div className="h-3 w-full bg-slate-100 dark:bg-slate-800/60" />
        <div className="h-3 w-5/6 bg-slate-100 dark:bg-slate-800/60" />
        <div className="h-3 w-4/6 bg-slate-100 dark:bg-slate-800/60" />
      </div>
    </div>
  );
}

function BeliefParagraph({ item }: { item: BeliefWithEvidence }) {
  const text = item.text || item.topic || "";
  if (!text) return null;
  return (
    <div>
      <p className="text-[14.5px] leading-[1.85] text-slate-700 dark:text-slate-300">{text}</p>
      {item.note && (
        <p className="mt-1.5 text-[13px] leading-7 text-slate-500 dark:text-slate-400">{item.note}</p>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4
      className="text-[14px] font-bold text-slate-900 dark:text-slate-100 tracking-wide mt-7 pt-5 border-t border-slate-200 dark:border-slate-800 mb-3"
      style={{ textWrap: "pretty" } as React.CSSProperties}
    >
      {children}
    </h4>
  );
}

function CardBox({ card }: { card: WorldviewCard }) {
  const theme = BUNDLE_THEME[card.bundle];
  const wrapperBase = `border-t-[2px] ${theme.accentBorder} bg-white dark:bg-slate-900 border-x border-b border-slate-200 dark:border-slate-800 p-5 flex flex-col`;

  const s = card.synthesis_fa;
  const beliefs = (s?.core_beliefs || []).slice(0, 3);
  const emphasized = (s?.emphasized || []).slice(0, 3);
  const absent = (s?.absent || []).slice(0, 2);
  const predictions = (s?.predictions_primed || []).slice(0, 2);
  const totalGrounded = beliefs.length + emphasized.length + predictions.length;

  return (
    <div className={wrapperBase}>
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2.5 h-2.5 ${theme.accentDot}`} aria-hidden="true" />
          <h3 className="text-[22px] font-bold text-slate-900 dark:text-slate-100">{theme.label}</h3>
        </div>
        <p className="text-[12px] tracking-wide text-slate-500 dark:text-slate-400 mt-1.5 ms-[18px]">
          {theme.side} · {toFaDigits(card.article_count)} مقاله از {toFaDigits(card.source_count)} منبع
        </p>
      </div>

      {s?.tone_profile?.description && (
        <p className="text-[13.5px] leading-7 text-slate-600 dark:text-slate-400 italic mb-1">
          {s.tone_profile.description}
        </p>
      )}

      {card.status === "ok" && totalGrounded === 0 && (
        <p className="mt-3 text-[13.5px] leading-7 text-slate-600 dark:text-slate-400">
          این هفته هیچ ادعایی به آستانهٔ شواهد لازم نرسید.
        </p>
      )}
      {card.status !== "ok" && (
        <p className="mt-3 text-[13.5px] leading-7 text-slate-600 dark:text-slate-400">
          این بازه با {toFaDigits(card.article_count)} مقاله از {toFaDigits(card.source_count)} منبع به آستانهٔ تولید چکیده نرسید.
        </p>
      )}

      {beliefs.length > 0 && <SectionLabel>چه گفتند</SectionLabel>}
      <div className="space-y-3">
        {beliefs.map((b, i) => <BeliefParagraph key={`b${i}`} item={b} />)}
      </div>

      {emphasized.length > 0 && <SectionLabel>چه برجسته کردند</SectionLabel>}
      <div className="space-y-3">
        {emphasized.map((b, i) => <BeliefParagraph key={`e${i}`} item={b} />)}
      </div>

      {predictions.length > 0 && <SectionLabel>چه انتظاری ساختند</SectionLabel>}
      <div className="space-y-3">
        {predictions.map((b, i) => <BeliefParagraph key={`p${i}`} item={b} />)}
      </div>

      {absent.length > 0 && <SectionLabel>و چه نگفتند</SectionLabel>}
      <div className="space-y-3">
        {absent.map((b, i) => <BeliefParagraph key={`a${i}`} item={b} />)}
      </div>

    </div>
  );
}

export default function WorldviewsClientFallback({
  locale,
  initialError,
}: {
  locale: string;
  initialError: string;
}) {
  const [state, setState] = useState<{ status: "loading" | "ok" | "error"; data?: CurrentResponse; error?: string }>({
    status: "loading",
  });

  useEffect(() => {
    let cancelled = false;
    clientFetch().then((r) => {
      if (cancelled) return;
      if (r.ok) setState({ status: "ok", data: r.data });
      else setState({ status: "error", error: r.error });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <>
        <p className="text-[12px] text-slate-500 dark:text-slate-500 mb-4">
          در حال دریافت داده از مرورگر شما (تلاش پشتیبان) …
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-slate-200 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
          {GRID_ORDER.map((b) => <CardSkeleton key={b} bundle={b} />)}
        </div>
      </>
    );
  }

  if (state.status === "error") {
    return (
      <div className="border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-6">
        <p className="text-[14px] font-semibold text-amber-900 dark:text-amber-200">
          دادهٔ این صفحه از سرور قابل دریافت نبود.
        </p>
        <p className="text-[12.5px] text-amber-800 dark:text-amber-300 mt-2 font-mono">
          SSR: {initialError}
        </p>
        <p className="text-[12.5px] text-amber-800 dark:text-amber-300 mt-1 font-mono">
          مرورگر: {state.error}
        </p>
        <p className="text-[12.5px] text-slate-600 dark:text-slate-400 mt-3">
          هم سرور و هم مرورگر شما نتوانستند داده را دریافت کنند. احتمالاً API در حال راه‌اندازی مجدد است؛ چند دقیقه دیگر دوباره تلاش کنید.
        </p>
      </div>
    );
  }

  const data = state.data!;
  const cards = data.cards || [];
  const byBundle = new Map<Bundle, WorldviewCard>(cards.map((c) => [c.bundle, c]));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-slate-200 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
      {GRID_ORDER.map((bundle) => {
        const card = byBundle.get(bundle);
        if (!card) return <CardSkeleton key={bundle} bundle={bundle} />;
        return <CardBox key={bundle} card={card} />;
      })}
    </div>
  );
}
