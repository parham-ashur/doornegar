"use client";

import { useMemo } from "react";
import { toFa } from "@/lib/utils";

interface TimelineArticle {
  id: string;
  title_fa?: string | null;
  title_original?: string | null;
  source_name_fa?: string | null;
  source_slug?: string | null;
  source_state_alignment?: string | null;
  published_at?: string | null;
  url?: string;
}

interface Props {
  articles: TimelineArticle[];
}

type Side = "conservative" | "opposition";

function getSide(alignment: string | null | undefined): Side {
  if (alignment === "state" || alignment === "semi_state") return "conservative";
  return "opposition";
}

export default function StoryTimeline({ articles }: Props) {
  const dayGroups = useMemo(() => {
    const withDate = articles
      .filter((a) => a.published_at)
      .sort((a, b) => new Date(a.published_at!).getTime() - new Date(b.published_at!).getTime());

    const groups: { day: string; label: string; conservative: TimelineArticle[]; opposition: TimelineArticle[] }[] = [];
    const seen = new Map<string, number>();

    for (const article of withDate) {
      const dayKey = new Date(article.published_at!).toISOString().slice(0, 10);
      const side = getSide(article.source_state_alignment);

      if (seen.has(dayKey)) {
        groups[seen.get(dayKey)!][side].push(article);
      } else {
        seen.set(dayKey, groups.length);
        const group = { day: dayKey, label: new Date(article.published_at!).toLocaleDateString("fa-IR", { month: "short", day: "numeric" }), conservative: [] as TimelineArticle[], opposition: [] as TimelineArticle[] };
        group[side].push(article);
        groups.push(group);
      }
    }
    return groups;
  }, [articles]);

  if (dayGroups.length < 2) return null;

  const renderSide = (articles: TimelineArticle[], color: string) => {
    if (articles.length === 0) return <p className="text-[13px] text-slate-300 dark:text-slate-600">—</p>;

    // Group by source
    const bySource = new Map<string, TimelineArticle[]>();
    for (const a of articles) {
      const key = a.source_slug || a.source_name_fa || "unknown";
      if (!bySource.has(key)) bySource.set(key, []);
      bySource.get(key)!.push(a);
    }

    return Array.from(bySource.entries()).map(([slug, arts]) => {
      const name = arts[0].source_name_fa || slug;
      const cleanTitle = (t: string | null | undefined) =>
        (t || "").replace(/\*+/g, "").replace(/[#•·◌]/g, "").trim();

      return (
        <p key={slug} className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">
          <span className="font-bold" style={{ color }}>{name}</span>
          <span className="text-slate-300 dark:text-slate-600"> — </span>
          {arts.map((a, i) => (
            <span key={a.id}>
              <a href={a.url || "#"} target={a.url ? "_blank" : undefined} rel="noopener noreferrer"
                className="hover:opacity-70">{cleanTitle(a.title_fa || a.title_original)}</a>
              {i < arts.length - 1 && <span className="text-slate-300 dark:text-slate-600"> ‹ </span>}
            </span>
          ))}
        </p>
      );
    });
  };

  return (
    <div className="my-6" dir="rtl">
      <h3 className="mb-4 text-[13px] font-black text-slate-900 dark:text-white">
        روند پوشش خبری
      </h3>

      {/* Column headers */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-[3px] h-3 bg-[#1e3a5f]" />
          <span className="text-[13px] font-bold text-[#1e3a5f] dark:text-blue-300">درون‌مرزی</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-[3px] h-3 bg-[#ea580c]" />
          <span className="text-[13px] font-bold text-[#ea580c] dark:text-orange-400">برون‌مرزی</span>
        </div>
      </div>

      {/* Days */}
      <div className="space-y-3">
        {dayGroups.map((group) => (
          <div key={group.day}>
            {/* Day header */}
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[13px] font-bold text-slate-500 dark:text-slate-400">{group.label}</span>
              <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />
              <span className="text-[13px] text-slate-400">{toFa(group.conservative.length + group.opposition.length)}</span>
            </div>

            {/* Two columns */}
            <div className="grid grid-cols-2 gap-3">
              <div className="border-r-[3px] border-[#1e3a5f] pr-2 space-y-0.5">
                {renderSide(group.conservative, "#1e3a5f")}
              </div>
              <div className="border-r-[3px] border-[#ea580c] pr-2 space-y-0.5">
                {renderSide(group.opposition, "#ea580c")}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
