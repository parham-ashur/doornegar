/**
 * Related stories — horizontal-scroll slider shown at the bottom of a
 * story page. Populated from the `/api/v1/stories/{id}/related`
 * endpoint, which returns arc siblings first (curated narrative
 * grouping) and fills the rest with centroid-cosine neighbors.
 *
 * Snap-scroll on mobile, edge-to-edge via `-mx-4` so cards peek off
 * the right edge on small screens.
 *
 * Client component (lightweight) so it can read `?feedback=1` from
 * the URL and (a) propagate it onto related-story hrefs to keep the
 * rater in feedback mode while they navigate, and (b) surface a
 * small «بازخورد» chip on each card that opens the related story
 * directly into feedback mode.
 */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import SafeImageStatic from "@/components/common/SafeImageStatic";
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
  storyId,
}: {
  stories: RelatedStory[];
  currentArcId?: string | null;
  locale?: string;
  /** Parent story id — used to label «نامرتبط» feedback so an admin
   *  knows the related-pair was rejected from this story, not from
   *  the related card itself. */
  storyId?: string;
}) {
  const sp = useSearchParams();
  const feedbackMode = sp.get("feedback") === "1";
  const href = (id: string) =>
    `/${locale}/stories/${id}${feedbackMode ? "?feedback=1" : ""}`;

  if (!stories || stories.length === 0) return null;

  return (
    <section
      dir="rtl"
      className="mt-10 pt-6 border-t border-slate-200 dark:border-slate-800 -mx-4 sm:mx-0"
      aria-label="خبرهای مرتبط"
    >
      <div className="px-4 sm:px-0 mb-4 flex items-baseline justify-between">
        <h2 className="text-base font-black text-slate-900 dark:text-white">خبرهای مرتبط</h2>
        <span className="text-[12px] text-slate-400">{toFa(stories.length)} خبر</span>
      </div>

      <div
        className="flex gap-3 overflow-x-auto pb-4 px-4 sm:px-0 snap-x snap-mandatory scrollbar-thin"
        style={{ scrollbarWidth: "thin" }}
      >
        {stories.map((s) => {
          const isArcSibling = currentArcId && s.arc_id === currentArcId;
          return (
            <div
              key={s.id}
              className="relative shrink-0 w-[72vw] sm:w-60 md:w-64 snap-start group"
            >
              <Link
                href={href(s.id)}
                className="block border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40 hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
              >
                <div className="relative aspect-[16/10] bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <SafeImageStatic
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
                  <h3 className="text-[15px] leading-6 font-bold text-slate-900 dark:text-slate-100 group-hover:text-blue-700 dark:group-hover:text-blue-300 line-clamp-3">
                    {s.title_fa || s.title_en}
                  </h3>
                  <div className="mt-2 flex items-center gap-3 text-[12px] text-slate-500">
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
              {feedbackMode && (
                <RelatedFeedback
                  parentStoryId={storyId}
                  relatedStoryId={s.id}
                  relatedTitle={s.title_fa || s.title_en || ""}
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function RelatedFeedback({
  parentStoryId,
  relatedStoryId,
  relatedTitle,
}: {
  parentStoryId?: string;
  relatedStoryId: string;
  relatedTitle: string;
}) {
  const submit = async (kind: "unrelated" | "merge") => {
    try {
      const { antiSpamHeaders } = await import("@/lib/antiSpamToken");
      await fetch(`${API}/api/v1/improvements`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...antiSpamHeaders() },
        body: JSON.stringify({
          target_type: "story",
          target_id: relatedStoryId,
          issue_type: kind === "unrelated" ? "wrong_clustering" : "merge_stories",
          reason:
            kind === "unrelated"
              ? `از منظر خبرِ والد (${parentStoryId || "؟"}) این خبر مرتبط نیست`
              : `پیشنهاد ادغام با خبرِ والد ${parentStoryId || "؟"}`,
          context: { parent_story_id: parentStoryId, related_title: relatedTitle },
        }),
      });
    } catch {}
  };
  return (
    <div className="absolute top-2 left-2 z-10 flex flex-col gap-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity">
      <button
        type="button"
        title="نامرتبط با این خبر"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); submit("unrelated"); }}
        className="text-[10px] font-bold px-1.5 py-0.5 bg-slate-900/85 text-white border border-slate-700 hover:bg-red-600"
      >
        نامرتبط
      </button>
      <button
        type="button"
        title="ادغام با این خبر"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); submit("merge"); }}
        className="text-[10px] font-bold px-1.5 py-0.5 bg-slate-900/85 text-white border border-slate-700 hover:bg-blue-600"
      >
        ادغام
      </button>
    </div>
  );
}
