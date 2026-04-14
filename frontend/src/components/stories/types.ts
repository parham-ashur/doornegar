import type { StoryBackgroundMedia } from "./StoryBackground";

export type StoryCore = {
  id: string;
  title: string;
  media: StoryBackgroundMedia;
  sourceCount?: number;
  articleCount?: number;
  summary?: string;
  progressivePosition?: string;
  conservativePosition?: string;
  telegramSummary?: string;
  telegramPredictions?: string[];
  telegramClaims?: { source?: string; text: string; verified?: boolean }[];
  // Coverage percentages — drive the bias comparison bar
  statePct?: number;
  diasporaPct?: number;
  // List of source names that covered this story (Farsi names preferred)
  sourceNames?: string[];
};

export type StorySlot =
  | { kind: "story"; story: StoryCore }
  | { kind: "telegram"; data: TelegramSlotData }
  | { kind: "blindspot"; data: BlindspotSlotData }
  | { kind: "maxDisagreement"; data: MaxDisagreementSlotData }
  | { kind: "desktopPreview"; url: string }
  | { kind: "placeholder"; label: string; bg?: string };

export type TelegramSlotData = {
  title: string;
  predictions: { text: string; analystPercent?: number }[];
  claims: { source: string; text: string; verified?: boolean; story?: StoryCore }[];
};

export type BlindspotSlotData = {
  top: { story: StoryCore; sideLabel: string; excerpt: string };
  bottom: { story: StoryCore; sideLabel: string; excerpt: string };
};

export type MaxDisagreementSlotData = {
  // Two different stories that have the highest dispute scores
  top: { story: StoryCore; disputeScore: number; excerpt: string };
  bottom: { story: StoryCore; disputeScore: number; excerpt: string };
};
