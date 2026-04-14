"use client";

import { useEffect, useState, useCallback } from "react";
import { ChevronDown } from "lucide-react";
import TelegramAnalyzingAnimation from "@/components/common/TelegramAnalyzingAnimation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TelegramAnalysis {
  discourse_summary: string;
  predictions: string[];
  worldviews: {
    pro_regime?: string;
    opposition?: string;
    neutral?: string;
  };
  key_claims: string[];
  number_battle?: string;
  coordinated_messaging?: string;
  consensus: string;
  missing_voices: string;
  reliability_note?: string;
}

interface ChannelStat {
  name: string;
  type: string;
  posts: number;
}

function CollapsibleSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-slate-100 dark:border-slate-800">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full py-2 text-[13px] font-bold text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
      >
        <span>{title}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pb-2">{children}</div>}
    </div>
  );
}

export default function StoryTelegramSection({ storyId, initialTab, highlightText }: { storyId: string; initialTab?: string | null; highlightText?: string | null }) {
  const [analysis, setAnalysis] = useState<TelegramAnalysis | null>(null);
  const [postCount, setPostCount] = useState<number>(0);
  const [channels, setChannels] = useState<ChannelStat[]>([]);
  const [dataReady, setDataReady] = useState(false);
  const skipAnimation = !!(initialTab || highlightText);
  const [animDone, setAnimDone] = useState(skipAnimation);
  const [noData, setNoData] = useState(false);
  const [activeTab, setActiveTab] = useState<"predictions" | "claims">(
    initialTab === "claims" ? "claims" : "predictions"
  );

  useEffect(() => {
    let cancelled = false;

    fetch(`${API}/api/v1/social/stories/${storyId}/telegram-analysis`)
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
      .then(res => {
        if (cancelled) return;
        setPostCount(res?.total_posts || 0);
        setChannels(res?.channels || []);
        if (res?.status === "ok" && res.analysis) {
          setAnalysis(res.analysis);
        } else {
          setNoData(true);
        }
        setDataReady(true);
      });

    return () => { cancelled = true; };
  }, [storyId]);

  const handleAnimComplete = useCallback(() => setAnimDone(true), []);

  if (!dataReady || !animDone) {
    if (skipAnimation) {
      return <p className="text-[13px] text-slate-400 animate-pulse">بارگذاری...</p>;
    }
    return <TelegramAnalyzingAnimation durationMs={2000} onComplete={handleAnimComplete} />;
  }

  if (noData || !analysis) {
    return (
      <p className="text-[13px] text-slate-400">
        {postCount > 0
          ? `${postCount} پست — تحلیل عمیق در اجرای بعدی`
          : "هنوز پستی از تلگرام دریافت نشده"}
      </p>
    );
  }

  const clean = (t: string) => t
    .replace(/^[\s۰-۹0-9]+[).\-–]\s*/, "")
    .replace(/^[•·]\s*/, "")
    .replace(/^با توجه به [^،]+،\s*/, "")
    .replace(/^کانال\s*[«»]?[^«»]*[«»]?\s*ادعا کرد (که\s*)?/i, "")
    .replace(/^[^،]+ ادعا کرد (که\s*)?/i, "");

  const getCredLabel = (t: string): { label: string; color: string } | null => {
    if (/مشکوک|اغراق|بعید|غیرواقعی/.test(t)) return { label: "مشکوک", color: "text-red-500" };
    if (/تبلیغاتی|جنبه تبلیغی|پروپاگاند/.test(t)) return { label: "تبلیغاتی", color: "text-red-400" };
    if (/نیازمند.*تایید|نیازمند.*تأیید|نیاز به تایید|نیاز به تأیید|تأیید نشده|تایید نشده|قابل.تأیید نیست|نیازمند.*مستقل|صحت.*نیاز/.test(t)) return { label: "تأیید نشده", color: "text-amber-500" };
    if (/قابل.اعتبار|تایید شده|تأیید شده|قابل.اعتماد|معتبر/.test(t)) return { label: "تأیید شده", color: "text-emerald-500" };
    return null;
  };

  const predictions = analysis.predictions || [];
  const claims = analysis.key_claims || [];

  return (
    <div className="space-y-3 animate-[fadeIn_0.2s_ease-in]">
      {/* Summary */}
      <p className="text-[14px] leading-6 text-slate-600 dark:text-slate-400">
        {analysis.discourse_summary}
      </p>

      {/* Tabs: Predictions | Claims */}
      {(predictions.length > 0 || claims.length > 0) && (
        <div>
          <div className="flex gap-0 border-b border-slate-200 dark:border-slate-700 mb-2">
            <button
              onClick={() => setActiveTab("predictions")}
              className={`text-[13px] font-bold px-3 py-1.5 border-b-2 transition-colors ${
                activeTab === "predictions"
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              پیش‌بینی‌ها ({predictions.length})
            </button>
            <button
              onClick={() => setActiveTab("claims")}
              className={`text-[13px] font-bold px-3 py-1.5 border-b-2 transition-colors ${
                activeTab === "claims"
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              ادعاهای کلیدی ({claims.length})
            </button>
          </div>

          <div className="space-y-1.5">
            {activeTab === "predictions" && predictions.slice(0, 3).map((p, i) => {
              const text = typeof p === "string" ? p : (p as any).text || "";
              const pct = typeof p === "object" && !(typeof p === "string") ? (p as any).pct : undefined;
              const isHighlighted = highlightText && clean(text).includes(highlightText);
              return (
                <div key={i} className={isHighlighted ? "bg-blue-50 dark:bg-blue-900/20 -mx-2 px-2 py-1 border-r-2 border-blue-500" : ""}>
                  <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400">• {clean(text)}</p>
                  {pct != null && pct > 0 && (
                    <span className="text-[13px] text-blue-500 dark:text-blue-400 font-medium mr-3">{pct}٪ از تحلیلگران</span>
                  )}
                </div>
              );
            })}
            {activeTab === "claims" && claims.slice(0, 3).map((c, i) => {
              const isHighlighted = highlightText && clean(c).includes(highlightText);
              const cred = getCredLabel(c);
              return (
                <div key={i} className={isHighlighted ? "bg-amber-50 dark:bg-amber-900/20 -mx-2 px-2 py-1 border-r-2 border-amber-500" : ""}>
                  <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400">• {clean(c)}</p>
                  {cred && (
                    <p className={`text-[13px] ${cred.color} mr-3`}>{cred.label}</p>
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
          <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-400">{analysis.consensus}</p>
        </CollapsibleSection>
      )}

      {analysis.missing_voices && (
        <CollapsibleSection title="صداهای غایب">
          <p className="text-[13px] leading-5 text-amber-600 dark:text-amber-400">{analysis.missing_voices}</p>
        </CollapsibleSection>
      )}

      {/* Channel stats — compact one line */}
      {channels.length > 0 && (
        <div className="pt-1 border-t border-slate-100 dark:border-slate-800">
          <p className="text-[13px] text-slate-400">
            {postCount} پست از {channels.length} کانال — {channels.map(ch => `${ch.name} (${ch.posts})`).join("، ")}
          </p>
        </div>
      )}
    </div>
  );
}
