"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import TelegramAnalyzingAnimation from "@/components/common/TelegramAnalyzingAnimation";
import {
  cleanClaim,
  cleanPrediction,
  displayPredictions,
} from "@/lib/telegram-text";
import type { TelegramAnalysis } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AnalysisItem {
  storyId: string;
  analysis: TelegramAnalysis;
}

interface RankedItem {
  text: string;
  pct?: number;
  supporters?: string[];
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
  // If the server handed us a populated prefetch, trust it and skip the
  // client fetch. If prefetchedData is empty but storyIds are provided,
  // fall through to the client-side fetch — this handles the SSR
  // regression where 15 parallel Railway calls on ISR regen all fail
  // under load and bake `[]` into the cached HTML. Without this
  // fallback the sidebar stays blank for the full 300s revalidate
  // window even though the backend has the data.
  const hasPrefetch = !!prefetchedData?.length;
  const canFallbackFetch = !hasPrefetch && !!storyIds?.length;
  const [items, setItems] = useState<AnalysisItem[]>(prefetchedData || []);
  const [dataReady, setDataReady] = useState(hasPrefetch);
  const [animDone, setAnimDone] = useState(false);
  const [noData, setNoData] = useState(prefetchedData !== undefined && prefetchedData.length === 0 && !canFallbackFetch);

  useEffect(() => {
    if (hasPrefetch) return;
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
  }, [storyIds, hasPrefetch]);

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

  // Collect unique predictions, ranked by length (longer = more detailed = better)
  const predictions: RankedItem[] = [];
  const seenPred = new Set<string>();

  for (const item of items) {
    const preds = displayPredictions(item.analysis);
    for (const p of preds) {
      const text = typeof p === "string" ? p : p.text || "";
      const pct = typeof p === "object" ? p.pct : undefined;
      const supporters =
        typeof p === "object" && Array.isArray(p.supporters)
          ? p.supporters.filter((s): s is string => typeof s === "string" && s.length > 0)
          : undefined;
      // Dedup by full text — first-30-chars was collapsing every prediction
      // starting with «احتمال ادامه …» into one.
      const key = text.trim();
      if (text && !seenPred.has(key)) {
        seenPred.add(key);
        predictions.push({ text, pct, supporters, storyId: item.storyId });
      }
    }
  }

  const clean = (t: string) => cleanClaim(cleanPrediction(t))
    .replace(/^[\s۰-۹0-9]+[).\-–]\s*/, "")
    .replace(/^[•·]\s*/, "")
    .replace(/^با توجه به [^،]+،\s*/, "");

  // Sort predictions by pct (if available), then by length
  predictions.sort((a, b) => (b.pct || 0) - (a.pct || 0) || b.text.length - a.text.length);

  // Source-dedup pass: each Telegram channel can back at most one prediction.
  // Walk in display-order (already sorted), attribute each supporter to the
  // first prediction it appears under, drop later mentions, and drop any
  // prediction that ends up with zero supporters AFTER filtering — but only
  // if it had supporters to begin with. Predictions with no supporters
  // metadata at all (legacy data) stay so the section isn't empty.
  const usedSources = new Set<string>();
  const dedupedPreds: RankedItem[] = [];
  for (const p of predictions) {
    if (!p.supporters || p.supporters.length === 0) {
      dedupedPreds.push(p);
      continue;
    }
    const fresh: string[] = [];
    const seenLocal = new Set<string>();
    for (const s of p.supporters) {
      if (usedSources.has(s) || seenLocal.has(s)) continue;
      seenLocal.add(s);
      fresh.push(s);
    }
    if (fresh.length === 0) continue;
    fresh.forEach(s => usedSources.add(s));
    dedupedPreds.push({ ...p, supporters: fresh });
  }

  return (
    <div className="animate-[fadeIn_0.2s_ease-in]">
      {dedupedPreds.length > 0 && (
        <div>
          <h4 className="text-[13px] font-black text-blue-600 dark:text-blue-400 mb-2">پیش‌بینی‌ها</h4>
          <div className="space-y-2">
            {dedupedPreds.slice(0, 7).map((item, i) => (
              <Link
                key={i}
                href={`/${locale}/stories/${item.storyId}?tg=predictions&hl=${encodeURIComponent(clean(item.text).slice(0, 40))}#telegram`}
                className="block group border-b border-slate-100 dark:border-slate-800 pb-2 last:border-0 last:pb-0"
              >
                <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-3">
                  {clean(item.text)}
                </p>
                {item.supporters && item.supporters.length > 0 && (
                  <p className="text-[11px] leading-5 text-slate-400 dark:text-slate-500 mt-1">
                    {item.supporters.join("، ")}
                  </p>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
