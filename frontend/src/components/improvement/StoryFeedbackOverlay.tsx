"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Type, Image as ImageIcon, FileText, LayoutGrid,
  MessageSquare, Globe, BarChart3, Sparkles,
} from "lucide-react";
import ImprovementModal from "@/components/improvement/ImprovementModal";

type TargetType =
  | "story" | "story_title" | "story_image" | "story_summary"
  | "article" | "source" | "source_dimension" | "layout" | "homepage" | "other";

type IssueType =
  | "wrong_title" | "bad_image" | "wrong_clustering" | "bad_summary"
  | "wrong_source_class" | "layout_issue" | "bug" | "feature_request" | "other";

interface FeedbackContext {
  targetType: TargetType;
  targetId?: string;
  currentValue?: string;
  defaultIssueType?: IssueType;
  contextLabel?: string;
}

/**
 * Attaches a floating feedback toolbar to the story detail page when the URL
 * contains ?feedback=1. The toolbar lets the user select what they want to
 * give feedback about (title, image, summary, article clustering, source
 * classification, media dimensions, layout, or other). Clicking opens the
 * ImprovementModal with the right target pre-selected.
 *
 * This is an overlay approach — it doesn't require modifying the server-side
 * story detail page structure. The feedback target info is passed in props.
 */
interface Props {
  storyId: string;
  storyTitle: string;
}

export default function StoryFeedbackOverlay({ storyId, storyTitle }: Props) {
  const searchParams = useSearchParams();
  const [active, setActive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [context, setContext] = useState<FeedbackContext>({ targetType: "other" });
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    setActive(searchParams.get("feedback") === "1");
  }, [searchParams]);

  if (!active) return null;

  const open = (ctx: FeedbackContext) => {
    setContext(ctx);
    setModalOpen(true);
  };

  const buttons: {
    label: string;
    icon: typeof Type;
    ctx: FeedbackContext;
  }[] = [
    {
      label: "عنوان خبر",
      icon: Type,
      ctx: {
        targetType: "story_title",
        targetId: storyId,
        currentValue: storyTitle,
        defaultIssueType: "wrong_title",
        contextLabel: storyTitle,
      },
    },
    {
      label: "تصویر خبر",
      icon: ImageIcon,
      ctx: {
        targetType: "story_image",
        targetId: storyId,
        defaultIssueType: "bad_image",
        contextLabel: storyTitle,
      },
    },
    {
      label: "خلاصه / تحلیل",
      icon: FileText,
      ctx: {
        targetType: "story_summary",
        targetId: storyId,
        defaultIssueType: "bad_summary",
        contextLabel: storyTitle,
      },
    },
    {
      label: "دسته‌بندی مقاله‌ها",
      icon: LayoutGrid,
      ctx: {
        targetType: "story",
        targetId: storyId,
        defaultIssueType: "wrong_clustering",
        contextLabel: storyTitle,
      },
    },
    {
      label: "مقاله خاص",
      icon: MessageSquare,
      ctx: {
        targetType: "article",
        targetId: storyId,
        defaultIssueType: "wrong_clustering",
        contextLabel: storyTitle,
      },
    },
    {
      label: "دسته‌بندی رسانه",
      icon: Globe,
      ctx: {
        targetType: "source",
        targetId: storyId,
        defaultIssueType: "wrong_source_class",
        contextLabel: storyTitle,
      },
    },
    {
      label: "ابعاد رسانه‌ای",
      icon: BarChart3,
      ctx: {
        targetType: "source_dimension",
        targetId: storyId,
        defaultIssueType: "other",
        contextLabel: storyTitle,
      },
    },
    {
      label: "چیدمان / طراحی",
      icon: Sparkles,
      ctx: {
        targetType: "layout",
        targetId: storyId,
        defaultIssueType: "layout_issue",
        contextLabel: storyTitle,
      },
    },
  ];

  return (
    <>
      {/* Fixed sidebar on desktop, bottom sheet on mobile */}
      <div
        dir="rtl"
        className="fixed top-20 right-4 left-4 md:left-auto md:right-4 md:top-24 md:w-72 z-40 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 shadow-xl"
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700 bg-blue-50 dark:bg-blue-950/30 text-slate-900 dark:text-white"
        >
          <span className="text-xs font-bold">حالت بازخورد — انتخاب کنید</span>
          <span className="text-xs text-slate-500">{expanded ? "−" : "+"}</span>
        </button>

        {expanded && (
          <div className="p-2 grid grid-cols-2 gap-1.5 max-h-[60vh] overflow-y-auto">
            {buttons.map((btn) => {
              const Icon = btn.icon;
              return (
                <button
                  key={btn.label}
                  onClick={() => open(btn.ctx)}
                  className="flex items-center gap-1.5 p-2 text-[11px] text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:border-slate-900 dark:hover:border-white hover:bg-slate-50 dark:hover:bg-slate-800 text-right"
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="line-clamp-1">{btn.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <ImprovementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        targetType={context.targetType}
        targetId={context.targetId}
        currentValue={context.currentValue}
        defaultIssueType={context.defaultIssueType}
        contextLabel={context.contextLabel}
      />
    </>
  );
}
