import { setRequestLocale } from "next-intl/server";
import Link from "next/link";

export const revalidate = 300;

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────
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

// 4-subgroup palette — sitewide tokens; kept identical to NarrativeMap /
// WordsOfWeek / SourceComparison so the bundle identity is consistent.
// Per DESIGN.md, color is information: these are the bundle markers,
// reduced to a hairline so the page surface stays editorial.
const BUNDLE_THEME: Record<Bundle, {
  label: string;
  side: string;
  accentBorder: string;  // hairline at top
  accentDot: string;     // tiny dot beside label
}> = {
  principlist: {
    label: "اصول‌گرا",
    side: "درون مرز",
    accentBorder: "border-t-[#1e3a5f] dark:border-t-[#93c5fd]",
    accentDot: "bg-[#1e3a5f] dark:bg-[#93c5fd]",
  },
  reformist: {
    label: "اصلاح‌طلب/مستقل",
    side: "درون مرز",
    accentBorder: "border-t-[#4f7cac] dark:border-t-[#7ba3cf]",
    accentDot: "bg-[#4f7cac] dark:bg-[#7ba3cf]",
  },
  moderate_diaspora: {
    label: "میانه‌رو",
    side: "برون مرز",
    accentBorder: "border-t-[#f97316] dark:border-t-[#fdba74]",
    accentDot: "bg-[#f97316] dark:bg-[#fdba74]",
  },
  radical_diaspora: {
    label: "مخالف رادیکال",
    side: "برون مرز",
    accentBorder: "border-t-[#c2410c] dark:border-t-[#fb923c]",
    accentDot: "bg-[#c2410c] dark:bg-[#fb923c]",
  },
};

// In a 2-col RTL grid, col 1 sits on the right. Order: principlist (top-right),
// moderate (top-left), reformist (bottom-right), radical (bottom-left).
const GRID_ORDER: Bundle[] = [
  "principlist",
  "moderate_diaspora",
  "reformist",
  "radical_diaspora",
];

// ─── Helpers ─────────────────────────────────────────────────────
function toFaDigits(n: number | string): string {
  const map = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  return String(n).replace(/[0-9]/g, (d) => map[Number(d)]);
}

function formatDateRangeFa(start: string, end: string): string {
  const months = [
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
  ];
  const [, sm, sd] = start.split("-");
  const [ey, em, ed] = end.split("-");
  const sameMonth = sm === em;
  if (sameMonth) {
    return `${toFaDigits(parseInt(sd, 10))} تا ${toFaDigits(parseInt(ed, 10))} ${months[parseInt(em, 10) - 1]} ${toFaDigits(ey)}`;
  }
  return `${toFaDigits(parseInt(sd, 10))} ${months[parseInt(sm, 10) - 1]} تا ${toFaDigits(parseInt(ed, 10))} ${months[parseInt(em, 10) - 1]} ${toFaDigits(ey)}`;
}

