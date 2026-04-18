"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import TelegramAnalyzingAnimation from "@/components/common/TelegramAnalyzingAnimation";
import { toFa } from "@/lib/utils";
import { cleanPrediction, cleanClaim } from "@/lib/telegram-text";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TelegramAnalysis {
  discourse_summary: string;
  predictions?: any[];
  key_claims?: any[];
  // Niloofar-polished versions for homepage display. When present, these
  // replace `predictions` / `key_claims` in UI. Raw fields stay intact for
  // the full story page, which keeps the "موضوع: X |" grouping intact.
  predictions_display?: any[];
  key_claims_display?: any[];
}

interface AnalysisItem {
  storyId: string;
  analysis: TelegramAnalysis;
}

interface RankedItem {
  text: string;
  pct?: number;
  supporterCount?: number;
  analystsTotal?: number;
  storyId: string;
}

export default function TelegramDiscussions({
  storyIds,
  prefetchedData,
  locale = "fa",
}: {
  storyIds?: string[];
  prefetchedData?: AnalysisItem[];
  locale?: string;
}) {
  const [items, setItems] = useState<AnalysisItem[]>(prefetchedData || []);
  const [dataReady, setDataReady] = useState(!!prefetchedData?.length);
  const [animDone, setAnimDone] = useState(false);
  const [noData, setNoData] = useState(prefetchedData !== undefined && prefetchedData.length === 0);

  // Fetch client-side if no prefetched data
  useEffect(() => {
    if (prefetchedData?.length) return;
    if (!storyIds || storyIds.length === 0) {
      setNoData(true);
      setDataReady(true);
      return;
    }
    let cancelled = false;

    Promise.all(
      storyIds.slice(0, 5).map(id =>
        fetch(`${API}/api/v1/social/stories/${id}/telegram-analysis`)
          .then(r => r.ok ? r.json() : null)
          .catch(() => null)
          .then(res => res?.status === "ok" ? { storyId: id, analysis: res.analysis } : null)
      )
    ).then(results => {
      if (cancelled) return;
      const valid = results.filter(Boolean) as AnalysisItem[];
      setItems(valid);
      if (valid.length === 0) setNoData(true);
      setDataReady(true);
    });

    return () => { cancelled = true; };
  }, [storyIds, prefetchedData]);

  const handleAnimComplete = useCallback(() => setAnimDone(true), []);

  if (!dataReady || !animDone) {
    return <TelegramAnalyzingAnimation durationMs={1000} onComplete={handleAnimComplete} />;
  }

  if (noData || items.length === 0) {
    return (
      <p className="text-[14px] text-slate-400 dark:text-slate-500 leading-5">
        تحلیل عمیق پس از اجرای بعدی در دسترس خواهد بود
      </p>
    );
  }

  // Collect unique predictions and claims, ranked by length (longer = more detailed = better)
  const predictions: RankedItem[] = [];
  const claims: RankedItem[] = [];
  const seenPred = new Set<string>();
  const seenClaim = new Set<string>();

  for (const item of items) {
    // Prefer Niloofar-polished versions when available. Raw fields still
    // feed the story page where the "موضوع: X |" grouping stays useful.
    const preds = item.analysis.predictions_display || item.analysis.predictions || [];
    const kclaims = item.analysis.key_claims_display || item.analysis.key_claims || [];
    for (const p of preds) {
      const text = typeof p === "string" ? p : (p as any).text || "";
      const pct = typeof p === "object" ? (p as any).pct : undefined;
      const supporterCount = typeof p === "object" ? (p as any).supporter_count : undefined;
      const analystsTotal = typeof p === "object" ? (p as any).analysts_total : undefined;
      const key = text.slice(0, 30);
      if (text && !seenPred.has(key)) {
        seenPred.add(key);
        predictions.push({ text, pct, supporterCount, analystsTotal, storyId: item.storyId });
      }
    }
    for (const c of kclaims) {
      const text = typeof c === "string" ? c : (c as any).text || String(c);
      const key = text.slice(0, 30);
      if (text && !seenClaim.has(key)) {
        seenClaim.add(key);
        claims.push({ text, storyId: item.storyId });
      }
    }
  }

  // Strip "در آینده،" (predictions) and "موضوع: X |" (claims) first — those
  // are LLM label-boilerplate the Pass-2 prompt explicitly requests.
  // Then strip numbering, bullets, and "با توجه به X،" hedges.
  // Channel attribution («کانال X ادعا کرد/کردند/کرده است...») is already
  // handled inside cleanClaim — earlier ad-hoc regexes that only matched
  // singular «ادعا کرد» were leaving orphan «ند» / «کرده است» heads.
  const clean = (t: string) => cleanClaim(cleanPrediction(t))
    .replace(/^[\s۰-۹0-9]+[).\-–]\s*/, "")
    .replace(/^[•·]\s*/, "")
    .replace(/^با توجه به [^،]+،\s*/, "");

  // Extract credibility label from claim text. Niloofar's polish step
  // prefixes each claim with one of these exact labels followed by a
  // colon («تأیید شده: …», «مشکوک: …», «تبلیغاتی: …», «تک‌منبع: …»,
  // «نیازمند تأیید: …»). Leading-prefix matches are preferred; free-text
  // keyword fallbacks stay below for un-polished claims that still
  // carry an "(… — cred)" suffix from pass-2.
  const getCredLabel = (t: string): { label: string; color: string } | null => {
    if (/^تأیید شده\s*:|^تایید شده\s*:/.test(t)) return { label: "تأیید شده", color: "text-emerald-500" };
    if (/^مشکوک\s*:/.test(t)) return { label: "مشکوک", color: "text-red-500" };
    if (/^تبلیغاتی\s*:/.test(t)) return { label: "تبلیغاتی", color: "text-red-400" };
    if (/^تک[‌\s]?منبع\s*:/.test(t)) return { label: "تک‌منبع", color: "text-amber-500" };
    if (/^نیازمند تأیید\s*:|^نیازمند تایید\s*:/.test(t)) return { label: "نیازمند تأیید", color: "text-amber-500" };
    // Free-text fallback for un-polished claims
    if (/مشکوک|اغراق|بعید|غیرواقعی/.test(t)) return { label: "مشکوک", color: "text-red-500" };
    if (/تبلیغاتی|جنبه تبلیغی|پروپاگاند/.test(t)) return { label: "تبلیغاتی", color: "text-red-400" };
    if (/نیازمند.*تایید|نیازمند.*تأیید|نیاز به تایید|نیاز به تأیید|تأیید نشده|تایید نشده|قابل.تأیید نیست|نیازمند.*مستقل|صحت.*نیاز/.test(t)) return { label: "تأیید نشده", color: "text-amber-500" };
    if (/قابل.اعتبار|تایید شده|تأیید شده|قابل.اعتماد|معتبر/.test(t)) return { label: "تأیید شده", color: "text-emerald-500" };
    return null;
  };

  // Sort predictions by pct (if available), then by length
  predictions.sort((a, b) => (b.pct || 0) - (a.pct || 0) || b.text.length - a.text.length);
  claims.sort((a, b) => b.text.length - a.text.length);

  return (
    <div className="animate-[fadeIn_0.2s_ease-in] space-y-4">
      {/* Predictions */}
      {predictions.length > 0 && (
        <div>
          <h4 className="text-[13px] font-black text-blue-600 dark:text-blue-400 mb-2">پیش‌بینی‌ها</h4>
          <div className="space-y-2">
            {predictions.slice(0, 4).map((item, i) => {
              const hasAnalystLine =
                item.supporterCount != null && item.analystsTotal != null && item.supporterCount > 0;
              return (
                <Link
                  key={i}
                  href={`/${locale}/stories/${item.storyId}?tg=predictions&hl=${encodeURIComponent(clean(item.text).slice(0, 40))}#telegram`}
                  className="block group border-b border-slate-100 dark:border-slate-800 pb-2 last:border-0 last:pb-0"
                >
                  {/* Without the analyst line, let the text take its row so
                      each item keeps roughly the same visual height. */}
                  <p
                    className={`text-[13px] leading-5 text-slate-600 dark:text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors ${
                      hasAnalystLine ? "line-clamp-2" : "line-clamp-3"
                    }`}
                  >
                    {clean(item.text)}
                  </p>
                  {hasAnalystLine && (
                    <p className="text-[13px] text-blue-500 dark:text-blue-400 text-left">
                      {toFa(item.supporterCount!)} از {toFa(item.analystsTotal!)} تحلیلگر
                    </p>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Claims */}
      {claims.length > 0 && (
        <div>
          <h4 className="text-[13px] font-black text-amber-600 dark:text-amber-400 mb-2">ادعاهای کلیدی</h4>
          <div className="space-y-2">
            {claims.slice(0, 4).map((item, i) => {
              const cred = getCredLabel(item.text);
              return (
                <Link
                  key={i}
                  href={`/${locale}/stories/${item.storyId}?tg=claims&hl=${encodeURIComponent(clean(item.text).slice(0, 40))}#telegram`}
                  className="block group border-b border-slate-100 dark:border-slate-800 pb-2 last:border-0 last:pb-0"
                >
                  <p
                    className={`text-[13px] leading-5 text-slate-600 dark:text-slate-400 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors ${
                      cred ? "line-clamp-2" : "line-clamp-3"
                    }`}
                  >
                    {clean(item.text)}
                  </p>
                  {cred && (
                    <p className={`text-[13px] ${cred.color} text-left`}>{cred.label}</p>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
