"use client";

import { useState, useEffect, useMemo } from "react";
import { Clock, Send } from "lucide-react";
import ArticleRelevanceButton from "@/components/feedback/ArticleRelevanceButton";
import type { StoryArticleWithBias } from "@/lib/types";

// Telegram detection + de-deep-linking. Articles sourced from a
// Telegram channel land here with `url = https://t.me/{channel}/{id}`.
// Tapping that URL on a phone Safari triggers the Telegram-app handoff
// even with target=_blank — there's no `rel` we can set to suppress it.
// Appending `?embed=1` (or `&embed=1`) flips Telegram's t.me page to
// the standalone embed view, which renders the post inline in the
// browser and never offers the app deep-link.
const TELEGRAM_URL_RE = /^https?:\/\/(t\.me|telegram\.me)\//i;
function isTelegramArticle(url: string | null | undefined): boolean {
  return !!url && TELEGRAM_URL_RE.test(url);
}
function articleHref(url: string): string {
  if (!isTelegramArticle(url)) return url;
  if (/[?&]embed=/.test(url)) return url;
  return url + (url.includes("?") ? "&embed=1" : "?embed=1");
}

const TEHRAN_DAY_FMT = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tehran" });
const TEHRAN_LABEL_FMT = new Intl.DateTimeFormat("fa-IR", {
  timeZone: "Asia/Tehran",
  year: "numeric",
  month: "long",
  day: "numeric",
});

interface ArticleFilterListProps {
  articles: StoryArticleWithBias[];
  storyId?: string;
  sidebarSync?: boolean;
}

type FilterKey = "all" | "state" | "diaspora";

const filters: { key: FilterKey; label: string }[] = [
  { key: "all", label: "همه" },
  { key: "state", label: "درون‌مرزی" },
  { key: "diaspora", label: "برون‌مرزی" },
];

