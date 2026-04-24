import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { Info } from "lucide-react";

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

// ─── Visual tokens (match the 4-subgroup palette used site-wide) ──
const BUNDLE_THEME: Record<Bundle, { borderTop: string; label: string; side: string; accent: string }> = {
  principlist: {
    borderTop: "border-t-[3px] border-[#1e3a5f] dark:border-[#93c5fd]",
    label: "اصول‌گرا",
    side: "درون مرز",
    accent: "text-[#1e3a5f] dark:text-[#93c5fd]",
  },
  reformist: {
    borderTop: "border-t-[3px] border-[#4f7cac] dark:border-[#7ba3cf]",
    label: "اصلاح‌طلب/مستقل",
    side: "درون مرز",
    accent: "text-[#4f7cac] dark:text-[#7ba3cf]",
  },
  moderate_diaspora: {
    borderTop: "border-t-[3px] border-[#f97316] dark:border-[#fdba74]",
    label: "میانه‌رو",
    side: "برون مرز",
    accent: "text-[#f97316] dark:text-[#fdba74]",
  },
  radical_diaspora: {
    borderTop: "border-t-[3px] border-[#c2410c] dark:border-[#fb923c]",
    label: "مخالف رادیکال",
    side: "برون مرز",
    accent: "text-[#c2410c] dark:text-[#fb923c]",
  },
};

// DOM order for a 2-column RTL grid so that principlist + reformist
// land on the RIGHT column (top, bottom) and moderate + radical land
// on the LEFT column (top, bottom). Parham's spec.
const GRID_ORDER: Bundle[] = [
  "principlist",        // row 1, right
  "moderate_diaspora",  // row 1, left
  "reformist",          // row 2, right
  "radical_diaspora",   // row 2, left
];

// ─── Helpers ─────────────────────────────────────────────────────
function toFaDigits(n: number | string): string {
  const map = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  return String(n).replace(/[0-9]/g, (d) => map[Number(d)]);
}

