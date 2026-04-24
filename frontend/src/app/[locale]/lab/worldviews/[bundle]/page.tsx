import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Info, ArrowLeft } from "lucide-react";

export const revalidate = 300;

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Bundle = "principlist" | "reformist" | "moderate_diaspora" | "radical_diaspora";

const BUNDLES: Record<Bundle, { label: string; side: string; accent: string; borderTop: string }> = {
  principlist: {
    label: "اصول‌گرا",
    side: "درون مرز",
    accent: "text-[#1e3a5f] dark:text-[#93c5fd]",
    borderTop: "border-t-[3px] border-[#1e3a5f] dark:border-[#93c5fd]",
  },
  reformist: {
    label: "اصلاح‌طلب/مستقل",
    side: "درون مرز",
    accent: "text-[#4f7cac] dark:text-[#7ba3cf]",
    borderTop: "border-t-[3px] border-[#4f7cac] dark:border-[#7ba3cf]",
  },
  moderate_diaspora: {
    label: "میانه‌رو",
    side: "برون مرز",
    accent: "text-[#f97316] dark:text-[#fdba74]",
    borderTop: "border-t-[3px] border-[#f97316] dark:border-[#fdba74]",
  },
  radical_diaspora: {
    label: "مخالف رادیکال",
    side: "برون مرز",
    accent: "text-[#c2410c] dark:text-[#fb923c]",
    borderTop: "border-t-[3px] border-[#c2410c] dark:border-[#fb923c]",
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
  model_used: string | null;
  generated_at: string;
}

function toFa(n: number | string): string {
  const map = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  return String(n).replace(/[0-9]/g, (d) => map[Number(d)]);
}

function formatDateFa(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${toFa(y)}/${toFa(m)}/${toFa(d)}`;
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

function EvidenceList({ ids, locale }: { ids: string[]; locale: string }) {
  if (!ids || ids.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {ids.map((id) => (
        <Link
          key={id}
          href={`/${locale}/stories/${id}`}
          className="text-[11px] text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 border border-slate-200 dark:border-slate-700 px-2 py-0.5"
        >
          {id.slice(0, 8)}…
        </Link>
      ))}
    </div>
  );
}

function BeliefBlock({
  kind,
  idx,
  item,
  evidence,
  locale,
  accent,
}: {
  kind: "core_beliefs" | "emphasized" | "predictions_primed";
  idx: number;
  item: BeliefWithEvidence;
  evidence: Record<string, string[]> | null;
  locale: string;
  accent: string;
}) {
  const text = item.text || item.topic || "";
  if (!text) return null;
  const ids =
    evidence?.[`${kind}:${idx}`] ||
    item.example_article_ids ||
    [];
  return (
    <li className="border-b border-slate-100 dark:border-slate-800 py-3 last:border-0">
      <p className="text-[15px] leading-6 text-slate-800 dark:text-slate-200">{text}</p>
      <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
        {item.article_count ? `${toFa(item.article_count)} مقاله` : ""}
        {item.source_count ? ` · از ${toFa(item.source_count)} رسانه` : ""}
      </p>
      {item.note && (
        <p className="text-[12px] leading-5 text-slate-500 dark:text-slate-400 mt-1">{item.note}</p>
      )}
      <EvidenceList ids={ids} locale={locale} />
    </li>
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
          هنوز چکیده‌ای برای این گروه تولید نشده است.
        </p>
        <Link
          href={`/${locale}/lab/worldviews`}
          className="inline-flex items-center gap-1 text-[13px] text-blue-600 dark:text-blue-400 hover:underline mt-4"
        >
          <ArrowLeft className="w-4 h-4" />
          بازگشت
        </Link>
      </div>
    );
  }

  const theme = BUNDLES[bundle];
  const s = data.synthesis_fa;
  const evidence = data.evidence_fa;

  return (
    <div dir="rtl" className="mx-auto max-w-3xl px-4 py-8">
      <Link
        href={`/${locale}/lab/worldviews`}
        className="inline-flex items-center gap-1 text-[12px] text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 mb-6"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        همهٔ گروه‌ها
      </Link>

      {/* Unskippable caveat — at the top of the detail page */}
      <div className="flex items-start gap-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 mb-5 p-3 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
        <Info className="w-4 h-4 shrink-0 mt-0.5" />
        <span>
          این صفحه چکیدهٔ آنچه <strong>رسانه‌ها</strong>ی این گروه در هفتهٔ گذشته به خوانندگان خود گفتند را نشان می‌دهد، نه آنچه <strong>خوانندگان</strong> یا یک گروه اجتماعی باور دارند.
        </span>
      </div>

      {/* Header */}
      <div className={`${theme.borderTop} pt-4`}>
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div>
            <h1 className={`text-[24px] font-black ${theme.accent}`}>{theme.label}</h1>
            <p className="text-[12px] text-slate-400 dark:text-slate-500 mt-0.5">{theme.side}</p>
          </div>
          <span className="text-[12px] text-slate-400 dark:text-slate-500">
            {formatDateFa(data.window_start)} – {formatDateFa(data.window_end)}
          </span>
        </div>
        <p className="text-[12px] text-slate-400 dark:text-slate-500 mt-2">
          {toFa(data.article_count)} مقاله · {toFa(data.source_count)} رسانه ·
          پوشش تحلیل {toFa(Math.round(data.coverage_pct))}٪
          {data.model_used && ` · ${data.model_used}`}
        </p>
      </div>

      {data.status !== "ok" || !s ? (
        <div className="mt-6 p-5 border border-slate-200 dark:border-slate-700">
          <p className="text-[14px] text-slate-500 dark:text-slate-400">
            اطلاعات کافی برای این هفته وجود نداشت.
          </p>
          <p className="text-[12px] text-slate-400 dark:text-slate-500 mt-2">
            برای تولید یک جهان‌بینی حداقل ۲۰ مقاله از ۳ رسانه با پوشش تحلیل ۷۵٪ لازم است.
          </p>
        </div>
      ) : (
        <div className="mt-6 space-y-8">
          {s.core_beliefs && s.core_beliefs.length > 0 && (
            <section>
              <h2 className="text-[16px] font-black text-slate-900 dark:text-white mb-2">
                چه چیزی گفته شد
              </h2>
              <ul>
                {s.core_beliefs.map((item, i) => (
                  <BeliefBlock
                    key={`cb${i}`}
                    kind="core_beliefs"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    locale={locale}
                    accent={theme.accent}
                  />
                ))}
              </ul>
            </section>
          )}

          {s.emphasized && s.emphasized.length > 0 && (
            <section>
              <h2 className="text-[16px] font-black text-slate-900 dark:text-white mb-2">
                چه چیزی برجسته شد
              </h2>
              <ul>
                {s.emphasized.map((item, i) => (
                  <BeliefBlock
                    key={`em${i}`}
                    kind="emphasized"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    locale={locale}
                    accent={theme.accent}
                  />
                ))}
              </ul>
            </section>
          )}

          {s.absent && s.absent.length > 0 && (
            <section>
              <h2 className="text-[16px] font-black text-slate-900 dark:text-white mb-2">
                چه چیزی گفته نشد
              </h2>
              <ul>
                {s.absent.map((item, i) => (
                  <li
                    key={`ab${i}`}
                    className="border-b border-slate-100 dark:border-slate-800 py-3 last:border-0"
                  >
                    <p className="text-[15px] leading-6 text-slate-600 dark:text-slate-400">
                      {item.topic || item.text}
                    </p>
                    {item.note && (
                      <p className="text-[12px] leading-5 text-slate-500 dark:text-slate-500 mt-1">
                        {item.note}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {s.predictions_primed && s.predictions_primed.length > 0 && (
            <section>
              <h2 className="text-[16px] font-black text-slate-900 dark:text-white mb-2">
                چه انتظاری ساخته شد
              </h2>
              <ul>
                {s.predictions_primed.map((item, i) => (
                  <BeliefBlock
                    key={`pr${i}`}
                    kind="predictions_primed"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    locale={locale}
                    accent={theme.accent}
                  />
                ))}
              </ul>
            </section>
          )}

          {s.tone_profile?.description && (
            <section>
              <h2 className="text-[16px] font-black text-slate-900 dark:text-white mb-2">
                لحن مسلط
              </h2>
              <p className="text-[14px] leading-6 text-slate-600 dark:text-slate-400 italic">
                {s.tone_profile.description}
              </p>
              {(s.tone_profile.dominant || s.tone_profile.alt) && (
                <p className="text-[12px] text-slate-400 dark:text-slate-500 mt-1">
                  {s.tone_profile.dominant && <span>غالب: {s.tone_profile.dominant}</span>}
                  {s.tone_profile.alt && <span className="mx-3">ثانوی: {s.tone_profile.alt}</span>}
                </p>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
