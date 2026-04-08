"use client";

import { useState } from "react";
import { ArrowUp, ArrowDown, Pin } from "lucide-react";
import { useFeedback } from "@/components/feedback/FeedbackProvider";

export default function PriorityControl({
  storyId,
  initialPriority,
}: {
  storyId: string;
  initialPriority: number;
}) {
  const { isRater } = useFeedback();
  const [priority, setPriority] = useState(initialPriority);
  const [saving, setSaving] = useState(false);

  if (!isRater) return null;

  const update = async (newPriority: number) => {
    setSaving(true);
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/stories/${storyId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priority: newPriority }),
      });
      if (res.ok) setPriority(newPriority);
    } catch {}
    setSaving(false);
  };

  return (
    <div className="flex items-center gap-2 text-[11px] text-slate-500">
      <span>Priority: {priority}</span>
      <button
        onClick={() => update(priority + 5)}
        disabled={saving}
        className="p-1 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
        title="Increase priority"
      >
        <ArrowUp className="h-3 w-3" />
      </button>
      <button
        onClick={() => update(priority - 5)}
        disabled={saving}
        className="p-1 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
        title="Decrease priority"
      >
        <ArrowDown className="h-3 w-3" />
      </button>
      <button
        onClick={() => update(10)}
        disabled={saving || priority === 10}
        className="p-1 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
        title="Pin to top"
      >
        <Pin className="h-3 w-3" />
      </button>
      {priority !== 0 && (
        <button
          onClick={() => update(0)}
          disabled={saving}
          className="text-[10px] border border-slate-300 dark:border-slate-700 px-1.5 py-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          Reset
        </button>
      )}
    </div>
  );
}
