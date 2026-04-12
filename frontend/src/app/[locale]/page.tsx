import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";
import AnalystTicker from "@/components/common/AnalystTicker";
import type { StoryBrief } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";

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
  const published = story.first_published_at
    ? formatRelativeTime(story.first_published_at, "fa")
    : null;
  const updated = story.updated_at
    ? formatRelativeTime(story.updated_at, "fa")
    : null;
  const showUpdated = updated && story.updated_at && story.first_published_at
    && Math.abs(new Date(story.updated_at).getTime() - new Date(story.first_published_at).getTime()) > 3600000;
  const hasSides = story.state_pct > 0 || story.diaspora_pct > 0;
  return (
    <div className="mt-1.5" dir="rtl">
      <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-5">
        {story.source_count} رسانه · {story.article_count} مقاله
        {published && <span>{" · "}نشر {published}</span>}
        {showUpdated && <span>{" · "}به‌روز: {updated}</span>}
      </p>
      {hasSides && (
        <p className="text-[11px] leading-5 mt-0.5">
          {story.state_pct > 0 && <span className="text-[#1e3a5f] dark:text-blue-300">محافظه‌کار {story.state_pct}٪</span>}
          {story.state_pct > 0 && story.diaspora_pct > 0 && <span className="text-slate-300 dark:text-slate-600"> · </span>}
          {story.diaspora_pct > 0 && <span className="text-[#ea580c] dark:text-orange-400">اپوزیسیون {story.diaspora_pct}٪</span>}
        </p>
      )}
    </div>
  );
}

// ─── Reusable section components ───────────────────────────────

function TextRow({ stories, summaries, locale }: { stories: StoryBrief[]; summaries: Record<string, string | null>; locale: string }) {
  if (stories.length === 0) return null;
  return (
    <div className={`grid grid-cols-1 ${stories.length === 1 ? "" : stories.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3"} border-b border-slate-200 dark:border-slate-800`}>
      {stories.map((s, i) => (
        <Link key={s.id} href={`/${locale}/stories/${s.id}`}
          className={`group block py-7 ${i > 0 ? "sm:pr-6 sm:border-r border-slate-200 dark:border-slate-800" : ""} ${i < stories.length - 1 ? "sm:pl-6" : ""}`}>
          <h3 className="text-[17px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-1">
            {s.title_fa}
          </h3>
          <Meta story={s} />
          <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-3">{summaries[s.id] || s.title_fa}</p>
        </Link>
      ))}
    </div>
  );
}

function ImageGrid({ stories, summaries, locale }: { stories: StoryBrief[]; summaries: Record<string, string | null>; locale: string }) {
  if (stories.length === 0) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 border-b border-slate-200 dark:border-slate-800 py-6">
      {stories.map((s) => (
        <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group block">
          <div className="aspect-[4/3] w-full overflow-hidden bg-slate-100 dark:bg-slate-800 mb-3">
            <SafeImage src={s.image_url} className="h-full w-full object-cover" />
          </div>
          <h3 className="text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 overflow-hidden text-ellipsis whitespace-nowrap">
            {s.title_fa}
          </h3>
          <Meta story={s} />
          <p className="mt-2 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">{summaries[s.id] || s.title_fa}</p>
        </Link>
      ))}
    </div>
  );
}

