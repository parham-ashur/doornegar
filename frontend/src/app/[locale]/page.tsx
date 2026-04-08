import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";
import type { StoryBrief } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: 30 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchSummary(storyId: string): Promise<string | null> {
  try {
    const res = await fetch(`${API}/api/v1/stories/${storyId}/analysis`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    const data = await res.json();
    return data.summary_fa || null;
  } catch {
    return null;
  }
}

function Meta({ story }: { story: StoryBrief }) {
  return (
    <p className="mt-1.5 text-[11px] text-slate-400 dark:text-slate-500" dir="rtl">
      <span>{story.source_count} رسانه</span>
      <span>{" · "}</span>
      <span>{story.article_count} مقاله</span>
      {story.state_pct > 0 && <span className="text-red-500 mr-2">{" · "}حکومتی {story.state_pct}٪</span>}
      {story.independent_pct > 0 && <span className="text-emerald-600 mr-2">{" · "}مستقل {story.independent_pct}٪</span>}
      {story.diaspora_pct > 0 && <span className="text-blue-600 mr-2">{" · "}برون‌مرزی {story.diaspora_pct}٪</span>}
    </p>
  );
}

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  const stories = await fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=20") || [];

  // API returns stories sorted by priority desc, then trending_score desc
  const sorted = [...stories];
  const hero = sorted[0];
  const leftTextStories = sorted.slice(1, 4);
  const row2Stories = sorted.slice(4, 8);
  const remaining = sorted.slice(8);
  const shortTitle = remaining.filter(s => (s.title_fa?.length || 100) <= 45);
  const midRow = (shortTitle.length >= 3 ? shortTitle : remaining).slice(0, 3);
  const midRowIds = new Set(midRow.map(s => s.id));
  const afterMid = remaining.filter(s => !midRowIds.has(s.id));
  const bottomLeft = afterMid.slice(0, 2);
  const bottomRight = afterMid.slice(2, 6);
  const bottomTextRow = afterMid.slice(6, 8);

  // Fetch summaries
  const heroSummary = hero ? await fetchSummary(hero.id) : null;
  const leftSummaries: Record<string, string | null> = {};
  for (const s of leftTextStories) {
    leftSummaries[s.id] = await fetchSummary(s.id);
  }
  const row2Summaries: Record<string, string | null> = {};
  for (const s of row2Stories) {
    row2Summaries[s.id] = await fetchSummary(s.id);
  }
  const bottomSummaries: Record<string, string | null> = {};
  for (const s of [...bottomLeft, ...bottomTextRow]) {
    bottomSummaries[s.id] = await fetchSummary(s.id);
  }

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
        <p className="mt-2 text-sm text-slate-500">پس از اجرای خط‌لوله داده، موضوعات خبری اینجا نمایش داده می‌شوند</p>
      </div>
    );
  }

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-6 lg:px-8">

      {/* ── ROW 1: title+summary right | image center | 3 text stories left ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">

        {/* Right: hero title + summary */}
        {hero && (
          <div className="lg:col-span-4 flex flex-col justify-center">
            <Link href={`/${locale}/stories/${hero.id}`} className="group block">
              <h1 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                {hero.title_fa}
              </h1>
              <Meta story={hero} />
              {heroSummary && (
                <div className="mt-4">
                  <p className="text-[12px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{heroSummary}</p>
                  <span className="text-[12px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                </div>
              )}
            </Link>
          </div>
        )}

        {/* Center: hero image (smaller) */}
        {hero && (
          <div className="lg:col-span-5">
            <Link href={`/${locale}/stories/${hero.id}`} className="block">
              <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
              </div>
            </Link>
          </div>
        )}

        {/* Left: 3 text-only stories stacked */}
        <div className="lg:col-span-3 flex flex-col justify-between lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6">
          {leftTextStories.map((s, i) => (
            <Link
              key={s.id}
              href={`/${locale}/stories/${s.id}`}
              className={`group block ${i > 0 ? "pt-4 mt-4 border-t border-slate-200 dark:border-slate-800" : ""}`}
            >
              <h3 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 overflow-hidden text-ellipsis whitespace-nowrap">
                {s.title_fa}
              </h3>
              <p className="mt-1 text-[10px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
              {leftSummaries[s.id] && (
                <p className="mt-1.5 text-[12px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">{leftSummaries[s.id]}</p>
              )}
            </Link>
          ))}
        </div>
      </div>

      {/* ── ROW 2: 4 stories with equal images + summaries ── */}
      {row2Stories.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 border-b border-slate-200 dark:border-slate-800 py-6">
          {row2Stories.map((s, i) => {
            const summary = row2Summaries[s.id];
            return (
              <Link
                key={s.id}
                href={`/${locale}/stories/${s.id}`}
                className="group block"
              >
                <div className="aspect-[4/3] w-full overflow-hidden bg-slate-100 dark:bg-slate-800 mb-3">
                  <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                </div>
                <h3 className="text-[14px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 overflow-hidden text-ellipsis whitespace-nowrap">
                  {s.title_fa}
                </h3>
                <Meta story={s} />
                <p className="mt-2 text-[12px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">{summary || s.title_fa}</p>
              </Link>
            );
          })}
        </div>
      )}

      {/* ── ROW 3: 2-col text-only ── */}
      {midRow.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 border-b border-slate-200 dark:border-slate-800">
          {midRow.map((s, i) => (
            <Link key={s.id} href={`/${locale}/stories/${s.id}`}
              className={`group block py-7 ${i > 0 ? "sm:pr-6 sm:border-r border-slate-200 dark:border-slate-800" : ""} ${i < midRow.length - 1 ? "sm:pl-6" : ""}`}>
              <h3 className="text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-1">
                {s.title_fa}
              </h3>
              <Meta story={s} />
            </Link>
          ))}
        </div>
      )}

      {/* ── ROW 4: text+image stories with summaries | small grid right ── */}
      {(bottomLeft.length > 0 || bottomRight.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800">
          <div className="lg:col-span-8 py-7 lg:pl-8 lg:border-l border-slate-200 dark:border-slate-800">
            {bottomLeft.map((s, i) => (
              <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                className={`group grid grid-cols-1 sm:grid-cols-5 gap-5 ${i > 0 ? "pt-5 mt-5 border-t border-slate-200 dark:border-slate-800" : ""}`}>
                <div className="sm:col-span-2">
                  <h3 className="text-[18px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                    {s.title_fa}
                  </h3>
                  <Meta story={s} />
                  {bottomSummaries[s.id] && (
                    <div className="mt-2">
                      <p className="text-[12px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-6">{bottomSummaries[s.id]}</p>
                      <span className="text-[11px] text-blue-600 dark:text-blue-400 mt-0.5 inline-block">ادامه ←</span>
                    </div>
                  )}
                </div>
                <div className="sm:col-span-3 aspect-[16/10] overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                </div>
              </Link>
            ))}
          </div>

          <div className="lg:col-span-4 py-7 lg:pr-6">
            {/* 4 thumbnail grid */}
            <div className="grid grid-cols-2 gap-5">
              {bottomRight.map((s) => (
                <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group block">
                  <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                  </div>
                  <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                    {s.title_fa}
                  </h3>
                </Link>
              ))}
            </div>

            {/* 2 text stories under thumbnails */}
            {bottomTextRow.map((s, i) => (
              <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                className={`group block pt-5 mt-5 border-t border-slate-200 dark:border-slate-800`}>
                <h3 className="text-[13px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                  {s.title_fa}
                </h3>
                <p className="mt-1 text-[10px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
                {bottomSummaries[s.id] && (
                  <p className="mt-1.5 text-[11px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">
                    {bottomSummaries[s.id]}
                  </p>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
