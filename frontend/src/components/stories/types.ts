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
};

export type StorySlot =
  | { kind: "story"; story: StoryCore }
  | { kind: "telegram"; data: TelegramSlotData }
  | { kind: "blindspot"; data: BlindspotSlotData }
  | { kind: "maxDisagreement"; data: MaxDisagreementSlotData }
  | { kind: "placeholder"; label: string; bg?: string };

export type TelegramSlotData = {
  title: string;
  predictions: { text: string; percent?: number }[];
  claims: { source: string; text: string; verified?: boolean; story?: StoryCore }[];
};

export type BlindspotSlotData = {
  top: { story: StoryCore; sideLabel: string; excerpt: string };
  bottom: { story: StoryCore; sideLabel: string; excerpt: string };
};

export type MaxDisagreementSlotData = {
  story: StoryCore;
  top: { sideLabel: string; percent: number; framing: string };
  bottom: { sideLabel: string; percent: number; framing: string };
};
