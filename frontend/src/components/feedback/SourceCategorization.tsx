"use client";

import { useState } from "react";
import { useFeedback } from "./FeedbackProvider";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ALIGNMENT_OPTIONS = [
  { value: "state", label: "درون‌مرزی" },
  { value: "semi_state", label: "نیمه‌دولتی" },
  { value: "independent", label: "مستقل" },
  { value: "diaspora", label: "برون‌مرزی" },
] as const;

interface SourceCategorizationProps {
  sourceId: string;
  currentAlignment: string | null;
}

export default function SourceCategorization({ sourceId, currentAlignment }: SourceCategorizationProps) {
  const { isRater, token } = useFeedback();
  const [open, setOpen] = useState(false);
  const [selectedAlignment, setSelectedAlignment] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (!isRater) return null;

  async function handleSubmit() {
    if (!selectedAlignment || submitting) return;
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        source_id: sourceId,
        suggested_alignment: selectedAlignment,
      };
      if (note.trim()) {
        body.categorization_note = note.trim();
      }
      const res = await fetch(`${API}/api/v1/feedback/source-categorization`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setSubmitted(true);
        setOpen(false);
      }
    } catch {
      // silently fail
    }
    setSubmitting(false);
  }

  if (submitted) {
    return (
      <span className="text-[10px] text-emerald-600 dark:text-emerald-400">
        ثبت شد &#10003;
      </span>
    );
  }

  return (
    <span className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        className="text-[10px] text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 underline underline-offset-2 transition-colors"
      >
        پیشنهاد تغییر
      </button>

      {open && (
        <div className="absolute top-full right-0 z-20 mt-1 w-56 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 shadow-sm space-y-2">
          <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300">
            دسته‌بندی پیشنهادی
          </p>

          <div className="space-y-1">
            {ALIGNMENT_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`flex items-center gap-2 px-2 py-1 text-[11px] cursor-pointer border transition-colors ${
                  selectedAlignment === opt.value
                    ? "border-slate-500 dark:border-slate-400 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white"
                    : "border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                } ${opt.value === currentAlignment ? "font-bold" : ""}`}
              >
                <input
                  type="radio"
                  name={`alignment-${sourceId}`}
                  value={opt.value}
                  checked={selectedAlignment === opt.value}
                  onChange={() => setSelectedAlignment(opt.value)}
                  className="accent-slate-600 dark:accent-slate-400"
                />
                {opt.label}
                {opt.value === currentAlignment && (
                  <span className="text-[9px] text-slate-400 dark:text-slate-500">(فعلی)</span>
                )}
              </label>
            ))}
          </div>

          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="توضیح (اختیاری)..."
            className="w-full border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1.5 text-[11px] text-slate-700 dark:text-slate-300 placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:border-slate-500"
          />

          <div className="flex items-center gap-2">
            <button
              onClick={handleSubmit}
              disabled={!selectedAlignment || submitting}
              className="px-3 py-1 text-[11px] font-medium border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-40"
            >
              {submitting ? "..." : "ثبت"}
            </button>
            <button
              onClick={() => setOpen(false)}
              className="px-3 py-1 text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            >
              انصراف
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
