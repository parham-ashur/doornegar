/**
 * Related stories — horizontal-scroll slider shown at the bottom of a
 * story page. Populated from the `/api/v1/stories/{id}/related`
 * endpoint, which returns arc siblings first (curated narrative
 * grouping) and fills the rest with centroid-cosine neighbors.
 *
 * Snap-scroll on mobile, edge-to-edge via `-mx-4` so cards peek off
 * the right edge on small screens. Server Component — no client JS;
 * data is fetched at the page level and passed in via props.
 */

import Link from "next/link";
import SafeImage from "@/components/common/SafeImage";
import type { RelatedStory } from "@/lib/api";
import { toFa } from "@/lib/utils";

function fmtRelative(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days < 1) return "امروز";
  if (days === 1) return "دیروز";
  if (days < 7) return `${toFa(days)} روز پیش`;
  if (days < 30) return `${toFa(Math.floor(days / 7))} هفته پیش`;
  return `${toFa(Math.floor(days / 30))} ماه پیش`;
}

export default function RelatedStoriesSlider({
  stories,
  currentArcId,
  locale = "fa",
}: {
  stories: RelatedStory[];
  currentArcId?: string | null;
  locale?: string;
}) {
  if (!stories || stories.length === 0) return null;

  return (
    <section
      dir="rtl"
      className="mt-10 pt-6 border-t border-slate-200 dark:border-slate-800 -mx-4 sm:mx-0"
      aria-label="خبرهای مرتبط"
    >
      <div className="px-4 sm:px-0 mb-4 flex items-baseline justify-between">
        <h2 className="text-base font-black text-slate-900 dark:text-white">خبرهای مرتبط</h2>
        <span className="text-[11px] text-slate-400">{toFa(stories.length)} خبر</span>
      </div>

      <div
        className="flex gap-3 overflow-x-auto pb-4 px-4 sm:px-0 snap-x snap-mandatory scrollbar-thin"
        style={{ scrollbarWidth: "thin" }}
      >
        {stories.map((s) => {
          const isArcSibling = currentArcId && s.arc_id === currentArcId;
          return (
            <Link
              key={s.id}
              href={`/${locale}/stories/${s.id}`}
              className="shrink-0 w-[72vw] sm:w-60 md:w-64 snap-start border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40 hover:border-blue-400 dark:hover:border-blue-600 transition-colors group"
            >
              <div className="relative aspect-[16/10] bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <SafeImage
                  src={s.image_url}
                  sizes="(max-width: 640px) 72vw, 256px"
                />
                {isArcSibling && (
                  <span className="absolute top-2 right-2 text-[10px] font-bold px-2 py-0.5 bg-blue-600 text-white">
                    روایت نزدیک
                  </span>
                )}
              </div>
              <div className="p-3">
                <h3 className="text-[13px] leading-6 font-bold text-slate-900 dark:text-slate-100 group-hover:text-blue-700 dark:group-hover:text-blue-300 line-clamp-3">
                  {s.title_fa || s.title_en}
                </h3>
                <div className="mt-2 flex items-center gap-3 text-[11px] text-slate-500">
                  <span>{toFa(s.source_count)} رسانه</span>
                  <span>·</span>
                  <span>{toFa(s.article_count)} مقاله</span>
                  {s.first_published_at && (
                    <>
                      <span>·</span>
                      <span>{fmtRelative(s.first_published_at)}</span>
                    </>
                  )}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