function FeatureRow({ stories, summaries, locale, mirror }: { stories: StoryBrief[]; summaries: Record<string, string | null>; locale: string; mirror?: boolean }) {
  if (stories.length === 0) return null;
  return (
    <div className="border-b border-slate-200 dark:border-slate-800">
      {stories.map((s, i) => (
        <Link key={s.id} href={`/${locale}/stories/${s.id}`}
          className={`group grid grid-cols-1 sm:grid-cols-5 gap-5 py-7 ${i > 0 ? "border-t border-slate-200 dark:border-slate-800" : ""}`}>
          {mirror ? (
            <>
              <div className="sm:col-span-3 aspect-[16/10] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={s.image_url} className="h-full w-full object-cover" />
              </div>
              <div className="sm:col-span-2">
                <h3 className="text-[20px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                  {s.title_fa}
                </h3>
                <Meta story={s} />
                {summaries[s.id] && (
                  <div className="mt-2">
                    <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-6">{summaries[s.id]}</p>
                    <span className="text-[12px] text-blue-600 dark:text-blue-400 mt-0.5 inline-block">ادامه ←</span>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="sm:col-span-2">
                <h3 className="text-[20px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                  {s.title_fa}
                </h3>
                <Meta story={s} />
                {summaries[s.id] && (
                  <div className="mt-2">
                    <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-6">{summaries[s.id]}</p>
                    <span className="text-[12px] text-blue-600 dark:text-blue-400 mt-0.5 inline-block">ادامه ←</span>
                  </div>
                )}
              </div>
              <div className="sm:col-span-3 aspect-[16/10] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={s.image_url} className="h-full w-full object-cover" />
              </div>
            </>
          )}
        </Link>
      ))}
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  const stories = await fetchAPI<StoryBrief[]>("/api/v1/stories/trending?limit=50") || [];

  if (stories.length === 0) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-24 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">هنوز موضوعی ایجاد نشده</h2>
        <p className="mt-2 text-sm text-slate-500">پس از اجرای خط‌لوله داده، موضوعات خبری اینجا نمایش داده می‌شوند</p>
      </div>
    );
  }

  const sorted = [...stories];

  // ── Section 1: Hero (first 19 stories) ──
  const hero = sorted[0];
  const leftTextStories = sorted.slice(1, 4);
  const row2Stories = sorted.slice(4, 6);
  const remaining1 = sorted.slice(6);
  const shortTitle = remaining1.filter(s => (s.title_fa?.length || 100) <= 45);
  const midRow = (shortTitle.length >= 3 ? shortTitle : remaining1).slice(0, 3);
  const midRowIds = new Set(midRow.map(s => s.id));
  const afterMid = remaining1.filter(s => !midRowIds.has(s.id));
  const bottomLeft = afterMid.slice(0, 2);
  const bottomRight = afterMid.slice(2, 6);
  const bottomTextRow = afterMid.slice(6, 7);

  // Total used in section 1
  const section1Count = 1 + leftTextStories.length + row2Stories.length + midRow.length + bottomLeft.length + bottomRight.length + bottomTextRow.length;
  const overflow = sorted.slice(section1Count);

  // ── Overflow: build sections sequentially, each consuming what it needs ──
  // Section types cycle: text(3) → images(4) → feature(2) → text(3) → images(4) → feature(2)...
  // Odd cycles: mirror the feature rows
  type Section = { type: "text"; stories: StoryBrief[] }
    | { type: "images"; stories: StoryBrief[] }
    | { type: "hero-thumb"; stories: StoryBrief[] }
    | { type: "hero-repeat"; stories: StoryBrief[] };

  const sections: Section[] = [];
  // Pattern: hero-thumb(2) → hero-repeat(4) → text(3)
  const pattern = [
    { type: "hero-thumb" as const, size: 2 },
    { type: "hero-repeat" as const, size: 4 },
    { type: "text" as const, size: 3 },
  ];
  let cursor = 0;

  // Only one cycle, then stop
  for (const step of pattern) {
    if (cursor >= overflow.length) break;
    const chunk = overflow.slice(cursor, cursor + step.size);
    if (chunk.length === 0) break;
    sections.push({ type: step.type, stories: chunk } as Section);
    cursor += chunk.length;
  }

  // ── Fetch summaries (all in parallel) ──
  const allStoriesForSummary = new Set<string>();
  if (hero) allStoriesForSummary.add(hero.id);
  for (const s of [...leftTextStories, ...row2Stories, ...bottomLeft, ...bottomRight, ...bottomTextRow, ...midRow]) {
    allStoriesForSummary.add(s.id);
  }
  for (const sec of sections) {
    for (const s of sec.stories) allStoriesForSummary.add(s.id);
  }
  const summaryIds = Array.from(allStoriesForSummary);
  const summaryResults = await Promise.all(summaryIds.map((id) => fetchSummary(id)));
  const allSummaries: Record<string, string | null> = {};
  summaryIds.forEach((id, i) => { allSummaries[id] = summaryResults[i]; });

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-0 md:px-6 lg:px-8">

      {/* ════════════════════════════════════════════ */}
      {/* MOBILE LAYOUT (phones only, below md)        */}
      {/* ════════════════════════════════════════════ */}
      <MobileHome
        hero={hero}
        stories={sorted}
        summaries={allSummaries}
        locale={locale}
      />

      {/* ════════════════════════════════════════════ */}
      {/* DESKTOP LAYOUT (tablet and up)                */}
      {/* ════════════════════════════════════════════ */}
      <div className="hidden md:block">

      {/* ROW 1: Hero */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
        {hero && (
          <div className="lg:col-span-4 flex flex-col justify-center">
            <Link href={`/${locale}/stories/${hero.id}`} className="group block">
              <h1 className="text-[26px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                {hero.title_fa}
              </h1>
              <Meta story={hero} />
              {allSummaries[hero.id] && (
                <div className="mt-4">
                  <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{allSummaries[hero.id]}</p>
                  <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                </div>
              )}
            </Link>
            <AnalystTicker />
          </div>
        )}
        {hero && (
          <div className="lg:col-span-5">
            <Link href={`/${locale}/stories/${hero.id}`} className="block">
              <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
              </div>
            </Link>
          </div>
        )}
        <div className="lg:col-span-3 lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6 flex flex-col justify-center">
          {leftTextStories.length > 0 && (() => {
            const s = leftTextStories[leftTextStories.length - 1];
            return (
              <Link href={`/${locale}/stories/${s.id}`} className="group block">
                <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800">
                  <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                </div>
                <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                  {s.title_fa}
                </h3>
                <Meta story={s} />
                {allSummaries[s.id] && (
                  <p className="mt-1.5 text-[12px] leading-[20px] text-slate-400 dark:text-slate-500 line-clamp-3">{allSummaries[s.id]}</p>
                )}
              </Link>
            );
          })()}
        </div>
      </div>

      {/* ROW 2: hero-thumb layout (thumbnail right, big image+text left) */}
      {row2Stories.length >= 2 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
          {/* Right (RTL first): thumbnail with summary */}
          <div className="lg:col-span-3 lg:border-l border-slate-200 dark:border-slate-800 lg:pl-6 flex flex-col justify-center">
            <Link href={`/${locale}/stories/${row2Stories[1].id}`} className="group block">
              <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={row2Stories[1].image_url} className="h-full w-full object-cover" />
              </div>
              <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                {row2Stories[1].title_fa}
              </h3>
              <Meta story={row2Stories[1]} />
              <p className="mt-1.5 text-[12px] leading-[20px] text-slate-400 dark:text-slate-500 line-clamp-3">{allSummaries[row2Stories[1].id] || row2Stories[1].title_fa}</p>
            </Link>
          </div>
          {/* Center: title + summary */}
          <div className="lg:col-span-4 flex flex-col justify-center">
            <Link href={`/${locale}/stories/${row2Stories[0].id}`} className="group block">
              <h2 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                {row2Stories[0].title_fa}
              </h2>
              <Meta story={row2Stories[0]} />
              {allSummaries[row2Stories[0].id] && (
                <div className="mt-4">
                  <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{allSummaries[row2Stories[0].id]}</p>
                  <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                </div>
              )}
            </Link>
          </div>
          {/* Left (RTL last): big image */}
          <div className="lg:col-span-5">
            <Link href={`/${locale}/stories/${row2Stories[0].id}`} className="block">
              <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                <SafeImage src={row2Stories[0].image_url} className="h-full w-full object-cover" />
              </div>
            </Link>
          </div>
        </div>
      )}

      {/* ROW 3: Text-only */}
      <TextRow stories={midRow} summaries={allSummaries} locale={locale} />

      {/* ROW 4: Feature + thumbnails */}
      {(bottomLeft.length > 0 || bottomRight.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800">
          <div className="lg:col-span-8 py-7 lg:pl-8 lg:border-l border-slate-200 dark:border-slate-800">
            {bottomLeft.map((s, i) => (
              <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                className={`group grid grid-cols-1 sm:grid-cols-5 gap-5 ${i > 0 ? "pt-5 mt-5 border-t border-slate-200 dark:border-slate-800" : ""}`}>
                <div className="sm:col-span-2">
                  <h3 className="text-[20px] font-extrabold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                    {s.title_fa}
                  </h3>
                  <Meta story={s} />
                  {allSummaries[s.id] && (
                    <div className="mt-2">
                      <p className="text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-4">{allSummaries[s.id]}</p>
                      <span className="text-[12px] text-blue-600 dark:text-blue-400 mt-0.5 inline-block">ادامه ←</span>
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
            <div className="grid grid-cols-2 gap-5">
              {bottomRight.map((s) => (
                <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group block">
                  <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                  </div>
                  <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                    {s.title_fa}
                  </h3>
                  <Meta story={s} />
                  {allSummaries[s.id] && (
                    <p className="mt-1 text-[11px] leading-4 text-slate-400 dark:text-slate-500 line-clamp-2">{allSummaries[s.id]}</p>
                  )}
                </Link>
              ))}
            </div>
            {bottomTextRow.map((s) => (
              <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                className="group block pt-5 mt-5 border-t border-slate-200 dark:border-slate-800">
                <h3 className="text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                  {s.title_fa}
                </h3>
                <Meta story={s} />
                {allSummaries[s.id] && (
                  <p className="mt-1.5 text-[12px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">{allSummaries[s.id]}</p>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════ */}
      {/* OVERFLOW: Sections cycle text(3)→images(4)→feature(2) */}
      {/* ════════════════════════════════════════════ */}
      {sections.map((sec, i) => {
        if (sec.type === "text") {
          return <TextRow key={`s${i}`} stories={sec.stories} summaries={allSummaries} locale={locale} />;
        }
        if (sec.type === "hero-thumb") {
          // Thumbnail on RIGHT, big image center, text on LEFT
          const mainStory = sec.stories[0];
          const thumbStory = sec.stories[1];
          if (!mainStory) return null;
          return (
            <div key={`s${i}`} className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
              {/* Right (RTL first): 1 thumbnail with summary */}
              {thumbStory && (
                <div className="lg:col-span-3 lg:border-l border-slate-200 dark:border-slate-800 lg:pl-6 flex flex-col justify-center">
                  <Link href={`/${locale}/stories/${thumbStory.id}`} className="group block">
                    <div className="aspect-[3/2] overflow-hidden bg-slate-100 dark:bg-slate-800">
                      <SafeImage src={thumbStory.image_url} className="h-full w-full object-cover" />
                    </div>
                    <h3 className="mt-2 text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 line-clamp-2">
                      {thumbStory.title_fa}
                    </h3>
                    <Meta story={thumbStory} />
                    <p className="mt-1.5 text-[12px] leading-[20px] text-slate-400 dark:text-slate-500 line-clamp-3">{allSummaries[thumbStory.id] || thumbStory.title_fa}</p>
                  </Link>
                </div>
              )}
              {/* Center: title + summary */}
              <div className="lg:col-span-4 flex flex-col justify-center">
                <Link href={`/${locale}/stories/${mainStory.id}`} className="group block">
                  <h2 className="text-[24px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                    {mainStory.title_fa}
                  </h2>
                  <Meta story={mainStory} />
                  {allSummaries[mainStory.id] && (
                    <div className="mt-4">
                      <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{allSummaries[mainStory.id]}</p>
                      <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                    </div>
                  )}
                </Link>
              </div>
              {/* Left (RTL last): big image */}
              <div className="lg:col-span-5">
                <Link href={`/${locale}/stories/${mainStory.id}`} className="block">
                  <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={mainStory.image_url} className="h-full w-full object-cover" />
                  </div>
                </Link>
              </div>
            </div>
          );
        }
        if (sec.type === "hero-repeat") {
          // Same as ROW 1: title+summary right, big image center, 3 text stories left
          const heroStory = sec.stories[0];
          const sideStories = sec.stories.slice(1);
          if (!heroStory) return null;
          return (
            <div key={`s${i}`} className="grid grid-cols-1 lg:grid-cols-12 border-b border-slate-200 dark:border-slate-800 py-8 gap-8">
              {/* Right (RTL): title + summary */}
              <div className="lg:col-span-4 flex flex-col justify-center">
                <Link href={`/${locale}/stories/${heroStory.id}`} className="group block">
                  <h1 className="text-[26px] font-black leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400">
                    {heroStory.title_fa}
                  </h1>
                  <Meta story={heroStory} />
                  <div className="mt-4">
                    <p className="text-[13px] leading-6 text-slate-500 dark:text-slate-400 line-clamp-4">{allSummaries[heroStory.id] || heroStory.title_fa}</p>
                    <span className="text-[13px] text-blue-600 dark:text-blue-400 mt-1 inline-block">ادامه ←</span>
                  </div>
                </Link>
              </div>
              {/* Center: big image */}
              <div className="lg:col-span-5">
                <Link href={`/${locale}/stories/${heroStory.id}`} className="block">
                  <div className="aspect-[16/10] w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                    <SafeImage src={heroStory.image_url} className="h-full w-full object-cover" />
                  </div>
                </Link>
              </div>
              {/* Left (RTL): 3 text stories sidebar */}
              <div className="lg:col-span-3 flex flex-col justify-between lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6">
                {sideStories.map((s, j) => (
                  <Link key={s.id} href={`/${locale}/stories/${s.id}`}
                    className={`group block ${j > 0 ? "pt-4 mt-4 border-t border-slate-200 dark:border-slate-800" : ""}`}>
                    <h3 className="text-[14px] font-bold leading-snug text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-400 overflow-hidden text-ellipsis whitespace-nowrap">
                      {s.title_fa}
                    </h3>
                    <p className="mt-1 text-[12px] text-slate-400">{s.source_count} رسانه · {s.article_count} مقاله</p>
                    {allSummaries[s.id] && (
                      <p className="mt-1.5 text-[13px] leading-5 text-slate-400 dark:text-slate-500 line-clamp-2">{allSummaries[s.id]}</p>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          );
        }
        return null;
      })}
      </div>
    </div>
  );
}


// ─── Mobile-only home layout (phones) ─────────────────────────────
function MobileHome({
  hero,
  stories,
  summaries,
  locale,
}: {
  hero: StoryBrief | undefined;
  stories: StoryBrief[];
  summaries: Record<string, string | null>;
  locale: string;
}) {
  if (!hero) return null;

  // Data slicing for mobile: hero + alternating blocks of (4 thumbnails, 3 text)
  const after = stories.slice(1);
  const blocks: { type: "thumbs" | "text"; items: StoryBrief[] }[] = [];
  let cursor = 0;
  const pattern: { type: "thumbs" | "text"; size: number }[] = [
    { type: "thumbs", size: 4 },
    { type: "text", size: 3 },
    { type: "thumbs", size: 4 },
    { type: "text", size: 3 },
    { type: "thumbs", size: 4 },
  ];
  for (const step of pattern) {
    const chunk = after.slice(cursor, cursor + step.size);
    if (chunk.length === 0) break;
    blocks.push({ type: step.type, items: chunk });
    cursor += chunk.length;
  }

  return (
    <div className="md:hidden">
      {/* Pattern 1: Hero with text on top of image */}
      <Link
        href={`/${locale}/stories/${hero.id}`}
        className="relative block border-b border-slate-200 dark:border-slate-800"
      >
        <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
          <SafeImage src={hero.image_url} className="h-full w-full object-cover" />
        </div>
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/50 to-transparent p-4 pt-16">
          <h1 className="text-[22px] font-black leading-snug text-white line-clamp-3">
            {hero.title_fa}
          </h1>
          <p className="mt-2 text-[11px] text-white/80">
            {hero.source_count} رسانه · {hero.article_count} مقاله
            {hero.state_pct > 0 && <span className="mr-2 text-red-300"> · محافظه‌کار {hero.state_pct}٪</span>}
            {hero.diaspora_pct > 0 && <span className="mr-2 text-blue-300"> · اپوزیسیون {hero.diaspora_pct}٪</span>}
          </p>
        </div>
      </Link>

      {/* Alternating pattern blocks */}
      {blocks.map((block, bi) => {
        if (block.type === "thumbs") {
          return (
            <div
              key={`m${bi}`}
              className="grid grid-cols-2 gap-4 p-4 border-b border-slate-200 dark:border-slate-800"
            >
              {block.items.map((s) => (
                <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="group block">
                  <div className="aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800 mb-2">
                    <SafeImage src={s.image_url} className="h-full w-full object-cover" />
                  </div>
                  <h3 className="text-[13px] font-bold leading-snug line-clamp-2 text-slate-900 dark:text-white">
                    {s.title_fa}
                  </h3>
                  <p className="mt-1 text-[10px] text-slate-400">
                    {s.source_count} رسانه · {s.article_count} مقاله
                  </p>
                </Link>
              ))}
            </div>
          );
        }
        // text pattern
        return (
          <div
            key={`m${bi}`}
            className="divide-y divide-slate-200 dark:divide-slate-800 border-b border-slate-200 dark:border-slate-800"
          >
            {block.items.map((s) => (
              <Link key={s.id} href={`/${locale}/stories/${s.id}`} className="block py-4 px-4">
                <h3 className="text-[15px] font-extrabold leading-snug text-slate-900 dark:text-white">
                  {s.title_fa}
                </h3>
                <p className="mt-1 text-[11px] text-slate-400">
                  {s.source_count} رسانه · {s.article_count} مقاله
                </p>
                {summaries[s.id] && (
                  <p className="mt-2 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-2">
                    {summaries[s.id]}
                  </p>
                )}
              </Link>
            ))}
          </div>
        );
      })}
    </div>
  );
}
