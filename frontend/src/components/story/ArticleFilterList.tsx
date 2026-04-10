"use client";

import { useState, useEffect, useRef } from "react";
import { ExternalLink } from "lucide-react";
import ArticleRelevanceButton from "@/components/feedback/ArticleRelevanceButton";
import type { StoryArticleWithBias } from "@/lib/types";

interface ArticleFilterListProps {
  articles: StoryArticleWithBias[];
  storyId?: string;
  sidebarSync?: boolean;
}

type FilterKey = "all" | "state" | "independent" | "diaspora";

const filters: { key: FilterKey; label: string }[] = [
  { key: "all", label: "همه" },
  { key: "state", label: "حکومتی" },
  { key: "independent", label: "مستقل" },
  { key: "diaspora", label: "برون‌مرزی" },
];

function getAlignmentBadge(alignment: string | null) {
  const map: Record<string, { label: string; color: string }> = {
    state: { label: "حکومتی", color: "text-red-600 dark:text-red-400" },
    semi_state: { label: "نیمه‌دولتی", color: "text-orange-600 dark:text-orange-400" },
    independent: { label: "مستقل", color: "text-emerald-600 dark:text-emerald-400" },
    diaspora: { label: "برون‌مرزی", color: "text-blue-600 dark:text-blue-400" },
  };
  if (!alignment || !map[alignment]) return null;
  return map[alignment];
}

export default function ArticleFilterList({ articles, storyId, sidebarSync }: ArticleFilterListProps) {
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [sidebarHeight, setSidebarHeight] = useState<number | null>(null);

  useEffect(() => {
    if (!sidebarSync) return;
    const sidebar = document.getElementById("story-sidebar");
    if (!sidebar) return;

    const update = () => setSidebarHeight(sidebar.offsetHeight);
    update();

    const ro = new ResizeObserver(update);
    ro.observe(sidebar);
    return () => ro.disconnect();
  }, [sidebarSync]);

  const filtered = activeFilter === "all"
    ? articles
    : articles.filter((a) => {
        const alignment = a.source_state_alignment;
        if (activeFilter === "state") return alignment === "state" || alignment === "semi_state";
        if (activeFilter === "independent") return alignment === "independent";
        if (activeFilter === "diaspora") return alignment === "diaspora";
        return true;
      });

  return (
    <div dir="rtl">
      {/* Filter buttons */}
      <div className="flex flex-wrap gap-2 mb-6">
        {filters.map((f) => {
          const count = f.key === "all" ? articles.length : articles.filter((a) => {
            const al = a.source_state_alignment;
            if (f.key === "state") return al === "state" || al === "semi_state";
            if (f.key === "independent") return al === "independent";
            if (f.key === "diaspora") return al === "diaspora";
            return false;
          }).length;

          return (
            <button
              key={f.key}
              onClick={() => setActiveFilter(f.key)}
              className={`px-4 py-1.5 text-sm font-medium border transition-colors ${
                activeFilter === f.key
                  ? "bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900 dark:border-white"
                  : "bg-transparent text-slate-500 border-slate-300 dark:border-slate-700 hover:border-slate-500 dark:hover:border-slate-500"
              }`}
            >
              {f.label}
              <span className="mr-1 text-xs opacity-60">({count})</span>
            </button>
          );
        })}
      </div>

      {/* Article list */}
      {filtered.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">مقاله‌ای یافت نشد</p>
      ) : (
        <div
          className={
            filtered.length > 6
              ? "overflow-y-auto scrollbar-thin pr-1"
              : ""
          }
          style={
            filtered.length > 6 && sidebarHeight
              ? { maxHeight: `${sidebarHeight}px` }
              : filtered.length > 6
              ? { maxHeight: "600px" }
              : undefined
          }
        >
          <div className="divide-y divide-slate-200 dark:divide-slate-800">
            {filtered.map((article) => {
              const title = article.title_fa || article.title_original;
              const sourceName = article.source_name_fa || article.source_name_en;
              const badge = getAlignmentBadge(article.source_state_alignment);

              return (
                <div key={article.id} className="py-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-slate-500">{sourceName}</span>
                      {badge && (
                        <span className={`text-[10px] font-bold ${badge.color}`}>
                          {badge.label}
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-bold leading-snug text-slate-900 dark:text-white line-clamp-2">
                      {title}
                    </h3>
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline mt-1"
                    >
                      مشاهده مقاله اصلی
                      <ExternalLink className="h-3 w-3" />
                    </a>
                    {storyId && (
                      <ArticleRelevanceButton storyId={storyId} articleId={article.id} />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {filtered.length > 6 && (
            <div className="sticky bottom-0 h-8 bg-gradient-to-t from-white dark:from-[#0a0e1a] to-transparent pointer-events-none" />
          )}
        </div>
      )}
    </div>
  );
}
