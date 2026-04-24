"use client";

import { useState } from "react";
import { ThumbsDown } from "lucide-react";
import { useFeedback } from "./FeedbackProvider";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ArticleRelevanceButtonProps {
  storyId: string;
  articleId: string;
}

// Only the "نامرتبط" button remains — clicking replaces the button with
// a thank-you message in the same typography. Feedback on "relevant"
// articles isn't useful signal (relevant is the default assumption);
// the value is letting readers flag wrongly-clustered pieces.
export default function ArticleRelevanceButton({ storyId, articleId }: ArticleRelevanceButtonProps) {
  const { isRater, token } = useFeedback();
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleClick() {
    if (submitting || done) return;
    setSubmitting(true);
    try {
      if (isRater && token) {
        const res = await fetch(`${API}/api/v1/feedback/article-relevance`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            story_id: storyId,
            article_id: articleId,
            is_relevant: false,
          }),
        });
        if (res.ok) setDone(true);
      } else {
        const res = await fetch(`${API}/api/v1/improvements`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_type: "article",
            target_id: articleId,
            issue_type: "wrong_clustering",
            reason: "مقاله نامرتبط است",
            device_info: typeof window !== "undefined"
              ? `${window.innerWidth <= 768 ? "mobile" : "desktop"} ${window.innerWidth}×${window.innerHeight}`
              : null,
          }),
        });
        if (res.ok) setDone(true);
      }
    } catch {}
    setSubmitting(false);
  }

  if (done) {
    return (
      <p className="mt-1.5 text-[10px] text-slate-500 dark:text-slate-400">
        از بازخورد شما ممنونیم؛ گزارش شما ثبت شد.
      </p>
    );
  }

  return (
    <div className="mt-1.5">
      <button
        onClick={handleClick}
        disabled={submitting}
        className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] border border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-red-400 hover:text-red-600 dark:hover:border-red-500 dark:hover:text-red-400 transition-colors disabled:cursor-default"
        title="نامرتبط"
      >
        <ThumbsDown className="h-3 w-3" />
        <span>نامرتبط</span>
      </button>
    </div>
  );
}
