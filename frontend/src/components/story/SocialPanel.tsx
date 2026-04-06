"use client";

import { useLocale, useTranslations } from "next-intl";
import { MessageCircle, Eye, Share2, ThumbsUp, ThumbsDown, Minus } from "lucide-react";
import type { SocialSentiment } from "@/lib/types";

interface SocialPanelProps {
  sentiment: SocialSentiment | null;
  totalPosts: number;
}

export default function SocialPanel({ sentiment, totalPosts }: SocialPanelProps) {
  const locale = useLocale();
  const t = useTranslations();

  if (!sentiment && totalPosts === 0) return null;

  const s = sentiment;

  return (
    <div className="card">
      <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
        <MessageCircle className="h-4 w-4 text-blue-500" />
        {t("social.telegram_reactions")}
      </h3>

      {/* Key metrics */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg bg-slate-50 p-3 text-center dark:bg-slate-800">
          <MessageCircle className="mx-auto mb-1 h-4 w-4 text-slate-400" />
          <p className="text-lg font-bold text-slate-900 dark:text-white">
            {s?.total_posts || totalPosts}
          </p>
          <p className="text-[10px] text-slate-500">{t("social.posts")}</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 text-center dark:bg-slate-800">
          <Eye className="mx-auto mb-1 h-4 w-4 text-slate-400" />
          <p className="text-lg font-bold text-slate-900 dark:text-white">
            {s?.total_views ? formatNumber(s.total_views) : "—"}
          </p>
          <p className="text-[10px] text-slate-500">{t("social.views")}</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 text-center dark:bg-slate-800">
          <Share2 className="mx-auto mb-1 h-4 w-4 text-slate-400" />
          <p className="text-lg font-bold text-slate-900 dark:text-white">
            {s?.total_forwards ? formatNumber(s.total_forwards) : "—"}
          </p>
          <p className="text-[10px] text-slate-500">
            {locale === "fa" ? "بازنشر" : "Forwards"}
          </p>
        </div>
      </div>

      {/* Sentiment bar */}
      {s && (s.positive_count > 0 || s.negative_count > 0 || s.neutral_count > 0) && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium text-slate-600 dark:text-slate-400">
            {t("social.sentiment")}
          </p>
          <div className="flex h-3 overflow-hidden rounded-full">
            {s.positive_count > 0 && (
              <div
                className="bg-emerald-500"
                style={{
                  width: `${(s.positive_count / s.total_posts) * 100}%`,
                }}
              />
            )}
            {s.neutral_count > 0 && (
              <div
                className="bg-slate-300 dark:bg-slate-600"
                style={{
                  width: `${(s.neutral_count / s.total_posts) * 100}%`,
                }}
              />
            )}
            {s.negative_count > 0 && (
              <div
                className="bg-red-500"
                style={{
                  width: `${(s.negative_count / s.total_posts) * 100}%`,
                }}
              />
            )}
          </div>
          <div className="mt-1.5 flex justify-between text-[10px] text-slate-500">
            <span className="flex items-center gap-0.5">
              <ThumbsUp className="h-3 w-3 text-emerald-500" />
              {t("social.positive")} ({s.positive_count})
            </span>
            <span className="flex items-center gap-0.5">
              <Minus className="h-3 w-3 text-slate-400" />
              {t("social.neutral")} ({s.neutral_count})
            </span>
            <span className="flex items-center gap-0.5">
              <ThumbsDown className="h-3 w-3 text-red-500" />
              {t("social.negative")} ({s.negative_count})
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}
