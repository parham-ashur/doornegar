"use client";

import { useEffect, useState } from "react";
import { TrendingUp, Compass } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DigestItem {
  title: string;
  description: string;
}

function extractSection(content: string, sectionName: string): DigestItem[] {
  // Match section by name (e.g. "روندهای کلیدی")
  const regex = new RegExp(`## \\S+\\s+${sectionName}([\\s\\S]*?)(?=\\n## |\\n---|$)`);
  const match = content.match(regex);
  if (!match) return [];
  return match[1]
    .split("\n")
    .filter(line => line.trimStart().startsWith("- **"))
    .map(line => {
      const cleaned = line.replace(/^[\s-]+\*\*/, "").replace(/\*\*\s*$/, "");
      const colonIdx = cleaned.indexOf(":**");
      if (colonIdx === -1) {
        const simpleColon = cleaned.indexOf(":");
        if (simpleColon > 0) {
          return { title: cleaned.slice(0, simpleColon).replace(/\*\*/g, "").trim(), description: cleaned.slice(simpleColon + 1).replace(/\*\*/g, "").trim() };
        }
        return { title: cleaned.replace(/\*\*/g, "").trim(), description: "" };
      }
      return {
        title: cleaned.slice(0, colonIdx).replace(/\*\*/g, "").trim(),
        description: cleaned.slice(colonIdx + 3).replace(/\*\*/g, "").trim(),
      };
    });
}

export default function WeeklyDigest() {
  const [trends, setTrends] = useState<DigestItem[]>([]);
  const [outlook, setOutlook] = useState<DigestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    async function fetchDigest() {
      try {
        const res = await fetch(`${API}/api/v1/stories/weekly-digest`);
        if (!res.ok) { setNoData(true); return; }
        const data = await res.json();
        if (!data.content || data.status === "no_data") { setNoData(true); return; }
        setTrends(extractSection(data.content, "روندهای کلیدی"));
        setOutlook(extractSection(data.content, "چشم‌انداز هفته آینده"));
      } catch {
        setNoData(true);
      } finally {
        setLoading(false);
      }
    }
    fetchDigest();
  }, []);

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
            <div className="space-y-2.5">
              {trends.map((item, i) => (
                <div key={i}>
                  <p className="text-[14px] leading-5 text-slate-700 dark:text-slate-300">
                    <span className="font-bold">{item.title}</span>
                    {item.description && <span className="text-slate-500 dark:text-slate-400"> — {item.description}</span>}
                  </p>
                </div>
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
            <div className="space-y-2.5">
              {outlook.map((item, i) => (
                <div key={i}>
                  <p className="text-[14px] leading-5 text-slate-700 dark:text-slate-300">
                    <span className="font-bold">{item.title}</span>
                    {item.description && <span className="text-slate-500 dark:text-slate-400"> — {item.description}</span>}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
