"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import TelegramAnalyzingAnimation from "@/components/common/TelegramAnalyzingAnimation";
import {
  cleanClaim,
  cleanPrediction,
  displayClaims,
  displayPredictions,
  getCredLabel,
} from "@/lib/telegram-text";
import { formatRelativeTime } from "@/lib/utils";
import type { TelegramAnalysis } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const POST_PREVIEW_CHARS = 280;
const MAX_POSTS_RENDERED = 8;

interface ChannelStat {
  name: string;
  type: string;
  posts: number;
}

interface SocialPost {
  id: string;
  message_id: number;
  text: string | null;
  date: string;
  views: number | null;
  channel: {
    username: string;
    title: string;
    channel_type: string;
  } | null;
}

const CHANNEL_TYPE_LABEL: Record<string, string> = {
  commentary: "تحلیلگر",
  activist: "فعال",
  political_party: "حزبی",
  citizen: "شهروند",
  news: "خبری",
};

function CollapsibleSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-slate-100 dark:border-slate-800">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full py-2 text-[15px] font-bold text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
      >
        <span>{title}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pb-2">{children}</div>}
    </div>
  );
}

export default function StoryTelegramSection({ storyId, initialTab, highlightText, scrollTargetId }: { storyId: string; initialTab?: string | null; highlightText?: string | null; scrollTargetId?: string }) {
  const [analysis, setAnalysis] = useState<TelegramAnalysis | null>(null);
  const [postCount, setPostCount] = useState<number>(0);
  const [channels, setChannels] = useState<ChannelStat[]>([]);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [dataReady, setDataReady] = useState(false);
  const skipAnimation = !!(initialTab || highlightText);
  const [animDone, setAnimDone] = useState(skipAnimation);
  const [noData, setNoData] = useState(false);
  const [activeTab, setActiveTab] = useState<"predictions" | "claims">(
    initialTab === "claims" ? "claims" : "predictions"
  );
  const highlightRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (initialTab === "claims" || initialTab === "predictions") {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  useEffect(() => {
    if (!dataReady || !animDone) return;
    if (!initialTab && !highlightText) return;
    const t = setTimeout(() => {
      const el = highlightRef.current;
      if (el && el.offsetParent !== null) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      } else if (scrollTargetId) {
        const container = document.getElementById(scrollTargetId);
        if (container && container.offsetParent !== null) {
          container.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    }, 150);
    return () => clearTimeout(t);
  }, [dataReady, animDone, initialTab, highlightText, activeTab, scrollTargetId]);

  useEffect(() => {
    let cancelled = false;

    // Two parallel fetches: the cached LLM analysis (predictions /
    // claims / discourse) and the raw post list (analyst commentary
    // we can render verbatim with a deep link). Both are read-only.
    Promise.all([
      fetch(`${API}/api/v1/social/stories/${storyId}/telegram-analysis`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API}/api/v1/social/stories/${storyId}/social?limit=${MAX_POSTS_RENDERED}`).then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([analysisRes, socialRes]) => {
      if (cancelled) return;
      setPostCount(analysisRes?.total_posts || 0);
      setChannels(analysisRes?.channels || []);
      if (analysisRes?.status === "ok" && analysisRes.analysis) {
        setAnalysis(analysisRes.analysis);
      } else {
        setNoData(true);
      }
      if (Array.isArray(socialRes?.posts)) {
        setPosts(socialRes.posts.filter((p: SocialPost) => p.text && p.channel?.username));
      }
      setDataReady(true);
    });

    return () => { cancelled = true; };
  }, [storyId]);

  const handleAnimComplete = useCallback(() => setAnimDone(true), []);

  if (!dataReady || !animDone) {
    if (skipAnimation) {
      return <p className="text-[15px] text-slate-400 animate-pulse">بارگذاری...</p>;
    }
    return <TelegramAnalyzingAnimation durationMs={2000} onComplete={handleAnimComplete} />;
  }

  if (noData || !analysis) {
    return (
      <div className="border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 p-3">
        <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400">
          {postCount > 0
            ? `تا الان ${postCount} پست مرتبط در تلگرام جمع شده است، اما برای تحلیل عمیق (پیش‌بینی‌ها، ادعاهای کلیدی، اجماع و اختلاف) به تعداد بیشتری پست از کانال‌های تحلیلی نیاز داریم. به‌محض رسیدن تعداد لازم، این بخش خودکار تکمیل می‌شود.`
            : "این خبر هنوز در کانال‌های تحلیلی تلگرام بازتاب نیافته است. به‌محض انتشار تعداد مناسبی پست، پیش‌بینی‌ها و ادعاهای کلیدی در همین بخش نمایش داده می‌شوند."}
        </p>
      </div>
    );
  }

  const clean = (t: string) => cleanClaim(cleanPrediction(t))
    .replace(/^[\s۰-۹0-9]+[).\-–]\s*/, "")
    .replace(/^[•·]\s*/, "")
    .replace(/^با توجه به [^،]+،\s*/, "");

  const predictions = displayPredictions(analysis);
  const claims = displayClaims(analysis);

  return (
    <div className="space-y-3 animate-[fadeIn_0.2s_ease-in]">
      {/* Summary */}
      <p className="text-[15px] leading-6 text-slate-600 dark:text-slate-400">
        {analysis.discourse_summary}
      </p>

      {/* Tabs: Predictions | Claims */}
      {(predictions.length > 0 || claims.length > 0) && (
        <div>
          <div className="flex gap-0 border-b border-slate-200 dark:border-slate-700 mb-2">
            <button
              onClick={() => setActiveTab("predictions")}
              className={`text-[15px] font-bold px-3 py-1.5 border-b-2 transition-colors ${
                activeTab === "predictions"
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              پیش‌بینی‌ها ({predictions.length})
            </button>
            <button
              onClick={() => setActiveTab("claims")}
              className={`text-[15px] font-bold px-3 py-1.5 border-b-2 transition-colors ${
                activeTab === "claims"
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              ادعاهای کلیدی ({claims.length})
            </button>
          </div>

          <div className="space-y-1.5">
            {activeTab === "predictions" && predictions.map((p, i) => {
              const text = typeof p === "string" ? p : p.text || "";
              const isHighlighted = !!(highlightText && clean(text).includes(highlightText));
              return (
                <div key={i} ref={isHighlighted ? highlightRef : undefined} className={isHighlighted ? "bg-blue-50 dark:bg-blue-900/20 -mx-2 px-2 py-1 border-r-2 border-blue-500" : ""}>
                  <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400">• {clean(text)}</p>
                </div>
              );
            })}
            {activeTab === "claims" && claims.map((c, i) => {
              const text = typeof c === "string" ? c : c.text || "";
              const isHighlighted = !!(highlightText && clean(text).includes(highlightText));
              const cred = getCredLabel(text);
              return (
                <div key={i} ref={isHighlighted ? highlightRef : undefined} className={isHighlighted ? "bg-amber-50 dark:bg-amber-900/20 -mx-2 px-2 py-1 border-r-2 border-amber-500" : ""}>
                  <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400">• {clean(text)}</p>
                  {cred && (
                    <p className={`text-[15px] ${cred.color} mr-3`}>{cred.label}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Collapsible sections */}
      {analysis.consensus && (
        <CollapsibleSection title="اجماع و اختلاف">
          <p className="text-[15px] leading-6 text-slate-500 dark:text-slate-400">{analysis.consensus}</p>
        </CollapsibleSection>
      )}

      {analysis.missing_voices && (
        <CollapsibleSection title="صداهای غایب">
          <p className="text-[15px] leading-6 text-amber-600 dark:text-amber-400">{analysis.missing_voices}</p>
        </CollapsibleSection>
      )}

      {/* Telegram references — actual analyst commentary posts attached
          to this story. Each row has the channel label, the timestamp,
          a text preview, and a deep link back to the original post on
          Telegram. Posts from RSS-mirror channels are excluded server-
          side (they already appear in the article list). When the post
          list is empty, fall back to the channel chip summary so the
          old behaviour still renders for stories whose analysis ran
          before the schema extension. */}
      {(posts.length > 0 || channels.length > 0) && (
        <div className="pt-3 mt-2 border-t border-slate-200 dark:border-slate-800">
          <h4 className="text-[12px] font-bold text-slate-600 dark:text-slate-400 mb-2">
            منابع تلگرامی — {channels.length} کانال، {postCount} پست مستقیم
          </h4>
          {posts.length > 0 ? (
            <ul className="space-y-2.5">
              {posts.map((p) => {
                if (!p.channel || !p.text) return null;
                const href = `https://t.me/${p.channel.username}/${p.message_id}`;
                const truncated = p.text.length > POST_PREVIEW_CHARS;
                const preview = truncated
                  ? p.text.slice(0, POST_PREVIEW_CHARS).trimEnd() + "…"
                  : p.text;
                const typeLabel = CHANNEL_TYPE_LABEL[p.channel.channel_type] || null;
                return (
                  <li key={p.id} className="border-r-2 border-slate-200 dark:border-slate-700 pr-3">
                    <div className="flex items-center gap-2 mb-1 text-[12px]">
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-bold text-slate-700 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400"
                      >
                        {p.channel.title}
                      </a>
                      {typeLabel && (
                        <span className="text-slate-400 text-[12px]">{typeLabel}</span>
                      )}
                      <span className="text-slate-300 dark:text-slate-600">·</span>
                      <time className="text-slate-400 text-[12px]">
                        {formatRelativeTime(p.date, "fa")}
                      </time>
                    </div>
                    <p className="text-[15px] leading-6 text-slate-600 dark:text-slate-300 whitespace-pre-line break-words">
                      {preview}
                    </p>
                    {truncated && (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-1 text-[12px] text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        ادامه در تلگرام
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {channels.map((ch, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[12px] border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300"
                >
                  <span className="font-medium">{ch.name}</span>
                  <span className="text-slate-400 text-[12px]">·</span>
                  <span className="text-slate-500 dark:text-slate-400 text-[12px]">{ch.posts}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
