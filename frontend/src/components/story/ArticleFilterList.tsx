"use client";

import { useState, useEffect, useRef } from "react";
import { ExternalLink, Clock } from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";
import ArticleRelevanceButton from "@/components/feedback/ArticleRelevanceButton";
import type { StoryArticleWithBias } from "@/lib/types";

interface ArticleFilterListProps {
  articles: StoryArticleWithBias[];
  storyId?: string;
  sidebarSync?: boolean;
}

type FilterKey = "all" | "state" | "diaspora";

const filters: { key: FilterKey; label: string }[] = [
  { key: "all", label: "همه" },
  { key: "state", label: "محافظه‌کار" },
  { key: "diaspora", label: "اپوزیسیون" },
];

function getAlignmentBadge(alignment: string | null) {
  const map: Record<string, { label: string; color: string }> = {
    state: { label: "محافظه‌کار", color: "text-[#1e3a5f] dark:text-blue-300" },
    semi_state: { label: "محافظه‌کار", color: "text-[#2563eb] dark:text-blue-300" },
    independent: { label: "محافظه‌کار", color: "text-slate-500 dark:text-slate-400" },
    diaspora: { label: "اپوزیسیون", color: "text-[#ea580c] dark:text-orange-400" },
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
        if (activeFilter === "state") return alignment === "state" || alignment === "semi_state" || alignment === "independent";
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
            filtered.length > 5
              ? "overflow-y-auto scrollbar-thin pr-1"
              : ""
          }
          style={
            filtered.length > 5
              ? { maxHeight: "700px" }
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
                    <div className="flex items-center gap-3 mt-1.5">
                      {article.published_at && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-slate-400">
                          <Clock className="h-3 w-3" />
                          نشر {formatRelativeTime(article.published_at, "fa")}
                        </span>
                      )}
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        مشاهده مقاله اصلی
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                    {storyId && (
                      <ArticleRelevanceButton storyId={storyId} articleId={article.id} />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {filtered.length > 5 && (
            <div className="sticky bottom-0 h-8 bg-gradient-to-t from-white dark:from-[#0a0e1a] to-transparent pointer-events-none" />
          )}
        </div>
      )}
    </div>
  );
}
