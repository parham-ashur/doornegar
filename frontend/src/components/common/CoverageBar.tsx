"use client";

import { Fragment } from "react";
import { cn } from "@/lib/utils";
import {
  GROUP_COLORS,
  GROUP_LABELS_FA,
  GROUPS_BY_SIDE,
  NARRATIVE_GROUP_ORDER,
  SIDE_LABELS_FA,
  narrativeGroupsFrom,
} from "@/lib/narrativeGroups";
import type { NarrativeGroup, NarrativeGroups, StoryBrief } from "@/lib/types";

interface CoverageBarProps {
  /** Either pass a full story (preferred — handles legacy fallback) or the raw groups. */
  story?: StoryBrief;
  groups?: NarrativeGroups;
  height?: "sm" | "md" | "lg";
  /** When true, a row of subgroup labels + percentages appears beneath the bar. */
  showSubgroupLabels?: boolean;
  /** When true, a single "درون‌مرزی X٪ · برون‌مرزی Y٪" summary appears above the bar. */
  showSideTotals?: boolean;
  className?: string;
}

const HEIGHT_CLASS = { sm: "h-1.5", md: "h-2", lg: "h-3" };

export default function CoverageBar({
  story,
  groups,
  height = "md",
  showSubgroupLabels = false,
  showSideTotals = false,
  className,
}: CoverageBarProps) {
  const pct: NarrativeGroups = groups ?? (story ? narrativeGroupsFrom(story) : {
    principlist: 0,
    reformist: 0,
    moderate_diaspora: 0,
    radical_diaspora: 0,
  });

  const total =
    pct.principlist + pct.reformist + pct.moderate_diaspora + pct.radical_diaspora;
  if (total === 0) return null;

  const inside = pct.principlist + pct.reformist;
  const outside = pct.moderate_diaspora + pct.radical_diaspora;

  return (
    <div className={cn("w-full", className)}>
      {showSideTotals && (
        <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2" style={{ backgroundColor: GROUP_COLORS.principlist }} />
            {SIDE_LABELS_FA.inside} {inside}٪
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2" style={{ backgroundColor: GROUP_COLORS.radical_diaspora }} />
            {SIDE_LABELS_FA.outside} {outside}٪
          </span>
        </div>
      )}

      <div
        className={cn(
          "flex w-full overflow-hidden bg-slate-200 dark:bg-slate-800",
          HEIGHT_CLASS[height],
        )}
        role="img"
        aria-label={`درون‌مرزی ${inside}٪ — برون‌مرزی ${outside}٪`}
      >
        {NARRATIVE_GROUP_ORDER.map((group, i) => {
          const width = pct[group];
          if (width === 0) return null;
          // Insert a 2px divider between the inside and outside sides when both
          // are present — makes the 2-side grouping visually obvious.
          const isSideBoundary = i === 2 && inside > 0 && outside > 0;
          return (
            <Fragment key={group}>
              {isSideBoundary && <div className="w-[2px] bg-white dark:bg-slate-950 shrink-0" />}
              <div
                className="transition-all"
                style={{ width: `${width}%`, backgroundColor: GROUP_COLORS[group] }}
              />
            </Fragment>
          );
        })}
      </div>

      {showSubgroupLabels && (
        <div className="mt-2 grid grid-cols-2 gap-x-4 text-[11px]">
          {(["inside", "outside"] as const).map((side) => {
            const sideTotal = side === "inside" ? inside : outside;
            return (
              <div key={side} className="flex flex-col gap-0.5">
                <div className="font-bold text-slate-700 dark:text-slate-300">
                  {SIDE_LABELS_FA[side]}{" "}
                  <span className="font-normal text-slate-400">({sideTotal}٪)</span>
                </div>
                {withinSidePercentages(GROUPS_BY_SIDE[side], pct, sideTotal).map(
                  ([g, withinPct]) => (
                    <div
                      key={g}
                      className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400"
                    >
                      <span
                        className="inline-block h-1.5 w-1.5"
                        style={{ backgroundColor: GROUP_COLORS[g] }}
                      />
                      <span>{GROUP_LABELS_FA[g]}</span>
                      <span className="text-slate-400">{withinPct}٪</span>
                    </div>
                  ),
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Convert per-side subgroup percentages from "share of total story" to
 * "share of this side", so the two numbers read "76%" + "24%" summing to
 * 100 within the side rather than "34%" + "11%" summing to 45.
 *
 * Rounds with largest-remainder so both always sum to exactly 100 (or 0
 * when the side is empty).
 */
function withinSidePercentages(
  groups: NarrativeGroup[],
  pctOfTotal: NarrativeGroups,
  sideTotal: number,
): [NarrativeGroup, number][] {
  if (sideTotal <= 0) {
    return groups.map((g) => [g, 0]);
  }
  const raw = groups.map<[NarrativeGroup, number]>((g) => [
    g,
    (pctOfTotal[g] / sideTotal) * 100,
  ]);
  const floored = raw.map<[NarrativeGroup, number]>(([g, r]) => [g, Math.floor(r)]);
  let deficit = 100 - floored.reduce((s, [, v]) => s + v, 0);
  // Hand out the remaining 1's to groups with the largest fractional remainder.
  const order = raw
    .map(([g, r], i) => ({ g, i, rem: r - Math.floor(r) }))
    .sort((a, b) => b.rem - a.rem || a.i - b.i);
  for (const { i } of order) {
    if (deficit <= 0) break;
    floored[i][1] += 1;
    deficit -= 1;
  }
  return floored;
}
