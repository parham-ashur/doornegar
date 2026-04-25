import { useLocale, useTranslations } from "next-intl";
import { ExternalLink } from "lucide-react";
import BiasSpectrum from "@/components/common/BiasSpectrum";
import SourceBadge from "@/components/source/SourceBadge";
import { formatRelativeTime } from "@/lib/utils";
import type { StoryArticleWithBias, StateAlignment } from "@/lib/types";

interface StoryComparisonProps {
  articles: StoryArticleWithBias[];
}

export default function StoryComparison({ articles }: StoryComparisonProps) {
  const locale = useLocale();
  const t = useTranslations();

  if (articles.length === 0) return null;

  // Sort: state media first, then semi-state, independent, diaspora
  const order: Record<string, number> = {
    state: 0,
    semi_state: 1,
    independent: 2,
    diaspora: 3,
  };
  const sorted = [...articles].sort(
    (a, b) =>
      (order[a.source_state_alignment || "diaspora"] || 3) -
      (order[b.source_state_alignment || "diaspora"] || 3)
  );

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {sorted.map((article) => {
        const title =
          locale === "fa"
            ? article.title_fa || article.title_original
            : article.title_en || article.title_original;

        const sourceName =
          locale === "fa"
            ? article.source_name_fa || article.source_name_en
            : article.source_name_en || article.source_name_fa;

        const biasScore = article.bias_scores?.[0];

        return (
          <div key={article.id} className="card flex flex-col">
            {/* Source header */}
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900 dark:text-white">
                  {sourceName}
                </span>
                {article.source_state_alignment && (
                  <SourceBadge
                    alignment={article.source_state_alignment as StateAlignment}
                  />
                )}
              </div>
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-slate-400 transition-colors hover:text-diaspora"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>

            {/* Title */}
            <h4 className="text-sm font-medium leading-snug text-slate-800 dark:text-slate-200">
              {title}
            </h4>

            {/* Summary */}
            {article.summary && (
              <p className="mt-2 line-clamp-3 text-xs text-slate-500 dark:text-slate-400">
                {article.summary}
              </p>
            )}

            {/* Bias spectrum */}
            {biasScore?.political_alignment != null && (
              <div className="mt-4">
                <BiasSpectrum
                  value={biasScore.political_alignment}
                  size="sm"
                  showLabel={false}
                />
              </div>
            )}

            {/* Framing labels */}
            {biasScore?.framing_labels && biasScore.framing_labels.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">
                {biasScore.framing_labels.map((label) => (
                  <span
                    key={label}
                    className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                  >
                    {label}
                  </span>
                ))}
              </div>
            )}

            {/* Scores row */}
            {biasScore && (
              <div className="mt-3 flex gap-4 border-t border-slate-100 pt-3 text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
                {biasScore.factuality_score != null && (
                  <span>
                    {t("bias.factuality")}: {Math.round(biasScore.factuality_score * 100)}%
                  </span>
                )}
                {biasScore.emotional_language_score != null && (
                  <span>
                    {t("bias.emotional_language")}: {Math.round(biasScore.emotional_language_score * 100)}%
                  </span>
                )}
              </div>
            )}

            {/* Date */}
            {article.published_at && (
              <p className="mt-auto pt-3 text-[11px] text-slate-400 dark:text-slate-500">
                {formatRelativeTime(article.published_at, locale)}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
