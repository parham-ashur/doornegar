import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

export const revalidate = 300;

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Bundle = "principlist" | "reformist" | "moderate_diaspora" | "radical_diaspora";

const BUNDLES: Record<Bundle, { label: string; side: string; accentBorder: string; accentDot: string }> = {
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

interface BeliefWithEvidence {
  text?: string;
  topic?: string;
  note?: string;
  article_count?: number;
  source_count?: number;
  example_article_ids?: string[];
}

interface Synthesis {
  core_beliefs?: BeliefWithEvidence[];
  emphasized?: BeliefWithEvidence[];
  absent?: BeliefWithEvidence[];
  tone_profile?: { dominant?: string; alt?: string; description?: string };
  predictions_primed?: BeliefWithEvidence[];
}

interface EvidenceArticle {
  id: string;
  title_fa: string | null;
  source_slug: string | null;
  source_name_fa: string | null;
  story_id: string | null;
  url: string | null;
  published_at: string | null;
}

interface WorldviewDetail {
  bundle: Bundle;
  bundle_label_fa: string;
  window_start: string;
  window_end: string;
  status: "ok" | "insufficient";
  article_count: number;
  source_count: number;
  coverage_pct: number;
  synthesis_fa: Synthesis | null;
  evidence_fa: Record<string, string[]> | null;
  evidence_articles: Record<string, EvidenceArticle> | null;
  model_used: string | null;
  generated_at: string;
}

function toFa(n: number | string): string {
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
    return `${toFa(parseInt(sd, 10))} تا ${toFa(parseInt(ed, 10))} ${months[parseInt(em, 10) - 1]} ${toFa(ey)}`;
  }
  return `${toFa(parseInt(sd, 10))} ${months[parseInt(sm, 10) - 1]} تا ${toFa(parseInt(ed, 10))} ${months[parseInt(em, 10) - 1]} ${toFa(ey)}`;
}

