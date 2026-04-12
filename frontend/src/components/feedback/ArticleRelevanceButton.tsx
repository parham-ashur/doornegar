"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useFeedback } from "./FeedbackProvider";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ArticleRelevanceButtonProps {
  storyId: string;
  articleId: string;
}

export default function ArticleRelevanceButton({ storyId, articleId }: ArticleRelevanceButtonProps) {
  const { isRater, token } = useFeedback();
  const [selected, setSelected] = useState<boolean | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleClick(isRelevant: boolean) {
    if (submitting || selected !== null) return;
    setSubmitting(true);
    try {
      if (isRater && token) {
        // Authenticated rater path
        const res = await fetch(`${API}/api/v1/feedback/article-relevance`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            story_id: storyId,
            article_id: articleId,
            is_relevant: isRelevant,
          }),
        });
        if (res.ok) setSelected(isRelevant);
      } else {
        // Public feedback path (improvement system)
        const res = await fetch(`${API}/api/v1/improvements`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_type: "article",
            target_id: articleId,
            issue_type: "wrong_clustering",
            reason: isRelevant ? "مقاله مرتبط است" : "مقاله نامرتبط است",
            device_info: typeof window !== "undefined"
              ? `${window.innerWidth <= 768 ? "mobile" : "desktop"} ${window.innerWidth}×${window.innerHeight}`
              : null,
          }),
        });
        if (res.ok) setSelected(isRelevant);
      }
    } catch {}
    setSubmitting(false);
  }

  return (
    <div className="flex items-center gap-2 mt-1.5">
      <button
        onClick={() => handleClick(true)}
        disabled={submitting || selected !== null}
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] border transition-colors ${
          selected === true
            ? "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-600"
            : selected !== null
            ? "border-slate-200 dark:border-slate-700 text-slate-300 dark:text-slate-600 cursor-default"
            : "border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-emerald-400 hover:text-emerald-600 dark:hover:border-emerald-500 dark:hover:text-emerald-400"
        } disabled:cursor-default`}
        title="مرتبط"
      >
        <ThumbsUp className={`h-3 w-3 ${selected === true ? "fill-current" : ""}`} />
        <span>مرتبط</span>
      </button>
      <button
        onClick={() => handleClick(false)}
        disabled={submitting || selected !== null}
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] border transition-colors ${
          selected === false
            ? "border-red-500 bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400 dark:border-red-600"
            : selected !== null
            ? "border-slate-200 dark:border-slate-700 text-slate-300 dark:text-slate-600 cursor-default"
            : "border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-red-400 hover:text-red-600 dark:hover:border-red-500 dark:hover:text-red-400"
        } disabled:cursor-default`}
        title="نامرتبط"
      >
        <ThumbsDown className={`h-3 w-3 ${selected === false ? "fill-current" : ""}`} />
        <span>نامرتبط</span>
      </button>
    </div>
  );
}
