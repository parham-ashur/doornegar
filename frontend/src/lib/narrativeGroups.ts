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
 * Mirror of backend `app.services.narrative_groups.narrative_group`.
 * Classifies a Source object into one of the four narrative subgroups
 * based on production_location + factional_alignment + state_alignment.
 */
export function narrativeGroupOfSource(source: {
  production_location?: string | null;
  factional_alignment?: string | null;
  state_alignment?: string | null;
}): NarrativeGroup {
  const inside = source.production_location === "inside_iran";
  const faction = source.factional_alignment || null;
  const state = source.state_alignment || null;
  if (inside) {
    if (faction === "hardline" || faction === "principlist" || state === "state") {
      return "principlist";
    }
    return "reformist";
  }
  if (faction === "opposition" || faction === "monarchist" || faction === "radical") {
    return "radical_diaspora";
  }
  return "moderate_diaspora";
}

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

/**
 * Display-side percentages that always sum to 100 across the 2 sides.
 *
 * Raw `state_pct` / `diaspora_pct` leave an implicit gap for «independent»
 * articles (outlets like etemad-online, zeitoons that are classified
 * outside the 4 political subgroups). Showing «درون‌مرزی 75% · برون‌مرزی 22%»
 * looks misleading — the reader expects 100. Renormalize over just the
 * politically-classified share so the bar always sums correctly.
 *
 * When a story has NO politically-classified articles (pure independent),
 * returns zeros so the caller can choose to hide the ratio entirely.
 */
export function normalizedSidePercentages(
  story: StoryBrief,
): { inside: number; outside: number } {
  const { inside, outside } = sidePercentages(story);
  const total = inside + outside;
  if (total <= 0) return { inside: 0, outside: 0 };
  const n_inside = Math.round((inside / total) * 100);
  return { inside: n_inside, outside: 100 - n_inside };
}

/**
 * Same idea for the 4-subgroup mix — always sums to 100 across
 * (principlist, reformist, moderate_diaspora, radical_diaspora).
 * Rounding leaves one group absorbing the rounding error so the
 * total is exactly 100.
 */
export function normalizedSubgroupPercentages(story: StoryBrief): NarrativeGroups {
  const g = narrativeGroupsFrom(story);
  const total =
    g.principlist + g.reformist + g.moderate_diaspora + g.radical_diaspora;
  if (total <= 0) {
    return {
      principlist: 0,
      reformist: 0,
      moderate_diaspora: 0,
      radical_diaspora: 0,
    };
  }
  const p = Math.round((g.principlist / total) * 100);
  const r = Math.round((g.reformist / total) * 100);
  const m = Math.round((g.moderate_diaspora / total) * 100);
  // Last group absorbs rounding drift so the four sum to exactly 100
  const rad = Math.max(0, 100 - p - r - m);
  return {
    principlist: p,
    reformist: r,
    moderate_diaspora: m,
    radical_diaspora: rad,
  };
}

/**
 * Share of the story's articles that are NOT in any of the 4 political
 * subgroups (independent outlets). Useful to surface separately when
 * non-trivial (≥ 5%) so the reader knows the normalized side-split
 * excludes this bucket.
 */
export function independentShare(story: StoryBrief): number {
  const { inside, outside } = sidePercentages(story);
  const classified = inside + outside;
  return Math.max(0, 100 - classified);
}
