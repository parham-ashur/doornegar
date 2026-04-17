/**
 * Single source of truth for the 4-subgroup narrative taxonomy on the
 * frontend. Backend authors the classification; frontend only presents
 * it. Keep this file in sync with `backend/app/services/narrative_groups.py`.
 */

import type { NarrativeGroup, NarrativeGroups, StoryBrief } from "./types";

export const NARRATIVE_GROUP_ORDER: NarrativeGroup[] = [
  "principlist",
  "reformist",
  "moderate_diaspora",
  "radical_diaspora",
];

export const GROUP_LABELS_FA: Record<NarrativeGroup, string> = {
  principlist: "اصول‌گرا",
  reformist: "اصلاح‌طلب",
  moderate_diaspora: "میانه‌رو",
  radical_diaspora: "رادیکال",
};

export const GROUP_LABELS_EN: Record<NarrativeGroup, string> = {
  principlist: "Principlist",
  reformist: "Reformist",
  moderate_diaspora: "Moderate diaspora",
  radical_diaspora: "Radical diaspora",
};

/** Navy family inside, orange family outside. Shade encodes subgroup. */
export const GROUP_COLORS: Record<NarrativeGroup, string> = {
  principlist: "#1e3a5f",       // dark navy
  reformist: "#4f7cac",         // slate blue
  moderate_diaspora: "#f97316", // warm amber
  radical_diaspora: "#c2410c",  // deep orange
};

export type Side = "inside" | "outside";

export const SIDE_OF_GROUP: Record<NarrativeGroup, Side> = {
  principlist: "inside",
  reformist: "inside",
  moderate_diaspora: "outside",
  radical_diaspora: "outside",
};

export const SIDE_LABELS_FA: Record<Side, string> = {
  inside: "درون‌مرزی",
  outside: "برون‌مرزی",
};

/** Base color used for side-level elements (bar dividers, headings). */
export const SIDE_BASE_COLOR: Record<Side, string> = {
  inside: "#1e3a5f",
  outside: "#c2410c",
};

export const GROUPS_BY_SIDE: Record<Side, NarrativeGroup[]> = {
  inside: ["principlist", "reformist"],
  outside: ["moderate_diaspora", "radical_diaspora"],
};

/**
 * Pull percentages out of a StoryBrief.
 *
 * Backwards compat: if `narrative_groups` is missing (older cached
 * responses), synthesize a rough mapping from the legacy 3-bucket
 * state_pct / diaspora_pct / independent_pct fields so the UI doesn't
 * render 0s. Approximation: state_pct → principlist, independent_pct
 * → reformist (conservative guess), diaspora_pct → moderate_diaspora.
 * This only applies until all cached responses refresh.
 */
export function narrativeGroupsFrom(story: StoryBrief): NarrativeGroups {
  if (story.narrative_groups) return story.narrative_groups;
  return {
    principlist: story.state_pct ?? 0,
    reformist: story.independent_pct ?? 0,
    moderate_diaspora: story.diaspora_pct ?? 0,
    radical_diaspora: 0,
  };
}

export function sidePercentages(story: StoryBrief): { inside: number; outside: number } {
  if (story.inside_border_pct != null && story.outside_border_pct != null) {
    return { inside: story.inside_border_pct, outside: story.outside_border_pct };
  }
  const g = narrativeGroupsFrom(story);
  return {
    inside: g.principlist + g.reformist,
    outside: g.moderate_diaspora + g.radical_diaspora,
  };
}
