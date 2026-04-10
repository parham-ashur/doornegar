import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";
import type { TopicBrief } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchTopics(): Promise<TopicBrief[]> {
  try {
    const res = await fetch(`${API}/api/v1/lab/topics?page_size=50`, { next: { revalidate: 30 } });
    if (!res.ok) return [];
    const data = await res.json();
    return data.topics || [];
  } catch {
    return [];
  }
}

const LEANING_COLORS: Record<string, string> = {
  pro_regime: "text-red-500",
  reformist: "text-amber-600 dark:text-amber-400",
  opposition: "text-blue-600 dark:text-blue-400",
  monarchist: "text-purple-600 dark:text-purple-400",
  neutral: "text-emerald-600 dark:text-emerald-400",
};

const LEANING_LABELS: Record<string, string> = {
  pro_regime: "حکومتی",
  reformist: "اصلاح‌طلب",
  opposition: "اپوزیسیون",
  monarchist: "سلطنت‌طلب",
  neutral: "مستقل",
};

function ModeBadge({ mode }: { mode: string }) {
  return (
    <span className={`px-2 py-0.5 text-[10px] font-bold border ${
      mode === "debate"
        ? "border-amber-400 text-amber-600 dark:text-amber-400"
        : "border-blue-400 text-blue-600 dark:text-blue-400"
    }`}>
      {mode === "debate" ? "بحث" : "خبر"}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════
   TYPE 1: Hero — full data (articles + analysts + image)
   ═══════════════════════════════════════════════════════════ */
function HeroCard({ topic, locale }: { topic: TopicBrief; locale: string }) {
  return (
    <Link href={`/${locale}/lab/${topic.id}`} className="group block border-b border-slate-200 dark:border-slate-800 py-8">
      <div className="flex items-center gap-3 mb-3">
        <ModeBadge mode={topic.mode} />
        <span className="text-[11px] text-slate-400">{topic.article_count} مقاله</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Right (RTL): title + summary + per-side lines */}
        <div className="lg:col-span-5">
          <h2 className="text-[26px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
            {topic.title_fa}
          </h2>
          {topic.analysis_fa && (
            <p className="mt-3 text-[13px] leading-7 text-slate-600 dark:text-slate-400 line-clamp-3">
              {topic.analysis_fa}
            </p>
          )}
        </div>
        {/* Center: image */}
        {topic.image_url && (
          <div className="lg:col-span-4">
            <div className="aspect-[16/10] overflow-hidden bg-slate-100 dark:bg-slate-800">
              <SafeImage src={topic.image_url} className="h-full w-full object-cover" />
            </div>
          </div>
        )}
        {/* Left (RTL): analyst preview */}
        <div className="lg:col-span-3 lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6 flex flex-col justify-center">
          <h4 className="text-[11px] font-bold text-slate-400 mb-3">تحلیلگران</h4>
          <p className="text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-4">
            {topic.analysis_fa || "تحلیل در حال آماده‌سازی..."}
          </p>
        </div>
      </div>
    </Link>
  );
}

/* ═══════════════════════════════════════════════════════════
   TYPE 2: Large Thumbnail — articles + analysts, secondary
   ═══════════════════════════════════════════════════════════ */
function LargeThumbCard({ topic, locale }: { topic: TopicBrief; locale: string }) {
  return (
    <Link href={`/${locale}/lab/${topic.id}`} className="group block">
      {topic.image_url && (
        <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800 mb-3">
          <SafeImage src={topic.image_url} className="h-full w-full object-cover" />
        </div>
      )}
      <ModeBadge mode={topic.mode} />
      <h3 className="mt-2 text-[16px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
        {topic.title_fa}
      </h3>
      <p className="mt-1 text-[11px] text-slate-400">{topic.article_count} مقاله</p>
      {topic.analysis_fa && (
        <p className="mt-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
          {topic.analysis_fa}
        </p>
      )}
      {topic.has_analysts && (
        <p className="mt-1.5 text-[11px] leading-4 text-slate-400 italic line-clamp-2">
          تحلیلگران: دیدگاه‌های مختلف درباره این موضوع...
        </p>
      )}
    </Link>
  );
}

/* ═══════════════════════════════════════════════════════════
   TYPE 3: Box — articles + analysts, like main page hero
   ═══════════════════════════════════════════════════════════ */
function BoxCard({ topic, locale }: { topic: TopicBrief; locale: string }) {
  return (
    <Link href={`/${locale}/lab/${topic.id}`}
      className="group grid grid-cols-1 sm:grid-cols-5 gap-5">
      <div className="sm:col-span-3">
        <ModeBadge mode={topic.mode} />
        <h3 className="mt-2 text-[18px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
          {topic.title_fa}
        </h3>
        <p className="mt-1 text-[11px] text-slate-400">{topic.article_count} مقاله</p>
        {topic.analysis_fa && (
          <p className="mt-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">
            {topic.analysis_fa}
          </p>
        )}
        {topic.has_analysts && (
          <div className="mt-3 border-t border-slate-200 dark:border-slate-800 pt-2">
            <span className="text-[10px] font-bold text-slate-400">تحلیلگران</span>
            <p className="mt-0.5 text-[11px] leading-4 text-slate-400 italic line-clamp-2">
              بررسی دیدگاه‌های مختلف تحلیلگران درباره این موضوع
            </p>
          </div>
        )}
      </div>
      {topic.image_url && (
        <div className="sm:col-span-2 aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
          <SafeImage src={topic.image_url} className="h-full w-full object-cover" />
        </div>
      )}
    </Link>
  );
}

/* ═══════════════════════════════════════════════════════════
   TYPE 4: Articles-only — no analyst, no image, text only
   ═══════════════════════════════════════════════════════════ */
function ArticlesOnlyCard({ topic, locale }: { topic: TopicBrief; locale: string }) {
  return (
    <Link href={`/${locale}/lab/${topic.id}`} className="group block">
      <ModeBadge mode={topic.mode} />
      <h3 className="mt-2 text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
        {topic.title_fa}
      </h3>
      <p className="mt-1 text-[11px] text-slate-400">{topic.article_count} مقاله</p>
      {topic.analysis_fa && (
        <p className="mt-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">
          {topic.analysis_fa}
        </p>
      )}
    </Link>
  );
}

/* ═══════════════════════════════════════════════════════════
   TYPE 5: Analyst-only — no articles, viewpoints + sources
   ═══════════════════════════════════════════════════════════ */
function AnalystOnlyCard({ topic, locale }: { topic: TopicBrief; locale: string }) {
  return (
    <Link href={`/${locale}/lab/${topic.id}`} className="group block border border-slate-200 dark:border-slate-800 p-5">
      <div className="flex items-center gap-2 mb-2">
        <span className="px-2 py-0.5 text-[10px] font-bold border border-amber-400 text-amber-600 dark:text-amber-400">تحلیل</span>
      </div>
      <h3 className="text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
        {topic.title_fa}
      </h3>
      {topic.analysis_fa && (
        <p className="mt-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
          {topic.analysis_fa}
        </p>
      )}
      <p className="mt-2 text-[11px] text-slate-400">دیدگاه‌های متفاوت تحلیلگران</p>
    </Link>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════════ */
export default async function LabPage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  const allTopics = await fetchTopics();

  if (allTopics.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-6 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
        <p className="mt-2 text-sm text-slate-500">از طریق API یک موضوع جدید بسازید</p>
      </div>
    );
  }

  // Categorize topics by data availability
  const full: TopicBrief[] = [];      // has_articles + has_analysts + image
  const articlesOnly: TopicBrief[] = [];
  const analystOnly: TopicBrief[] = [];

  for (const t of allTopics) {
    if (t.has_articles && t.has_analysts) {
      full.push(t);
    } else if (t.has_articles) {
      articlesOnly.push(t);
    } else if (t.has_analysts) {
      analystOnly.push(t);
    } else {
      articlesOnly.push(t); // fallback
    }
  }

  const hero = full[0] || null;
  const secondary = full.slice(1, 3); // large thumb + box
  const remaining = full.slice(3);

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-6 lg:px-8">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 py-6">
        <div>
          <h1 className="text-xl font-black text-slate-900 dark:text-white">آزمایشگاه تحلیل</h1>
          <p className="mt-0.5 text-[12px] text-slate-400">{allTopics.length} موضوع</p>
        </div>
      </div>

      {/* ── HERO (Type 1) ── */}
      {hero && <HeroCard topic={hero} locale={locale} />}

      {/* ── Secondary row: Large Thumb + Box (Types 2 & 3) ── */}
      {secondary.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-7 gap-6">
          {secondary[0] && (
            <div className="lg:col-span-4 lg:border-l border-slate-200 dark:border-slate-800 lg:pl-6">
              <LargeThumbCard topic={secondary[0]} locale={locale} />
            </div>
          )}
          {secondary[1] && (
            <div className="lg:col-span-8">
              <BoxCard topic={secondary[1]} locale={locale} />
            </div>
          )}
        </div>
      )}

      {/* ── Remaining full topics as boxes ── */}
      {remaining.length > 0 && (
        <div className="border-b border-slate-200 dark:border-slate-800 py-7 space-y-6">
          {remaining.map((t) => (
            <BoxCard key={t.id} topic={t} locale={locale} />
          ))}
        </div>
      )}

      {/* ── Articles-only row (Type 4) — up to 3 per row ── */}
      {articlesOnly.length > 0 && (
        <div className={`grid grid-cols-1 sm:grid-cols-${Math.min(articlesOnly.length, 3)} border-b border-slate-200 dark:border-slate-800`}>
          {articlesOnly.map((t, i) => (
            <div key={t.id}
              className={`py-7 ${i > 0 ? "sm:pr-6 sm:border-r border-slate-200 dark:border-slate-800" : ""} ${i < articlesOnly.length - 1 ? "sm:pl-6" : ""}`}>
              <ArticlesOnlyCard topic={t} locale={locale} />
            </div>
          ))}
        </div>
      )}

      {/* ── Analyst-only (Type 5) ── */}
      {analystOnly.length > 0 && (
        <div className="py-7 space-y-4">
          {analystOnly.map((t) => (
            <AnalystOnlyCard key={t.id} topic={t} locale={locale} />
          ))}
        </div>
      )}
    </div>
  );
}
