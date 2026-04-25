import { useLocale, useTranslations } from "next-intl";
import { ExternalLink, Shield } from "lucide-react";
import BiasSpectrum from "@/components/common/BiasSpectrum";
import type { StoryArticleWithBias } from "@/lib/types";

interface TopicSpectrumViewProps {
  articles: StoryArticleWithBias[];
}

type SpectrumCategory = "right" | "center" | "left";

function categorizeArticle(article: StoryArticleWithBias): SpectrumCategory {
  const alignment = article.source_state_alignment;
  if (alignment === "state" || alignment === "semi_state") return "right"; // pro-regime = right side in Iranian context
  if (alignment === "independent") return "center";
  return "left"; // diaspora/opposition = left in Iranian spectrum
}

function getCategoryLabel(cat: SpectrumCategory, locale: string) {
  const labels = {
    right: { en: "Pro-Establishment", fa: "درون‌مرزی" },
    center: { en: "Center / Independent", fa: "میانه / مستقل" },
    left: { en: "Opposition / Diaspora", fa: "برون‌مرزی / برون‌مرزی" },
  };
  return labels[cat][locale === "fa" ? "fa" : "en"];
}

function getCategoryColor(cat: SpectrumCategory) {
  return {
    right: "border-red-500 bg-red-50 dark:bg-red-950/20",
    center: "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/20",
    left: "border-blue-500 bg-blue-50 dark:bg-blue-950/20",
  }[cat];
}

function getCategoryHeaderColor(cat: SpectrumCategory) {
  return {
    right: "text-red-700 dark:text-red-400",
    center: "text-emerald-700 dark:text-emerald-400",
    left: "text-blue-700 dark:text-blue-400",
  }[cat];
}

export default function TopicSpectrumView({ articles }: TopicSpectrumViewProps) {
  const locale = useLocale();
  const t = useTranslations();

  // Group articles by spectrum position
  const groups: Record<SpectrumCategory, StoryArticleWithBias[]> = {
    right: [],
    center: [],
    left: [],
  };

  articles.forEach((article) => {
    const cat = categorizeArticle(article);
    groups[cat].push(article);
  });

  const categories: SpectrumCategory[] = ["left", "center", "right"];

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {categories.map((cat) => (
        <div
          key={cat}
          className={`rounded-xl border-t-4 p-4 ${getCategoryColor(cat)}`}
        >
          {/* Category header */}
          <h3 className={`mb-3 text-sm font-bold ${getCategoryHeaderColor(cat)}`}>
            {getCategoryLabel(cat, locale)}
            {groups[cat].length > 0 && (
              <span className="ms-2 text-xs font-normal text-slate-500">
                ({groups[cat].length} {locale === "fa" ? "مقاله" : "articles"})
              </span>
            )}
          </h3>

          {groups[cat].length === 0 ? (
            <p className="text-xs text-slate-400 italic">
              {locale === "fa" ? "پوشش داده نشده" : "No coverage"}
            </p>
          ) : (
            <div className="space-y-3">
              {groups[cat].map((article) => {
                const title =
                  locale === "fa"
                    ? article.title_fa || article.title_original
                    : article.title_en || article.title_original;
                const sourceName =
                  locale === "fa"
                    ? article.source_name_fa
                    : article.source_name_en;
                const biasScore = article.bias_scores?.[0];

                return (
                  <div key={article.id} className="border-b border-slate-200/50 pb-3 last:border-0 dark:border-slate-700/50">
                    {/* Source name */}
                    <div className="mb-1 flex items-center gap-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                      {sourceName}
                      {article.source_state_alignment === "state" && (
                        <Shield className="h-3 w-3 text-red-500" />
                      )}
                    </div>

                    {/* Title */}
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium leading-snug text-slate-800 hover:text-diaspora dark:text-slate-200"
                    >
                      {title}
                      <ExternalLink className="ms-1 inline h-3 w-3 text-slate-400" />
                    </a>

                    {/* Summary excerpt */}
                    {article.summary && (
                      <p className="mt-1 line-clamp-2 text-[11px] text-slate-500 dark:text-slate-400">
                        {article.summary.slice(0, 150)}...
                      </p>
                    )}

                    {/* Bias score mini bar */}
                    {biasScore?.political_alignment != null && (
                      <div className="mt-2">
                        <BiasSpectrum value={biasScore.political_alignment} size="sm" showLabel={false} />
                      </div>
                    )}

                    {/* Framing labels */}
                    {biasScore?.framing_labels && biasScore.framing_labels.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {biasScore.framing_labels.slice(0, 3).map((label) => (
                          <span
                            key={label}
                            className="rounded bg-slate-200/70 px-1.5 py-0.5 text-[9px] text-slate-600 dark:bg-slate-700/50 dark:text-slate-400"
                          >
                            {label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
