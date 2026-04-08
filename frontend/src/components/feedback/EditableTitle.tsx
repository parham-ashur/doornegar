"use client";

import { useState } from "react";
import { Pencil, Check, X } from "lucide-react";
import { useFeedback } from "@/components/feedback/FeedbackProvider";

export default function EditableTitle({
  storyId,
  initialTitle,
  className,
}: {
  storyId: string;
  initialTitle: string;
  className?: string;
}) {
  const { isRater } = useFeedback();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(initialTitle);
  const [saved, setSaved] = useState(initialTitle);

  if (!isRater) {
    return <span className={className}>{saved}</span>;
  }

  if (!editing) {
    return (
      <span className={`${className} group/edit inline`}>
        {saved}
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); setEditing(true); }}
          className="opacity-0 group-hover/edit:opacity-100 inline-flex items-center mr-2 p-1 text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-opacity"
          title="ویرایش"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </span>
    );
  }

  const handleSave = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/stories/${storyId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title_fa: title }),
      });
      if (res.ok) {
        setSaved(title);
        setEditing(false);
      }
    } catch {}
  };

  const handleCancel = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setTitle(saved);
    setEditing(false);
  };

  return (
    <div className="flex items-start gap-2" onClick={(e) => e.preventDefault()}>
      <textarea
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="flex-1 text-[inherit] font-[inherit] leading-[inherit] bg-transparent border border-blue-400 dark:border-blue-600 p-1 resize-none focus:outline-none"
        rows={2}
        dir="rtl"
        autoFocus
      />
      <div className="flex flex-col gap-1 pt-1">
        <button onClick={handleSave} className="p-1 text-emerald-600 hover:text-emerald-500">
          <Check className="h-4 w-4" />
        </button>
        <button onClick={handleCancel} className="p-1 text-red-500 hover:text-red-400">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
