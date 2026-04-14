"use client";

import { useSearchParams } from "next/navigation";
import { useState, useCallback } from "react";
import { ArrowUp, ArrowDown, GitMerge, Type, Image as ImageIcon, FileText } from "lucide-react";
import ImprovementModal from "@/components/improvement/ImprovementModal";

type TargetType = "story" | "story_title" | "story_image" | "story_summary" | "merge_stories" | "other";
type IssueType = "wrong_title" | "bad_image" | "bad_summary" | "priority_higher" | "priority_lower" | "merge_stories" | "other";

interface FeedbackContext {
  targetType: TargetType;
  targetId?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
}

export function useFeedbackMode() {
  const params = useSearchParams();
  return params.get("feedback") === "1";
}

export function FeedbackButtons({ storyId, storyTitle, imageUrl }: { storyId: string; storyTitle: string; imageUrl?: string | null }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [ctx, setCtx] = useState<FeedbackContext>({ targetType: "other" });

  const open = useCallback((c: FeedbackContext) => { setCtx(c); setModalOpen(true); }, []);

  const buttons = [
    { icon: Type, label: "عنوان", action: () => open({ targetType: "story_title", targetId: storyId, currentValue: storyTitle, defaultIssueType: "wrong_title", contextLabel: storyTitle }) },
    { icon: ImageIcon, label: "تصویر", action: () => open({ targetType: "story_image", targetId: storyId, defaultIssueType: "bad_image", contextLabel: storyTitle }) },
    { icon: FileText, label: "خلاصه", action: () => open({ targetType: "story_summary", targetId: storyId, defaultIssueType: "bad_summary", contextLabel: storyTitle }) },
    { icon: ArrowUp, label: "↑", action: () => open({ targetType: "story", targetId: storyId, defaultIssueType: "priority_higher", contextLabel: storyTitle }) },
    { icon: ArrowDown, label: "↓", action: () => open({ targetType: "story", targetId: storyId, defaultIssueType: "priority_lower", contextLabel: storyTitle }) },
    { icon: GitMerge, label: "ادغام", action: () => open({ targetType: "merge_stories", targetId: storyId, defaultIssueType: "merge_stories", contextLabel: storyTitle }) },
  ];

  return (
    <>
      <div className="flex items-center gap-0.5 mt-1" onClick={e => e.preventDefault()}>
        {buttons.map((b, i) => {
          const Icon = b.icon;
          return (
            <button
              key={i}
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); b.action(); }}
              className="p-1 text-blue-400 hover:text-blue-600 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors"
              title={b.label}
            >
              <Icon className="h-3 w-3" />
            </button>
          );
        })}
      </div>
      <ImprovementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        targetType={ctx.targetType}
        targetId={ctx.targetId}
        currentValue={ctx.currentValue}
        defaultIssueType={ctx.defaultIssueType}
        contextLabel={ctx.contextLabel}
      />
    </>
  );
}
