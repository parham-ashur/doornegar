"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { TrendingUp, Compass } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DigestItem {
  title: string;
  description: string;
  storyIds: string[];
}

interface StoryRef {
  id: string;
  title: string;
}

function extractStoryRefs(content: string): StoryRef[] {
  // Parse top_stories from YAML frontmatter
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (!fmMatch) return [];
  const fm = fmMatch[1];
  const refs: StoryRef[] = [];
  const idRegex = /- id: "([^"]+)"\n\s+title: "([^"]+)"/g;
  let m;
  while ((m = idRegex.exec(fm)) !== null) {
    refs.push({ id: m[1], title: m[2] });
  }
  return refs;
}

function extractSection(content: string, sectionName: string): DigestItem[] {
  // Match section by name (e.g. "روندهای کلیدی")
  const regex = new RegExp(`## \\S+\\s+${sectionName}([\\s\\S]*?)(?=\\n## |\\n---|$)`);
  const match = content.match(regex);
  if (!match) return [];
  return match[1]
    .split("\n")
    .filter(line => line.trimStart().startsWith("- **"))
    .map(rawLine => {
      // Pull out `{story_ids: id1|id2}` tag Niloofar appends per item, then
      // strip it from the visible text.
      let storyIds: string[] = [];
      const idTag = rawLine.match(/\{story_ids:\s*([^}]*)\}/);
      if (idTag) {
        storyIds = idTag[1]
          .split("|")
          .map(s => s.trim())
          .filter(s => /^[0-9a-f-]{20,}$/i.test(s));
      }
      const line = rawLine.replace(/\{story_ids:[^}]*\}/, "").trim();
      const cleaned = line.replace(/^[\s-]+\*\*/, "").replace(/\*\*\s*$/, "");
      const colonIdx = cleaned.indexOf(":**");
      if (colonIdx === -1) {
        const simpleColon = cleaned.indexOf(":");
        if (simpleColon > 0) {
          return {
            title: cleaned.slice(0, simpleColon).replace(/\*\*/g, "").trim(),
            description: cleaned.slice(simpleColon + 1).replace(/\*\*/g, "").trim(),
            storyIds,
          };
        }
        return { title: cleaned.replace(/\*\*/g, "").trim(), description: "", storyIds };
      }
      return {
        title: cleaned.slice(0, colonIdx).replace(/\*\*/g, "").trim(),
        description: cleaned.slice(colonIdx + 3).replace(/\*\*/g, "").trim(),
        storyIds,
      };
    });
}

