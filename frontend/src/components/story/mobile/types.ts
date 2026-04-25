export type MobileLayoutKind = "story" | "blindspot" | "max_disagreement" | "telegram";

export interface MobileStorySide {
  label_fa: string;
  label_en: string;
  body_fa: string;
  body_en: string;
  tone: "state" | "diaspora" | "independent";
}

export interface MobileStorySlot {
  id: string;
  kind: MobileLayoutKind;
  title_fa: string;
  title_en: string;
  summary_fa?: string;
  summary_en?: string;
  imageUrl?: string;
  videoUrl?: string;
  sides?: [MobileStorySide, MobileStorySide];
  telegram?: {
    predictions_fa: string[];
    claims: { text_fa: string; credibility?: "verified" | "suspect" | "unverified" }[];
  };
  pairId?: string;
}