async function fetchCurrent(): Promise<CurrentResponse | null> {
  try {
    const res = await fetch(`${API}/api/v1/worldviews/current`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ─── Card pieces ─────────────────────────────────────────────────

function CardHeader({ card }: { card: WorldviewCard }) {
  const theme = BUNDLE_THEME[card.bundle];
  return (
    <div className="mb-3">
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 ${theme.accentDot}`} aria-hidden="true" />
        <h3 className="text-[20px] font-bold text-slate-900 dark:text-slate-100" style={{ textWrap: "pretty" } as React.CSSProperties}>
          {theme.label}
        </h3>
      </div>
      <p className="text-[11px] tracking-wide text-slate-400 dark:text-slate-500 mt-1 ms-4">
        {theme.side} · {toFaDigits(card.article_count)} مقاله از {toFaDigits(card.source_count)} منبع
      </p>
    </div>
  );
}

function ToneSignature({ tone }: { tone: ToneProfile | undefined }) {
  if (!tone?.description && !tone?.dominant) return null;
  const text = tone.description || tone.dominant || "";
  return (
    <p className="text-[12.5px] leading-6 text-slate-500 dark:text-slate-400 italic mb-4">
      {text}
    </p>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] tracking-wide text-slate-400 dark:text-slate-500 mt-4 mb-2">
      {children}
    </p>
  );
}

function BeliefParagraph({ item }: { item: BeliefWithEvidence }) {
  const text = item.text || item.topic || "";
  if (!text) return null;
  return (
    <div>
      <p className="text-[14px] leading-7 text-slate-700 dark:text-slate-300">
        {text}
      </p>
      {item.note && (
        <p className="mt-1 text-[12.5px] leading-6 text-slate-500 dark:text-slate-500">
          {item.note}
        </p>
      )}
    </div>
  );
}

function GroundedOutCard({ card }: { card: WorldviewCard }) {
  // Status='ok' but every list got stripped by the grounding floor
  // (≥3 articles, ≥2 sources per belief). Common when a bundle has
  // ≤3 sources total — radical_diaspora's structural reality. Surface
  // it as fact, not failure.
  return (
    <div className="mt-3 text-[13.5px] leading-7 text-slate-600 dark:text-slate-400">
      <p>
        این هفته هیچ ادعایی به آستانهٔ شواهد لازم نرسید
        — هر گزاره باید دست‌کم ۳ مقاله از ۲ منبع متمایز پشتش باشد،
        و این گروه با {toFaDigits(card.source_count)} منبع تحت ردیابی
        به آن آستانه نمی‌رسد.
      </p>
    </div>
  );
}

function InsufficientCard({ card }: { card: WorldviewCard }) {
  return (
    <p className="mt-3 text-[13.5px] leading-7 text-slate-600 dark:text-slate-400">
      این بازه با {toFaDigits(card.article_count)} مقاله از {toFaDigits(card.source_count)} منبع
      به آستانهٔ تولید چکیده نرسید — حداقل ۲۰ مقاله از ۲ منبع لازم است.
    </p>
  );
}

function WorldviewCardBox({ card, locale }: { card: WorldviewCard; locale: string }) {
  const theme = BUNDLE_THEME[card.bundle];
  const wrapperBase = `border-t-[2px] ${theme.accentBorder} bg-white dark:bg-slate-900 border-x border-b border-slate-200 dark:border-slate-800 p-5 flex flex-col`;

  // Insufficient: precondition gate (too few articles/sources/coverage).
  if (card.status !== "ok") {
    return (
      <div className={wrapperBase}>
        <CardHeader card={card} />
        <InsufficientCard card={card} />
      </div>
    );
  }

  const s = card.synthesis_fa;
  const beliefs = (s?.core_beliefs || []).slice(0, 3);
  const emphasized = (s?.emphasized || []).slice(0, 3);
  const absent = (s?.absent || []).slice(0, 2);
  const predictions = (s?.predictions_primed || []).slice(0, 2);
  const totalGrounded = beliefs.length + emphasized.length + predictions.length;

  // status='ok' but everything got stripped post-LLM by the grounding
  // floor. Show the structural reason, then fall back to whatever
  // survived (absent + tone) without pretending it's a full card.
  const groundedOut = totalGrounded === 0;

  return (
    <div className={wrapperBase}>
      <CardHeader card={card} />
      <ToneSignature tone={s?.tone_profile} />

      {groundedOut && <GroundedOutCard card={card} />}

      {beliefs.length > 0 && (
        <>
          <SectionLabel>چه گفتند</SectionLabel>
          <div className="space-y-3">
            {beliefs.map((b, i) => (
              <BeliefParagraph key={`b${i}`} item={b} />
            ))}
          </div>
        </>
      )}

      {emphasized.length > 0 && (
        <>
          <SectionLabel>چه برجسته کردند</SectionLabel>
          <div className="space-y-3">
            {emphasized.map((b, i) => (
              <BeliefParagraph key={`e${i}`} item={b} />
            ))}
          </div>
        </>
      )}

      {predictions.length > 0 && (
        <>
          <SectionLabel>چه انتظاری ساختند</SectionLabel>
          <div className="space-y-3">
            {predictions.map((b, i) => (
              <BeliefParagraph key={`p${i}`} item={b} />
            ))}
          </div>
        </>
      )}

      {absent.length > 0 && (
        <>
          <SectionLabel>و چه نگفتند</SectionLabel>
          <div className="space-y-3">
            {absent.map((b, i) => (
              <BeliefParagraph key={`a${i}`} item={b} />
            ))}
          </div>
        </>
      )}

      {/* Footer: detail link */}
      <div className="mt-auto pt-4">
        <Link
          href={`/${locale}/lab/worldviews/${card.bundle}`}
          className="text-[12.5px] font-semibold text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 underline underline-offset-4 decoration-slate-300 dark:decoration-slate-600 decoration-[1px]"
        >
          شواهد و مقالات
        </Link>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────
export default async function WorldviewsLabPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const data = await fetchCurrent();
  const cards = data?.cards || [];
  const byBundle = new Map<Bundle, WorldviewCard>(
    cards.map((c) => [c.bundle, c])
  );
  const windowLine = data?.window_start && data?.window_end
    ? formatDateRangeFa(data.window_start, data.window_end)
    : null;

  return (
    <div dir="rtl" className="mx-auto max-w-6xl px-4 py-10">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-[28px] font-bold text-slate-900 dark:text-slate-100" style={{ textWrap: "pretty" } as React.CSSProperties}>
            اگر فقط از این گروه می‌خواندید
          </h1>
          <span className="px-2 py-0.5 text-[10px] font-semibold border border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400">
            آزمایشی
          </span>
        </div>
        {windowLine && (
          <p className="text-[12.5px] text-slate-500 dark:text-slate-500">
            بازهٔ {windowLine}
          </p>
        )}
        <p className="mt-4 text-[14px] leading-7 text-slate-600 dark:text-slate-400 max-w-3xl">
          چهار چکیده از آنچه رسانه‌های هر گروه در هفتهٔ گذشته به خوانندگان خود گفتند.
          هر گزاره دست‌کم به ۳ مقاله از ۲ منبع متمایز متکی است؛ کلیک روی «شواهد و مقالات»
          زنجیرهٔ منابع را باز می‌کند.
        </p>
        <p className="mt-2 text-[12.5px] leading-6 text-slate-500 dark:text-slate-500 max-w-3xl">
          این تصویری است از <em>محیط اطلاعاتی</em> این رسانه‌ها — نه باور خوانندگان آن‌ها
          و نه برداشت یک گروه اجتماعی.
        </p>
      </header>

      {cards.length === 0 ? (
        <div className="border border-slate-200 dark:border-slate-800 p-8">
          <p className="text-[14px] text-slate-600 dark:text-slate-400">
            هنوز چکیده‌ای تولید نشده است.
          </p>
          <p className="text-[12.5px] text-slate-500 dark:text-slate-500 mt-2">
            این فرایند هر دوشنبه اجرا می‌شود.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-slate-200 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
          {GRID_ORDER.map((bundle) => {
            const card = byBundle.get(bundle);
            if (!card) {
              const theme = BUNDLE_THEME[bundle];
              return (
                <div
                  key={bundle}
                  className={`border-t-[2px] ${theme.accentBorder} bg-white dark:bg-slate-900 p-5`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 ${theme.accentDot}`} />
                    <h3 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">
                      {theme.label}
                    </h3>
                  </div>
                  <p className="text-[11px] tracking-wide text-slate-400 dark:text-slate-500 mt-1 ms-4">
                    {theme.side}
                  </p>
                  <p className="mt-3 text-[13.5px] leading-7 text-slate-500 dark:text-slate-500">
                    این هفته چکیده‌ای برای این گروه تولید نشد.
                  </p>
                </div>
              );
            }
            return <WorldviewCardBox key={bundle} card={card} locale={locale} />;
          })}
        </div>
      )}
    </div>
  );
}
