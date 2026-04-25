import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { AlertTriangle, Newspaper } from "lucide-react";
import CoverageBar from "@/components/common/CoverageBar";
import { formatRelativeTime } from "@/lib/utils";
import type { StoryBrief } from "@/lib/types";

interface StoryCardProps {
  story: StoryBrief;
}

export default function StoryCard({ story }: StoryCardProps) {
  const locale = useLocale();
  const t = useTranslations();

  const title = locale === "fa" ? story.title_fa : story.title_en;

  return (
    <Link href={`/${locale}/stories/${story.id}`} className="card block group">
      {/* Blind spot badge */}
      {story.is_blindspot && (
        <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5" />
          {story.blindspot_type === "state_only"
            ? t("story.state_only")
            : t("story.diaspora_only")}
        </div>
      )}

      {/* Title */}
      <h3 className="text-base font-semibold leading-snug text-slate-900 group-hover:text-diaspora dark:text-white dark:group-hover:text-blue-400">
        {title}
      </h3>

      {/* Meta */}
      <div className="mt-2 flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
        <span className="flex items-center gap-1">
          <Newspaper className="h-3.5 w-3.5" />
          {t("story.sources_covered", { count: story.source_count })}
        </span>
        {story.first_published_at && (
          <span>{formatRelativeTime(story.first_published_at, locale)}</span>
        )}
      </div>

      {/* Coverage bar */}
      <div className="mt-3">
        <CoverageBar story={story} height="sm" />
      </div>
    </Link>
  );
}