function getAlignmentBadge(alignment: string | null) {
  // Collapse to a 2-label display on article cards: state + semi_state
  // both read as «درون‌مرزی»; diaspora reads as «برون‌مرزی»; independent
  // hides the badge. Finer distinction (semi_state vs state, or the
  // 4-subgroup narrative) lives on the sources spectrum and narrative
  // panel — it over-loaded the article list with classifier labels.
  const map: Record<string, { label: string; color: string }> = {
    state: { label: "درون‌مرزی", color: "text-[#1e3a5f] dark:text-blue-300" },
    semi_state: { label: "درون‌مرزی", color: "text-[#1e3a5f] dark:text-blue-300" },
    diaspora: { label: "برون‌مرزی", color: "text-[#ea580c] dark:text-orange-400" },
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

  type Group = {
    dayKey: string;
    dayLabel: string;
    sourceName: string;
    sourceSlug: string | null;
    alignment: string | null;
    items: StoryArticleWithBias[];
  };

  const filterCounts = useMemo(() => {
    let stateLike = 0;
    let diaspora = 0;
    for (const a of articles) {
      const al = a.source_state_alignment;
      if (al === "state" || al === "semi_state" || al === "independent") stateLike++;
      else if (al === "diaspora") diaspora++;
    }
    return { all: articles.length, state: stateLike, diaspora };
  }, [articles]);

  // Group by (Tehran-day × source) so multiple articles from the same
  // outlet on the same day collapse into one row. Saves vertical space
  // on umbrella stories where one source publishes 5+ pieces in a day.
  const groups = useMemo(() => {
    const filtered = activeFilter === "all"
      ? articles
      : articles.filter((a) => {
          const al = a.source_state_alignment;
          if (activeFilter === "state") return al === "state" || al === "semi_state" || al === "independent";
          if (activeFilter === "diaspora") return al === "diaspora";
          return true;
        });

    const groupsMap = new Map<string, Group>();
    for (const a of filtered) {
      const pub = a.published_at ? new Date(a.published_at) : null;
      const dayKey = pub ? TEHRAN_DAY_FMT.format(pub) : "unknown";
      const srcKey = a.source_slug || a.source_name_fa || a.source_name_en || "?";
      const key = `${dayKey}::${srcKey}`;
      let g = groupsMap.get(key);
      if (!g) {
        g = {
          dayKey,
          dayLabel: pub ? TEHRAN_LABEL_FMT.format(pub) : "",
          sourceName: a.source_name_fa || a.source_name_en || "",
          sourceSlug: a.source_slug,
          alignment: a.source_state_alignment,
          items: [],
        };
        groupsMap.set(key, g);
      }
      g.items.push(a);
    }
    const list = Array.from(groupsMap.values());
    list.sort((a, b) => {
      if (a.dayKey !== b.dayKey) return b.dayKey.localeCompare(a.dayKey);
      return a.sourceName.localeCompare(b.sourceName);
    });
    for (const g of list) {
      g.items.sort((x, y) => {
        const tx = x.published_at ? new Date(x.published_at).getTime() : 0;
        const ty = y.published_at ? new Date(y.published_at).getTime() : 0;
        return ty - tx;
      });
    }
    return list;
  }, [articles, activeFilter]);

  return (
    <div dir="rtl">
      {/* Filter buttons */}
      <div className="flex flex-wrap gap-2 mb-6">
        {filters.map((f) => {
          const count = filterCounts[f.key];

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

      {/* Article list — grouped by day × source */}
      {groups.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">مقاله‌ای یافت نشد</p>
      ) : (
        <div
          className={
            groups.length > 5
              ? "overflow-y-auto scrollbar-thin pr-1"
              : ""
          }
          style={
            groups.length > 5
              ? { maxHeight: "700px" }
              : undefined
          }
        >
          <div className="divide-y divide-slate-200 dark:divide-slate-800">
            {groups.map((g) => {
              const badge = getAlignmentBadge(g.alignment);
              const head = g.items[0];
              const isTelegramGroup = isTelegramArticle(head.url);
              return (
                <div key={`${g.dayKey}::${g.sourceSlug || g.sourceName}`} className="py-4">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className="text-xs font-semibold text-slate-500">{g.sourceName}</span>
                    {isTelegramGroup && (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 border border-sky-300 dark:border-sky-700 text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-950/40"
                        title="منبع: کانال تلگرام"
                      >
                        <Send className="h-3 w-3" />
                        تلگرام
                      </span>
                    )}
                    {badge && (
                      <span className={`text-[12px] font-bold ${badge.color}`}>
                        {badge.label}
                      </span>
                    )}
                    {g.dayLabel && (
                      <span className="inline-flex items-center gap-1 text-[12px] text-slate-400">
                        <Clock className="h-3 w-3" />
                        {g.dayLabel}
                        {g.items.length > 1 && (
                          <span className="mr-1 text-slate-400">· {g.items.length} مقاله</span>
                        )}
                      </span>
                    )}
                  </div>

                  {/* Primary title = most recent article in the group. */}
                  <a
                    href={articleHref(head.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block group"
                  >
                    <h3 className="text-sm font-bold leading-snug text-slate-900 dark:text-white line-clamp-2 group-hover:underline">
                      {head.title_fa || head.title_original}
                    </h3>
                  </a>

                  {storyId && (
                    <div className="mt-1">
                      <ArticleRelevanceButton storyId={storyId} articleId={head.id} />
                    </div>
                  )}

                  {/* Additional same-day titles from this source, stacked
                      compact so they read as a cluster rather than their
                      own cards. Each is its own link with its own
                      «نامرتبط» button so feedback maps to the article
                      the reader actually clicked, not the head. */}
                  {g.items.length > 1 && (
                    <ul className="mt-2 space-y-2 border-r-2 border-slate-200 dark:border-slate-800 pr-2.5">
                      {g.items.slice(1).map((a) => (
                        <li key={a.id}>
                          <a
                            href={articleHref(a.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[15px] leading-6 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:underline line-clamp-2"
                          >
                            {a.title_fa || a.title_original}
                          </a>
                          {storyId && (
                            <ArticleRelevanceButton storyId={storyId} articleId={a.id} />
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
          {groups.length > 5 && (
            <div className="sticky bottom-0 h-8 bg-gradient-to-t from-white dark:from-[#0a0e1a] to-transparent pointer-events-none" />
          )}
        </div>
      )}
    </div>
  );
}
