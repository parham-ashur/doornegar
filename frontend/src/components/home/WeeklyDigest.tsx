"use client";

import { useEffect, useState } from "react";
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

  // Per Parham 2026-04-24: outer title ("خلاصه هفتگی دورنگر") removed.
  // Two-column grid of the existing cards stays intact; the cards
  // themselves carry their own headers. Outer wrapper is now just a
  // plain container so the grid sits flush within the homepage flow.
  if (loading) {
    return (
      <div dir="rtl" className="animate-pulse grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border border-slate-200 dark:border-slate-700 p-4 h-32" />
        <div className="border border-slate-200 dark:border-slate-700 p-4 h-32" />
      </div>
    );
  }

  if (noData || (trends.length === 0 && outlook.length === 0)) {
    return (
      <div dir="rtl" className="border border-slate-200 dark:border-slate-700 px-4 py-6">
        <p className="text-[14px] text-slate-400 dark:text-slate-500">خلاصه هفتگی پس از اولین اجرا در دسترس خواهد بود</p>
      </div>
    );
  }

  return (
    <div dir="rtl">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Trends */}
        {trends.length > 0 && (
          <div className="border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-1.5 mb-3 pb-2 border-b border-slate-200 dark:border-slate-700">
              <TrendingUp className="h-3.5 w-3.5 text-blue-500" />
              <h4 className="text-[14px] font-black text-slate-900 dark:text-white">روندهای کلیدی هفتهٔ گذشته</h4>
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

        {/* Per-Parham 2026-04-17: sources (per-topic inline links + the flat
            footer) are removed for now. Keep descriptions only. We'll bring
            sources back when the source-attribution feature is designed
            properly. Parser and storyIds state stay in place so re-enabling
            is a one-line change. */}
      </div>
    </div>
  );
}

function TopicItem({
  item,
  storyRefs: _storyRefs,
  accent: _accent,
}: {
  item: DigestItem;
  storyRefs: StoryRef[];
  accent: "blue" | "emerald";
}) {
  // Links intentionally suppressed for now — see the comment where the flat
  // footer used to be. When sources come back, restore the related-stories
  // rendering by resolving item.storyIds against storyRefs.
  return (
    <div>
      <p className="text-[14px] leading-5 text-slate-700 dark:text-slate-300">
        <span className="font-bold">{item.title}</span>
        {item.description && (
          <span className="text-slate-500 dark:text-slate-400"> — {item.description}</span>
        )}
      </p>
    </div>
  );
}