async function fetchDetail(bundle: string): Promise<WorldviewDetail | null> {
  try {
    const res = await fetch(`${API}/api/v1/worldviews/${bundle}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function EvidenceList({
  ids,
  articles,
  locale,
}: {
  ids: string[];
  articles: Record<string, EvidenceArticle> | null;
  locale: string;
}) {
  if (!ids || ids.length === 0) return null;
  return (
    <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-px bg-slate-200 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
      {ids.map((id) => {
        const meta = articles?.[id];
        const storyHref = meta?.story_id ? `/${locale}/stories/${meta.story_id}` : null;
        const outletUrl = meta?.url || null;
        const title = meta?.title_fa?.trim() || id.slice(0, 8) + "…";
        const source = meta?.source_name_fa || meta?.source_slug;
        const inner = (
          <>
            <span className="text-[13px] leading-6 text-slate-700 dark:text-slate-300 line-clamp-2">
              {title}
            </span>
            {source && (
              <span className="text-[11px] tracking-wide text-slate-400 dark:text-slate-500 mt-1 block">
                {source}
              </span>
            )}
          </>
        );
        const className = "block bg-white dark:bg-slate-900 px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors";
        if (storyHref) {
          return (
            <li key={id}>
              <Link href={storyHref} className={className}>
                {inner}
              </Link>
            </li>
          );
        }
        if (outletUrl) {
          return (
            <li key={id}>
              <a
                href={outletUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={className}
              >
                {inner}
              </a>
            </li>
          );
        }
        return (
          <li key={id} className={className + " cursor-default"}>
            {inner}
          </li>
        );
      })}
    </ul>
  );
}

function BeliefBlock({
  kind,
  idx,
  item,
  evidence,
  articles,
  locale,
}: {
  kind: "core_beliefs" | "emphasized" | "predictions_primed";
  idx: number;
  item: BeliefWithEvidence;
  evidence: Record<string, string[]> | null;
  articles: Record<string, EvidenceArticle> | null;
  locale: string;
}) {
  const text = item.text || item.topic || "";
  if (!text) return null;
  const ids = evidence?.[`${kind}:${idx}`] || item.example_article_ids || [];
  return (
    <li className="border-b border-slate-200 dark:border-slate-800 py-6 last:border-0">
      <p className="text-[16px] leading-[1.85] text-slate-800 dark:text-slate-200">{text}</p>
      {item.note && (
        <p className="text-[13px] leading-7 text-slate-500 dark:text-slate-400 mt-2">{item.note}</p>
      )}
      <EvidenceList ids={ids} articles={articles} locale={locale} />
    </li>
  );
}

// Detail-page section heading. Turning-points between
// «چه گفتند» / «چه برجسته کردند» / «چه انتظاری ساختند» / «و چه نگفتند».
// On the detail page the surrounding rhythm is generous (each section
// has space-y-10 wrapper), so the heading itself just needs to feel
// like a chapter break. DESIGN.md §3 «running head» applied at title
// scale (1.125rem ≈ 18px) since this is a longer-form page than the
// 4-card overview.
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="text-[18px] font-bold text-slate-900 dark:text-slate-100 tracking-wide mb-4 pb-2 border-b border-slate-200 dark:border-slate-800"
      style={{ textWrap: "pretty" } as React.CSSProperties}
    >
      {children}
    </h2>
  );
}

export default async function WorldviewBundlePage({
  params,
}: {
  params: Promise<{ locale: string; bundle: string }>;
}) {
  const { locale, bundle: bundleParam } = await params;
  setRequestLocale(locale);
  if (!(bundleParam in BUNDLES)) {
    notFound();
  }
  const bundle = bundleParam as Bundle;
  const data = await fetchDetail(bundle);
  if (!data) {
    return (
      <div dir="rtl" className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-[14px] text-slate-500 dark:text-slate-400">
          چکیده‌ای برای این گروه موجود نیست.
        </p>
        <Link
          href={`/${locale}/lab/worldviews`}
          className="inline-flex items-center gap-1 text-[13px] text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 mt-4 underline underline-offset-4 decoration-slate-300"
        >
          <ArrowLeft className="w-4 h-4" />
          بازگشت به همهٔ گروه‌ها
        </Link>
      </div>
    );
  }

  const theme = BUNDLES[bundle];
  const s = data.synthesis_fa;
  const evidence = data.evidence_fa;
  const articles = data.evidence_articles;
  const beliefs = s?.core_beliefs || [];
  const emphasized = s?.emphasized || [];
  const predictions = s?.predictions_primed || [];
  const absent = s?.absent || [];
  const totalGrounded = beliefs.length + emphasized.length + predictions.length;
  const groundedOut = data.status === "ok" && totalGrounded === 0;

  return (
    <div dir="rtl" className="mx-auto max-w-3xl px-4 py-8">
      <Link
        href={`/${locale}/lab/worldviews`}
        className="inline-flex items-center gap-1 text-[12px] text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 mb-8"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        همهٔ گروه‌ها
      </Link>

      {/* Header */}
      <header className={`border-t-[2px] ${theme.accentBorder} pt-5 mb-2`}>
        <div className="flex items-center gap-2.5">
          <span className={`inline-block w-3 h-3 ${theme.accentDot}`} aria-hidden="true" />
          <h1 className="text-[30px] font-bold text-slate-900 dark:text-slate-100" style={{ textWrap: "pretty" } as React.CSSProperties}>
            {theme.label}
          </h1>
        </div>
        <p className="text-[12.5px] tracking-wide text-slate-500 dark:text-slate-400 mt-2 ms-[22px]">
          {theme.side} · بازهٔ {formatDateRangeFa(data.window_start, data.window_end)}
        </p>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mt-2 ms-[22px]">
          {toFa(data.article_count)} مقاله · {toFa(data.source_count)} منبع
          · پوشش تحلیل {toFa(Math.round(data.coverage_pct))}٪
        </p>
      </header>

      {/* Editorial caveat — single line, italicized, no box */}
      <p className="text-[13px] leading-7 text-slate-500 dark:text-slate-400 mt-5 mb-10 italic">
        تصویری از <strong className="font-semibold not-italic">محیط اطلاعاتی</strong> این رسانه‌ها در هفتهٔ گذشته،
        نه باور خوانندگان یا یک گروه اجتماعی.
      </p>

      {data.status !== "ok" || !s ? (
        <div className="text-[14.5px] leading-8 text-slate-600 dark:text-slate-400">
          <p>
            این بازه با {toFa(data.article_count)} مقاله از {toFa(data.source_count)} منبع
            به آستانهٔ تولید چکیده نرسید — حداقل ۲۰ مقاله از ۲ منبع لازم است.
          </p>
        </div>
      ) : groundedOut ? (
        <>
          <p className="text-[14.5px] leading-8 text-slate-600 dark:text-slate-400">
            این هفته هیچ ادعایی به آستانهٔ شواهد لازم نرسید
            — هر گزاره باید دست‌کم ۳ مقاله از ۲ منبع متمایز پشتش باشد،
            و این گروه با {toFa(data.source_count)} منبع تحت ردیابی به آن آستانه نمی‌رسد.
            باقی این هفته به‌صورت خالی سپری شد.
          </p>
          {s?.tone_profile?.description && (
            <div className="mt-8">
              <SectionLabel>لحن مسلط</SectionLabel>
              <p className="text-[14px] leading-7 text-slate-600 dark:text-slate-400 italic">
                {s.tone_profile.description}
              </p>
            </div>
          )}
          {absent.length > 0 && (
            <div className="mt-8">
              <SectionLabel>چه نگفتند</SectionLabel>
              <ul>
                {absent.map((item, i) => (
                  <li
                    key={`ab${i}`}
                    className="border-b border-slate-200 dark:border-slate-800 py-4 last:border-0"
                  >
                    <p className="text-[15px] leading-7 text-slate-700 dark:text-slate-300">
                      {item.topic || item.text}
                    </p>
                    {item.note && (
                      <p className="text-[12.5px] leading-6 text-slate-500 dark:text-slate-500 mt-1">
                        {item.note}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <div className="space-y-10">
          {/* Tone signature elevated near the top */}
          {s.tone_profile?.description && (
            <p className="text-[14px] leading-8 text-slate-600 dark:text-slate-400 italic border-r-2 border-slate-200 dark:border-slate-700 pr-4">
              {s.tone_profile.description}
            </p>
          )}

          {beliefs.length > 0 && (
            <section>
              <SectionLabel>چه گفتند</SectionLabel>
              <ul>
                {beliefs.map((item, i) => (
                  <BeliefBlock
                    key={`cb${i}`}
                    kind="core_beliefs"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    articles={articles}
                    locale={locale}
                  />
                ))}
              </ul>
            </section>
          )}

          {emphasized.length > 0 && (
            <section>
              <SectionLabel>چه برجسته کردند</SectionLabel>
              <ul>
                {emphasized.map((item, i) => (
                  <BeliefBlock
                    key={`em${i}`}
                    kind="emphasized"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    articles={articles}
                    locale={locale}
                  />
                ))}
              </ul>
            </section>
          )}

          {predictions.length > 0 && (
            <section>
              <SectionLabel>چه انتظاری ساختند</SectionLabel>
              <ul>
                {predictions.map((item, i) => (
                  <BeliefBlock
                    key={`pr${i}`}
                    kind="predictions_primed"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    articles={articles}
                    locale={locale}
                  />
                ))}
              </ul>
            </section>
          )}

          {absent.length > 0 && (
            <section>
              <SectionLabel>و چه نگفتند</SectionLabel>
              <ul>
                {absent.map((item, i) => (
                  <li
                    key={`ab${i}`}
                    className="border-b border-slate-200 dark:border-slate-800 py-4 last:border-0"
                  >
                    <p className="text-[15px] leading-7 text-slate-700 dark:text-slate-300">
                      {item.topic || item.text}
                    </p>
                    {item.note && (
                      <p className="text-[12.5px] leading-6 text-slate-500 dark:text-slate-500 mt-1">
                        {item.note}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
