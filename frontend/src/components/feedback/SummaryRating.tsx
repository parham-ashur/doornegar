"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { useFeedback } from "./FeedbackProvider";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SummaryRatingProps {
  storyId: string;
}

export default function SummaryRating({ storyId }: SummaryRatingProps) {
  const { isRater, token } = useFeedback();
  const [rating, setRating] = useState(0);
  const [hovered, setHovered] = useState(0);
  const [correction, setCorrection] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (!isRater) return null;

  async function handleSubmit() {
    if (rating === 0 || submitting) return;
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        story_id: storyId,
        summary_rating: rating,
      };
      if (correction.trim()) {
        body.summary_correction = correction.trim();
      }
      const res = await fetch(`${API}/api/v1/feedback/summary-rating`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setSubmitted(true);
      }
    } catch {
      // silently fail
    }
    setSubmitting(false);
  }

  if (submitted) {
    return (
      <div dir="rtl" className="border border-slate-200 dark:border-slate-800 px-4 py-3 mt-4">
        <p className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
          ثبت شد &#10003;
        </p>
      </div>
    );
  }

  return (
    <div dir="rtl" className="border border-slate-200 dark:border-slate-800 px-4 py-4 mt-4 space-y-3">
      <p className="text-xs font-bold text-slate-700 dark:text-slate-300">
        آیا این خلاصه دقیق است؟
      </p>

      {/* Star rating */}
      <div className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onMouseEnter={() => setHovered(star)}
            onMouseLeave={() => setHovered(0)}
            onClick={() => setRating(star)}
            className="p-0.5 transition-colors"
          >
            <Star
              className={`h-5 w-5 ${
                star <= (hovered || rating)
                  ? "text-amber-500 fill-amber-500"
                  : "text-slate-300 dark:text-slate-600"
              }`}
            />
          </button>
        ))}
        {rating > 0 && (
          <span className="text-[11px] text-slate-400 mr-2">{rating} از ۵</span>
        )}
      </div>

      {/* Correction text */}
      <div>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400 mb-1">
          پیشنهاد اصلاح (اختیاری)
        </label>
        <textarea
          value={correction}
          onChange={(e) => setCorrection(e.target.value)}
          rows={2}
          placeholder="اگر خلاصه نادرست است، اصلاح پیشنهادی خود را بنویسید..."
          className="w-full border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-xs text-slate-700 dark:text-slate-300 placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:border-slate-500 dark:focus:border-slate-500"
        />
      </div>

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={rating === 0 || submitting}
        className="px-4 py-1.5 text-xs font-medium border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-40 disabled:cursor-default"
      >
        {submitting ? "..." : "ثبت نظر"}
      </button>
    </div>
  );
}
