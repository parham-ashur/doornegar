"use client";

import { useState, useCallback, createContext, useContext } from "react";
import { Type, ArrowUp, ArrowDown, GitMerge } from "lucide-react";
import ImprovementModal from "@/components/improvement/ImprovementModal";
import RaterOnboarding from "@/components/improvement/RaterOnboarding";
import ImageSuggestionButton from "@/components/story/ImageSuggestionButton";

type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "source_dimension" | "layout" | "homepage"
  | "merge_stories" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request"
  | "priority_higher" | "priority_lower" | "merge_stories" | "other";

interface FeedbackContext {
  targetType: TargetType;
  targetId?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
  imageUrl?: string | null;
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FeedbackCtx = createContext<(ctx: FeedbackContext) => void>(() => {});

export function FeedbackProvider({ children }: { children: React.ReactNode }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });

  const openFeedback = useCallback((ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  }, []);

  return (
    <FeedbackCtx.Provider value={openFeedback}>
      <RaterOnboarding />
      <div dir="rtl" className="bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-900/50 px-4 py-3">
        <div className="mx-auto max-w-7xl">
          <p className="text-[13px] leading-6 text-slate-700 dark:text-slate-300">
            <span className="font-bold">حالت بازخورد</span> —
            دکمه‌های کوچک کنار هر خبر را ببینید: عنوان، تصویر، اولویت و ادغام.
          </p>
        </div>
      </div>
      {children}
      <ImprovementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        targetType={context.targetType}
        targetId={context.targetId}
        currentValue={context.currentValue}
        defaultIssueType={context.defaultIssueType}
        contextLabel={context.contextLabel}
        imageUrl={context.imageUrl}
      />
    </FeedbackCtx.Provider>
  );
}

/** Wrap a story card to add feedback buttons */
export function StoryFeedback({ storyId, title, imageUrl, children }: {
  storyId: string;
  title: string;
  imageUrl?: string | null;
  children: React.ReactNode;
}) {
  const openFeedback = useContext(FeedbackCtx);

  return (
    <div className="relative group">
      {children}
      {/* Title feedback */}
      <button type="button" title="عنوان" aria-label="عنوان"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "story_title", targetId: storyId, currentValue: title, defaultIssueType: "wrong_title", contextLabel: title }); }}
        className="absolute top-1 left-1 z-20 p-1.5 bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 shadow-md md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity hover:scale-110">
        <Type className="h-3 w-3" />
      </button>
      {/* Image suggestion (URL paste) — shown whether or not the story
          already has an image. When there's no image, it lets the rater
          suggest one; when there is one, it lets them suggest a better
          replacement. */}
      <div
        className="absolute top-1 right-1 z-20 md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        <ImageSuggestionButton storyId={storyId} storyTitle={title} />
      </div>
      {/* Priority + merge actions */}
      <div className="absolute bottom-1 right-1 z-20 flex gap-1 md:opacity-0 md:group-hover:opacity-100 opacity-100 transition-opacity" dir="ltr">
        <PriorityBtn storyId={storyId} direction="higher" />
        <PriorityBtn storyId={storyId} direction="lower" />
        <button type="button" title="ادغام با موضوع دیگر"
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFeedback({ targetType: "merge_stories", targetId: storyId, defaultIssueType: "merge_stories", contextLabel: title }); }}
          className="p-1 bg-slate-900/80 dark:bg-white/80 text-white dark:text-slate-900 shadow-sm hover:scale-110">
          <GitMerge className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

function PriorityBtn({ storyId, direction }: { storyId: string; direction: "higher" | "lower" }) {
  const Icon = direction === "higher" ? ArrowUp : ArrowDown;
  const label = direction === "higher" ? "مهم‌تر" : "کم‌اهمیت‌تر";
  const submit = async (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    try {
      await fetch(`${API}/api/v1/improvements`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: "story", target_id: storyId, issue_type: `priority_${direction}`, reason: label }),
      });
    } catch {}
  };
  return (
    <button type="button" onClick={submit} title={label}
      className="p-1 bg-slate-900/80 dark:bg-white/80 text-white dark:text-slate-900 shadow-sm hover:scale-110">
      <Icon className="h-3 w-3" />
    </button>
  );
}