function formatDateFa(iso: string): string {
  // Display as YYYY/MM/DD with Farsi digits. Jalali rendering intentionally
  // deferred — the window anchors are UTC dates we also write back to the
  // DB, so showing Gregorian is less ambiguous than a noisy conversion.
  const [y, m, d] = iso.split("-");
  return `${toFaDigits(y)}/${toFaDigits(m)}/${toFaDigits(d)}`;
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

// ─── Card components ─────────────────────────────────────────────
function CaveatChip() {
  return (
    <div className="flex items-start gap-1.5 text-[11px] leading-5 text-slate-400 dark:text-slate-500 mt-3 pt-2 border-t border-slate-100 dark:border-slate-800">
      <Info className="w-3 h-3 shrink-0 mt-0.5" />
      <span>
        چکیده‌ای از آنچه این رسانه‌ها گفتند، نه آنچه خوانندگان‌شان باور دارند.
      </span>
    </div>
  );
}

function InsufficientCard({ card, locale }: { card: WorldviewCard; locale: string }) {
  const theme = BUNDLE_THEME[card.bundle];
  return (
    <div className={`${theme.borderTop} bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5`}>
      <div className="flex items-baseline justify-between">
        <div>
          <h3 className={`text-[18px] font-black ${theme.accent}`}>{theme.label}</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">{theme.side}</p>
        </div>
        <span className="text-[11px] text-slate-400">
          {formatDateFa(card.window_start)} – {formatDateFa(card.window_end)}
        </span>
      </div>
      <p className="text-[14px] leading-6 text-slate-500 dark:text-slate-400 mt-4">
        اطلاعات کافی این هفته در دسترس نیست.
      </p>
      <p className="text-[12px] leading-5 text-slate-400 dark:text-slate-500 mt-2">
        {toFaDigits(card.article_count)} مقاله از {toFaDigits(card.source_count)} رسانه در این بازه
        — برای تولید یک جهان‌بینی معتبر کافی نبود.
      </p>
      <CaveatChip />
    </div>
  );
}

function BeliefBullet({ item, accent }: { item: BeliefWithEvidence; accent: string }) {
  const text = item.text || item.topic || "";
  const count = item.article_count ?? 0;
  if (!text) return null;
  return (
    <li className="flex items-start gap-2">
      <span className={`mt-1.5 w-1 h-1 rounded-full shrink-0 ${accent.replace("text-", "bg-")}`} />
      <span className="flex-1">
        <span className="text-[14px] leading-6 text-slate-700 dark:text-slate-300">{text}</span>
        {count > 0 && (
          <span className="inline-block mx-2 text-[11px] text-slate-400 align-middle">
            · {toFaDigits(count)} مقاله
          </span>
        )}
        {item.note && (
          <span className="block text-[12px] leading-5 text-slate-400 dark:text-slate-500 mt-0.5">
            {item.note}
          </span>
        )}
      </span>
    </li>
  );
}

function WorldviewCardBox({ card, locale }: { card: WorldviewCard; locale: string }) {
  if (card.status !== "ok" || !card.synthesis_fa) {
    return <InsufficientCard card={card} locale={locale} />;
  }
  const theme = BUNDLE_THEME[card.bundle];
  const s = card.synthesis_fa;
  const beliefs = (s.core_beliefs || []).slice(0, 3);
  const emphasized = (s.emphasized || []).slice(0, 3);
  const absent = (s.absent || []).slice(0, 2);
  const predictions = (s.predictions_primed || []).slice(0, 2);

  return (
    <div className={`${theme.borderTop} bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 flex flex-col`}>
      {/* Header: bundle name + window */}
      <div className="flex items-baseline justify-between">
        <div>
          <h3 className={`text-[18px] font-black ${theme.accent}`}>{theme.label}</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">{theme.side}</p>
        </div>
        <span className="text-[11px] text-slate-400">
          {formatDateFa(card.window_start)} – {formatDateFa(card.window_end)}
        </span>
      </div>

      {/* Measurement strip — signal strength behind the synthesis */}
      <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-2">
        {toFaDigits(card.article_count)} مقاله · {toFaDigits(card.source_count)} رسانه ·
        پوشش تحلیل {toFaDigits(Math.round(card.coverage_pct))}٪
      </p>

      {/* Core beliefs */}
      {beliefs.length > 0 && (
        <div className="mt-4">
          <p className="text-[12px] font-bold text-slate-500 dark:text-slate-400 mb-1.5">
            چه چیزی گفته شد
          </p>
          <ul className="space-y-1.5">
            {beliefs.map((b, i) => (
              <BeliefBullet key={`b${i}`} item={b} accent={theme.accent} />
            ))}
          </ul>
        </div>
      )}

      {/* Emphasized */}
      {emphasized.length > 0 && (
        <div className="mt-3">
          <p className="text-[12px] font-bold text-slate-500 dark:text-slate-400 mb-1.5">
            چه چیزی برجسته شد
          </p>
          <ul className="space-y-1.5">
            {emphasized.map((b, i) => (
              <BeliefBullet key={`e${i}`} item={b} accent={theme.accent} />
            ))}
          </ul>
        </div>
      )}

      {/* Absences */}
      {absent.length > 0 && (
        <div className="mt-3">
          <p className="text-[12px] font-bold text-slate-500 dark:text-slate-400 mb-1.5">
            چه چیزی گفته نشد
          </p>
          <ul className="space-y-1.5">
            {absent.map((b, i) => (
              <BeliefBullet key={`a${i}`} item={b} accent="text-slate-400" />
            ))}
          </ul>
        </div>
      )}

      {/* Predictions */}
      {predictions.length > 0 && (
        <div className="mt-3">
          <p className="text-[12px] font-bold text-slate-500 dark:text-slate-400 mb-1.5">
            چه انتظاری ساخته شد
          </p>
          <ul className="space-y-1.5">
            {predictions.map((b, i) => (
              <BeliefBullet key={`p${i}`} item={b} accent={theme.accent} />
            ))}
          </ul>
        </div>
      )}

      {/* Tone */}
      {s.tone_profile?.description && (
        <p className="text-[12px] leading-5 text-slate-500 dark:text-slate-400 mt-3 italic">
          {s.tone_profile.description}
        </p>
      )}

      {/* Footer: detail link + unskippable caveat */}
      <div className="mt-auto pt-3">
        <Link
          href={`/${locale}/lab/worldviews/${card.bundle}`}
          className={`inline-flex items-center gap-1 text-[12px] font-bold ${theme.accent} hover:underline`}
        >
          ببین چرا ←
        </Link>
      </div>
      <CaveatChip />
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

  return (
    <div dir="rtl" className="mx-auto max-w-6xl px-4 py-8">
      {/* Lab badge */}
      <div className="flex items-center gap-2 mb-4">
        <span className="px-2 py-0.5 text-[10px] font-bold border border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400">
          آزمایشی
        </span>
        <span className="text-[11px] text-slate-400">
          — این ابزار در حال آزمایش است و هنوز در صفحه اصلی نمایش داده نمی‌شود.
        </span>
      </div>

      {/* Header with line-title-line divider, same as other sections */}
      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
        <h1 className="text-[15px] font-black text-slate-900 dark:text-white shrink-0">
          اگر فقط از این گروه می‌خواندید
        </h1>
        <div className="flex-1 h-[2px] bg-slate-300 dark:bg-slate-600" />
      </div>

      {/* Window + context paragraph */}
      <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 mb-6 max-w-3xl">
        چهار چکیده از آنچه رسانه‌های هر گروه در هفتهٔ گذشته به خوانندگان خود گفتند.
        این‌ها تصویری از محیط اطلاعاتی این رسانه‌هاست، نه باورهای افراد یا گروه‌های اجتماعی.
        هر ادعا به چند مقالهٔ منبع متکی است که با کلیک روی کارت قابل مشاهده‌اند.
      </p>

      {cards.length === 0 ? (
        <div className="border border-slate-200 dark:border-slate-800 p-8 text-center">
          <p className="text-[14px] text-slate-500 dark:text-slate-400">
            هنوز چکیده‌ای تولید نشده است.
          </p>
          <p className="text-[12px] text-slate-400 dark:text-slate-500 mt-2">
            این فرایند هر دوشنبه اجرا می‌شود.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {GRID_ORDER.map((bundle) => {
            const card = byBundle.get(bundle);
            if (!card) {
              // Rare: bundle never ran. Still show a labeled placeholder so
              // the 2×2 grid stays symmetric.
              return (
                <div
                  key={bundle}
                  className={`${BUNDLE_THEME[bundle].borderTop} bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5`}
                >
                  <h3 className={`text-[18px] font-black ${BUNDLE_THEME[bundle].accent}`}>
                    {BUNDLE_THEME[bundle].label}
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">{BUNDLE_THEME[bundle].side}</p>
                  <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 mt-4">
                    هنوز چکیده‌ای برای این گروه موجود نیست.
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
