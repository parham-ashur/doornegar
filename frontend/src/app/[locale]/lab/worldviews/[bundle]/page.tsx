import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";

// Same data lifecycle as the overview — weekly refresh. 30 min ISR.
export const revalidate = 1800;

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

const TEHRAN_DATE_FMT = new Intl.DateTimeFormat("fa-IR-u-nu-arabext", {
  timeZone: "Asia/Tehran",
  month: "short",
  day: "numeric",
});

function formatPublishedFa(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return TEHRAN_DATE_FMT.format(new Date(iso));
  } catch {
    return null;
  }
}

type FetchResult =
  | { ok: true; data: WorldviewDetail }
  | { ok: false; error: string };

// Same retry-on-5xx pattern as the overview page (worldviews/page.tsx).
// First attempt right after a Vercel deploy can see a brief 5xx if
// Railway is still cycling; one retry with backoff catches most
// transients before ISR caches the error for 30 min.
async function fetchDetail(bundle: string): Promise<FetchResult> {
  let lastError = "fetch failed: unknown";
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${API}/api/v1/worldviews/${bundle}`, {
        next: { revalidate: 300 },
      });
      if (res.ok) {
        const data = (await res.json()) as WorldviewDetail;
        return { ok: true, data };
      }
      lastError = `HTTP ${res.status} from API`;
      if (res.status < 500 || attempt > 0) break;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      lastError = `fetch failed: ${msg}`;
      if (attempt > 0) break;
    }
    await new Promise((r) => setTimeout(r, 750));
  }
  return { ok: false, error: lastError };
}

// ─── Citation list (the «شواهد و مقالات» beneath each belief) ──────
//
// Editorial citation pattern (matches story-page ArticleFilterList):
//   - Source name as eyebrow text — small, slate-500, bold
//   - Date as a quiet right-aligned tag
//   - Article title as the dominant element — 14.5px body bold,
//     hover-underline, line-clamp-2
//   - Item separated by a hairline rule, no card-grid background
//   - Numbered marker so the citation reads as a reference, not a chip
//
// Click target priority:
//   1. Story page (the cluster the article belongs to) — preferred
//   2. Outlet URL (external link, opens in new tab)
//   3. No link — render as plain reference
function CitationItem({
  article,
  index,
  locale,
}: {
  article: EvidenceArticle | undefined;
  index: number;
  locale: string;
}) {
  const meta = article;
  const title = meta?.title_fa?.trim() || "—";
  const source = meta?.source_name_fa || meta?.source_slug || "";
  const dateLabel = formatPublishedFa(meta?.published_at || null);
  const storyHref = meta?.story_id ? `/${locale}/stories/${meta.story_id}` : null;
  const outletUrl = meta?.url || null;
  const isExternal = !storyHref && !!outletUrl;
  const href = storyHref || outletUrl || null;

  const body = (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 py-4">
      <span className="text-[13px] tabular-nums text-slate-400 dark:text-slate-500 select-none pt-0.5">
        {toFa(index + 1)}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 mb-1.5">
          {source && (
            <span className="text-[12px] font-bold tracking-wide text-slate-600 dark:text-slate-400">
              {source}
            </span>
          )}
          {dateLabel && (
            <span className="text-[11.5px] text-slate-400 dark:text-slate-500 tabular-nums">
              {dateLabel}
            </span>
          )}
          {isExternal && (
            <ExternalLink className="w-3 h-3 text-slate-400 dark:text-slate-500" aria-hidden="true" />
          )}
        </div>
        <p className="text-[14.5px] leading-7 font-semibold text-slate-800 dark:text-slate-200 line-clamp-2">
          {title}
        </p>
      </div>
    </div>
  );

  if (href) {
    const className = "block border-b border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors group";
    if (storyHref) {
      return (
        <Link href={storyHref} className={className}>
          {body}
        </Link>
      );
    }
    return (
      <a href={outletUrl!} target="_blank" rel="noopener noreferrer" className={className}>
        {body}
      </a>
    );
  }
  return <div className="border-b border-slate-200 dark:border-slate-800">{body}</div>;
}

function CitationList({
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
    <div className="mt-5">
      <p className="text-[11.5px] tracking-wide font-bold text-slate-500 dark:text-slate-400 mb-1 uppercase">
        شواهد · {toFa(ids.length)} مقاله
      </p>
      <div className="border-t border-slate-200 dark:border-slate-800">
        {ids.map((id, i) => (
          <CitationItem key={id} article={articles?.[id]} index={i} locale={locale} />
        ))}
      </div>
    </div>
  );
}

// ─── Belief blocks ──────────────────────────────────────────────────
//
// Each belief is rendered as a numbered editorial paragraph with a
// quiet «N مقاله» evidence-weight badge inline. The text uses 16px /
// 1.85 Persian-equal-craft body (DESIGN.md §3). Note text drops to
// 13px to differentiate from the main claim.

function BeliefBlock({
  kind,
  idx,
  item,
  evidence,
  articles,
  locale,
  ordinal,
}: {
  kind: "core_beliefs" | "emphasized" | "predictions_primed";
  idx: number;
  item: BeliefWithEvidence;
  evidence: Record<string, string[]> | null;
  articles: Record<string, EvidenceArticle> | null;
  locale: string;
  ordinal: number;
}) {
  const text = item.text || item.topic || "";
  if (!text) return null;
  const ids = evidence?.[`${kind}:${idx}`] || item.example_article_ids || [];
  const articleCount = item.article_count;

  return (
    <article className="border-b border-slate-200 dark:border-slate-800 py-8 last:border-0">
      <div className="grid grid-cols-[auto_1fr] gap-x-4">
        <span className="text-[15px] font-bold tabular-nums text-slate-300 dark:text-slate-600 select-none pt-1">
          {toFa(ordinal)}
        </span>
        <div className="min-w-0">
          <p className="text-[16px] leading-[1.95] text-slate-800 dark:text-slate-200">{text}</p>
          {item.note && (
            <p className="text-[13.5px] leading-7 text-slate-500 dark:text-slate-400 mt-3">{item.note}</p>
          )}
          {articleCount !== undefined && articleCount !== null && (
            <p className="text-[11.5px] tracking-wide text-slate-400 dark:text-slate-500 mt-3">
              {toFa(articleCount)} مقاله پشتیبان
            </p>
          )}
          <CitationList ids={ids} articles={articles} locale={locale} />
        </div>
      </div>
    </article>
  );
}

function AbsenceBlock({ item, ordinal }: { item: BeliefWithEvidence; ordinal: number }) {
  const text = item.topic || item.text || "";
  if (!text) return null;
  return (
    <article className="border-b border-slate-200 dark:border-slate-800 py-8 last:border-0">
      <div className="grid grid-cols-[auto_1fr] gap-x-4">
        <span className="text-[15px] font-bold tabular-nums text-slate-300 dark:text-slate-600 select-none pt-1">
          {toFa(ordinal)}
        </span>
        <div className="min-w-0">
          <p className="text-[16px] leading-[1.95] text-slate-800 dark:text-slate-200">{text}</p>
          {item.note && (
            <p className="text-[13.5px] leading-7 text-slate-500 dark:text-slate-400 mt-3">{item.note}</p>
          )}
        </div>
      </div>
    </article>
  );
}

// ─── Section heading ────────────────────────────────────────────────
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="text-[18px] font-bold text-slate-900 dark:text-slate-100 tracking-wide mb-2 pb-3 border-b-2 border-slate-300 dark:border-slate-700"
      style={{ textWrap: "pretty" } as React.CSSProperties}
    >
      {children}
    </h2>
  );
}

// ─── Page ───────────────────────────────────────────────────────────
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
  const result = await fetchDetail(bundle);
  if (!result.ok) {
    return (
      <div dir="rtl" className="mx-auto max-w-3xl px-4 py-16">
        <div className="border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-6">
          <p className="text-[14px] font-semibold text-amber-900 dark:text-amber-200">
            دادهٔ این صفحه در این لحظه از سرور قابل دریافت نبود.
          </p>
          <p className="text-[12.5px] text-amber-800 dark:text-amber-300 mt-2 font-mono">
            {result.error}
          </p>
          <p className="text-[12.5px] text-slate-600 dark:text-slate-400 mt-3">
            صفحه چند دقیقه دیگر دوباره تلاش می‌کند. اگر این پیام پایدار است،
            احتمالاً ISR کش یک پاسخ خطا را ذخیره کرده — یک استقرار جدید آن را پاک می‌کند.
          </p>
        </div>
        <Link
          href={`/${locale}/lab/worldviews`}
          className="inline-flex items-center gap-1.5 text-[13px] text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 mt-6 underline underline-offset-4 decoration-slate-300"
        >
          <ArrowLeft className="w-4 h-4" />
          بازگشت به همهٔ گروه‌ها
        </Link>
      </div>
    );
  }
  const data = result.data;

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
  const windowLabel = formatDateRangeFa(data.window_start, data.window_end);

  return (
    <div dir="rtl" className="mx-auto max-w-3xl px-4 py-8">
      {/* Top breadcrumb */}
      <Link
        href={`/${locale}/lab/worldviews`}
        className="inline-flex items-center gap-1 text-[12px] text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 mb-10"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        همهٔ گروه‌ها
      </Link>

      {/* Editorial header — eyebrow → headline → tabular metadata */}
      <header className={`border-t-[3px] ${theme.accentBorder} pt-6 mb-6`}>
        <div className="flex items-center gap-2.5 mb-1">
          <span className={`inline-block w-3 h-3 ${theme.accentDot}`} aria-hidden="true" />
          <p className="text-[12.5px] tracking-wider font-semibold text-slate-500 dark:text-slate-400">
            {theme.side} · بازهٔ {windowLabel}
          </p>
        </div>
        <h1
          className="text-[36px] font-bold leading-[1.15] text-slate-900 dark:text-slate-100 ms-[22px]"
          style={{ textWrap: "pretty" } as React.CSSProperties}
        >
          {theme.label}
        </h1>
        <dl className="ms-[22px] mt-4 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-slate-600 dark:text-slate-400">
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-400 dark:text-slate-500">مقاله</dt>
            <dd className="font-semibold tabular-nums">{toFa(data.article_count)}</dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-400 dark:text-slate-500">منبع</dt>
            <dd className="font-semibold tabular-nums">{toFa(data.source_count)}</dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-400 dark:text-slate-500">پوشش تحلیل</dt>
            <dd className="font-semibold tabular-nums">{toFa(Math.round(data.coverage_pct))}٪</dd>
          </div>
        </dl>
      </header>

      {/* Editorial caveat — italic, lighter weight, sits as a stand-alone note */}
      <p className="text-[13px] leading-7 text-slate-500 dark:text-slate-400 mb-12 italic">
        تصویری از <strong className="font-semibold not-italic">محیط اطلاعاتی</strong> این رسانه‌ها در هفتهٔ گذشته،
        نه باور خوانندگان یا یک گروه اجتماعی.
      </p>

      {data.status !== "ok" || !s ? (
        <div className="text-[15px] leading-8 text-slate-600 dark:text-slate-400 border-r-2 border-slate-300 dark:border-slate-700 pr-5">
          <p>
            این بازه با {toFa(data.article_count)} مقاله از {toFa(data.source_count)} منبع
            به آستانهٔ تولید چکیده نرسید — حداقل ۲۰ مقاله از ۲ منبع لازم است.
          </p>
        </div>
      ) : groundedOut ? (
        <div className="space-y-12">
          <p className="text-[15px] leading-8 text-slate-600 dark:text-slate-400 border-r-2 border-slate-300 dark:border-slate-700 pr-5">
            این هفته هیچ ادعایی به آستانهٔ شواهد لازم نرسید
            — هر گزاره باید دست‌کم ۳ مقاله از ۲ منبع متمایز پشتش باشد،
            و این گروه با {toFa(data.source_count)} منبع تحت ردیابی به آن آستانه نمی‌رسد.
          </p>
          {s?.tone_profile?.description && (
            <section>
              <SectionLabel>لحن مسلط</SectionLabel>
              <p className="text-[15px] leading-8 text-slate-700 dark:text-slate-300 italic mt-5">
                {s.tone_profile.description}
              </p>
            </section>
          )}
          {absent.length > 0 && (
            <section>
              <SectionLabel>چه نگفتند</SectionLabel>
              <div className="mt-2">
                {absent.map((item, i) => (
                  <AbsenceBlock key={`ab${i}`} item={item} ordinal={i + 1} />
                ))}
              </div>
            </section>
          )}
        </div>
      ) : (
        <div className="space-y-14">
          {/* Tone signature — pull-quote style at the top */}
          {s.tone_profile?.description && (
            <blockquote className="text-[16px] leading-[1.95] text-slate-700 dark:text-slate-300 italic border-r-2 border-slate-300 dark:border-slate-700 pr-5">
              {s.tone_profile.description}
              {(s.tone_profile.dominant || s.tone_profile.alt) && (
                <footer className="mt-3 not-italic text-[12px] tracking-wider font-semibold text-slate-400 dark:text-slate-500">
                  {s.tone_profile.dominant && <span>لحن غالب: {s.tone_profile.dominant}</span>}
                  {s.tone_profile.alt && <span className="ms-4">لحن ثانوی: {s.tone_profile.alt}</span>}
                </footer>
              )}
            </blockquote>
          )}

          {beliefs.length > 0 && (
            <section>
              <SectionLabel>چه گفتند</SectionLabel>
              <div className="mt-2">
                {beliefs.map((item, i) => (
                  <BeliefBlock
                    key={`cb${i}`}
                    kind="core_beliefs"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    articles={articles}
                    locale={locale}
                    ordinal={i + 1}
                  />
                ))}
              </div>
            </section>
          )}

          {emphasized.length > 0 && (
            <section>
              <SectionLabel>چه برجسته کردند</SectionLabel>
              <div className="mt-2">
                {emphasized.map((item, i) => (
                  <BeliefBlock
                    key={`em${i}`}
                    kind="emphasized"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    articles={articles}
                    locale={locale}
                    ordinal={i + 1}
                  />
                ))}
              </div>
            </section>
          )}

          {predictions.length > 0 && (
            <section>
              <SectionLabel>چه انتظاری ساختند</SectionLabel>
              <div className="mt-2">
                {predictions.map((item, i) => (
                  <BeliefBlock
                    key={`pr${i}`}
                    kind="predictions_primed"
                    idx={i}
                    item={item}
                    evidence={evidence}
                    articles={articles}
                    locale={locale}
                    ordinal={i + 1}
                  />
                ))}
              </div>
            </section>
          )}

          {absent.length > 0 && (
            <section>
              <SectionLabel>و چه نگفتند</SectionLabel>
              <div className="mt-2">
                {absent.map((item, i) => (
                  <AbsenceBlock key={`ab${i}`} item={item} ordinal={i + 1} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Footer back-link — long pages need a return path at the bottom */}
      <div className="mt-16 pt-8 border-t border-slate-200 dark:border-slate-800">
        <Link
          href={`/${locale}/lab/worldviews`}
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 underline underline-offset-4 decoration-slate-300 dark:decoration-slate-600"
        >
          <ArrowLeft className="w-4 h-4" />
          بازگشت به همهٔ گروه‌ها
        </Link>
      </div>
    </div>
  );
}