export default function WeeklyDigest({ prefetchedContent }: { prefetchedContent?: string | null }) {
  const initTrends = prefetchedContent ? extractSection(prefetchedContent, "روندهای کلیدی") : [];
  const initOutlook = prefetchedContent ? extractSection(prefetchedContent, "چشم‌انداز هفته آینده") : [];
  const initRefs = prefetchedContent ? extractStoryRefs(prefetchedContent) : [];

  const [trends, setTrends] = useState<DigestItem[]>(initTrends);
  const [outlook, setOutlook] = useState<DigestItem[]>(initOutlook);
  const [storyRefs, setStoryRefs] = useState<StoryRef[]>(initRefs);
  const [loading, setLoading] = useState(!prefetchedContent);
  const [noData, setNoData] = useState(prefetchedContent === null && !prefetchedContent);

  useEffect(() => {
    if (prefetchedContent !== undefined) return;
    async function fetchDigest() {
      try {
        const res = await fetch(`${API}/api/v1/stories/weekly-digest`);
        if (!res.ok) { setNoData(true); return; }
        const data = await res.json();
        if (!data.content || data.status === "no_data") { setNoData(true); return; }
        setTrends(extractSection(data.content, "روندهای کلیدی"));
        setOutlook(extractSection(data.content, "چشم‌انداز هفته آینده"));
        setStoryRefs(extractStoryRefs(data.content));
      } catch {
        setNoData(true);
      } finally {
        setLoading(false);
      }
    }
    fetchDigest();
  }, [prefetchedContent]);

  if (loading) {
    return (
      <div dir="rtl" className="border border-slate-300 dark:border-slate-600">
        <div className="flex items-center -mt-3 mx-4">
          <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
          <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">خلاصه هفتگی دورنگر</span>
          <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
        </div>
        <div className="px-4 pb-4 pt-3 animate-pulse">
          <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-3/4 mb-2" />
          <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-1/2" />
        </div>
      </div>
    );
  }

  if (noData || (trends.length === 0 && outlook.length === 0)) {
    return (
      <div dir="rtl" className="border border-slate-300 dark:border-slate-600">
        <div className="flex items-center -mt-3 mx-4">
          <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
          <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">خلاصه هفتگی دورنگر</span>
          <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
        </div>
        <div className="px-4 pb-4 pt-3">
          <p className="text-[14px] text-slate-400 dark:text-slate-500">خلاصه هفتگی پس از اولین اجرا در دسترس خواهد بود</p>
        </div>
      </div>
    );
  }

  return (
    <div dir="rtl" className="border border-slate-300 dark:border-slate-600">
      <div className="flex items-center -mt-3 mx-4">
        <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
        <span className="text-[13px] font-black text-slate-900 dark:text-white px-3 bg-white dark:bg-[#0a0e1a]">خلاصه هفتگی دورنگر</span>
        <div className="flex-1 h-px bg-white dark:bg-[#0a0e1a]" />
      </div>

      <div className="px-5 pb-5 pt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Trends */}
        {trends.length > 0 && (
          <div className="border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-1.5 mb-3 pb-2 border-b border-slate-200 dark:border-slate-700">
              <TrendingUp className="h-3.5 w-3.5 text-blue-500" />
              <h4 className="text-[14px] font-black text-slate-900 dark:text-white">روندهای کلیدی</h4>
            </div>
            <div className="space-y-3">
              {trends.map((item, i) => (
                <TopicItem key={i} item={item} storyRefs={storyRefs} accent="blue" />
              ))}
            </div>
          </div>
        )}

        {/* Outlook */}
        {outlook.length > 0 && (
          <div className="border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-1.5 mb-3 pb-2 border-b border-slate-200 dark:border-slate-700">
              <Compass className="h-3.5 w-3.5 text-emerald-500" />
              <h4 className="text-[14px] font-black text-slate-900 dark:text-white">چشم‌انداز هفته آینده</h4>
            </div>
            <div className="space-y-3">
              {outlook.map((item, i) => (
                <TopicItem key={i} item={item} storyRefs={storyRefs} accent="emerald" />
              ))}
            </div>
          </div>
        )}

        {/* Fallback footer: only shown when no item has per-topic links (old
            digests that predate the {story_ids: ...} format). Once Niloofar
            regenerates, every trend/outlook carries its own links inline. */}
        {storyRefs.length > 0 && ![...trends, ...outlook].some(t => t.storyIds.length > 0) && (
          <div className="md:col-span-2 pt-2 border-t border-slate-200 dark:border-slate-700">
            <p className="text-[12px] text-slate-400 dark:text-slate-500 mb-1.5">موضوعات این هفته:</p>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {storyRefs.slice(0, 8).map((ref) => (
                <Link
                  key={ref.id}
                  href={`/fa/stories/${ref.id}`}
                  className="text-[12px] text-slate-400 dark:text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  {ref.title.slice(0, 40)}{ref.title.length > 40 ? "…" : ""}
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TopicItem({
  item,
  storyRefs,
  accent,
}: {
  item: DigestItem;
  storyRefs: StoryRef[];
  accent: "blue" | "emerald";
}) {
  const linkHover =
    accent === "blue"
      ? "hover:text-blue-600 dark:hover:text-blue-400"
      : "hover:text-emerald-600 dark:hover:text-emerald-400";
  // Resolve IDs to {id, title}. Unknown IDs drop silently.
  const related = item.storyIds
    .map(id => storyRefs.find(r => r.id === id))
    .filter((r): r is StoryRef => Boolean(r));

  return (
    <div>
      <p className="text-[14px] leading-5 text-slate-700 dark:text-slate-300">
        <span className="font-bold">{item.title}</span>
        {item.description && (
          <span className="text-slate-500 dark:text-slate-400"> — {item.description}</span>
        )}
      </p>
      {related.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1">
          {related.map(ref => (
            <Link
              key={ref.id}
              href={`/fa/stories/${ref.id}`}
              className={`text-[12px] text-slate-400 dark:text-slate-500 transition-colors ${linkHover}`}
            >
              ← {ref.title.slice(0, 32)}{ref.title.length > 32 ? "…" : ""}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
