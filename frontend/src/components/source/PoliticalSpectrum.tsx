"use client";

import { useState } from "react";
import type { Source } from "@/lib/types";
import {
  GROUP_COLORS,
  GROUP_LABELS_FA,
  NARRATIVE_GROUP_ORDER,
  narrativeGroupOfSource,
} from "@/lib/narrativeGroups";

// Derive a favicon URL from a source's website when the DB has no
// logo_url. Google's S2 service caches favicons for every domain we
// track (including Iranian-hosted sites) at sz=64 which is sharper
// than the bare `/favicon.ico` at our 32×32 render size. Cheap and
// requires no DB backfill — frontend-only fallback.
function faviconFromWebsite(websiteUrl: string | null | undefined): string | null {
  if (!websiteUrl) return null;
  try {
    const host = new URL(websiteUrl).hostname.replace(/^www\./, "");
    return `https://www.google.com/s2/favicons?domain=${host}&sz=64`;
  } catch {
    return null;
  }
}

function SourceBadge({
  source,
  borderColor,
}: {
  source: Source;
  borderColor: string;
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const resolved = source.logo_url || faviconFromWebsite(source.website_url);
  const showImage = resolved && !imgFailed;

  if (showImage) {
    return (
      <div className={`w-8 h-8 rounded-full overflow-hidden bg-white dark:bg-slate-800 border-2 ${borderColor} shadow-sm transition-transform group-hover:scale-125`}>
        <img
          src={resolved}
          alt={source.name_fa || ""}
          className="w-full h-full object-cover"
          loading="lazy"
          onError={() => setImgFailed(true)}
        />
      </div>
    );
  }

  return (
    <div className={`w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-[13px] font-bold text-slate-500 dark:text-slate-300 border-2 ${borderColor} shadow-sm transition-transform group-hover:scale-125`}>
      {(source.name_fa || source.name_en || "?").charAt(0)}
    </div>
  );
}

function getSpectrumScore(source: Source): number {
  const align = source.state_alignment;
  const irgc = source.irgc_affiliated;

  if (align === "state") return irgc ? 1 : 2;
  if (align === "semi_state") return 2;
  if (align === "independent") return 3;
  if (align === "diaspora") {
    const slug = source.slug || "";
    if (slug.includes("bbc") || slug.includes("dw") || slug.includes("euronews") || slug.includes("rfi") || slug.includes("zamaneh")) return 4;
    return 5;
  }
  return 3;
}

interface Props {
  sources: Source[];
  sourceNeutrality: Record<string, number> | null;
}

export default function PoliticalSpectrum({ sources, sourceNeutrality }: Props) {
  const columns: Record<number, { source: Source; neutrality: number }[]> = {};
  for (const s of sources) {
    const score = getSpectrumScore(s);
    const n = sourceNeutrality?.[s.slug] ?? 0;
    if (!columns[score]) columns[score] = [];
    columns[score].push({ source: s, neutrality: n });
  }

  for (const col of Object.values(columns)) {
    col.sort((a, b) => b.neutrality - a.neutrality);
  }

  const colOrder = [1, 2, 3, 4, 5];
  const hasNeutrality = sourceNeutrality && Object.values(sourceNeutrality).some(v => v !== 0);

  // Score 1 = most conservative (right in RTL), score 5 = most opposition (left in RTL)
  // We use a LTR container with explicit positioning:
  // Left side = opposition, Right side = conservative (matching RTL reading)
  // So we INVERT: score 1 → right (high %), score 5 → left (low %)
  const getX = (score: number) => {
    // score 1 → 82%, score 5 → 18% (conservative on right, opposition on left)
    return 85 - ((score - 1) / 4) * 70;
  };

  return (
    <div>
      {/* Chart — NO dir=rtl, we position manually. Height grows with
          source count but stays tight at low counts so small stories
          don't show empty space above/below the logos. */}
      <div className="relative mx-6" style={{ height: Math.max(200, sources.length * 30) }}>

        {/* X-axis gradient line */}
        <div className="absolute z-0 flex items-center" style={{ top: "50%", transform: "translateY(-50%)", left: "8%", right: "8%" }}>
          <div className="flex-1 h-[2px]" style={{
            background: "linear-gradient(to right, #ea580c, #f97316, #94a3b8, #2563eb, #1e3a5f)",
          }} />
        </div>

        {/* X-axis labels — conservative on right, opposition on left */}
        <div className="absolute text-[13px] font-medium text-[#1e3a5f] dark:text-blue-300 z-10" style={{ top: "50%", right: 0, transform: "translateY(8px)" }}>درون‌مرزی</div>
        <div className="absolute text-[13px] font-medium text-[#ea580c] dark:text-orange-400 z-10" style={{ top: "50%", left: 0, transform: "translateY(8px)" }}>برون‌مرزی</div>

        {/* Y-axis labels */}
        <div className="absolute z-0 text-[13px] text-slate-400 dark:text-slate-500" style={{ right: 0, top: 2 }}>بی‌طرف</div>
        <div className="absolute z-0 text-[13px] text-slate-400 dark:text-slate-500" style={{ right: 0, bottom: 2 }}>یک‌جانبه</div>

        {/* Column separators */}
        {[1, 2, 3, 4].map(i => (
          <div
            key={i}
            className="absolute w-px bg-slate-200 dark:bg-slate-700/30 z-0"
            style={{ left: `${10 + (i / 5) * 80}%`, top: "8%", bottom: "8%" }}
          />
        ))}

        {/* Source logos — with collision avoidance */}
        <div className="absolute inset-0 z-10">
          {(() => {
            // Collect all logos with positions
            const allLogos: { source: Source; x: number; y: number; neutrality: number; borderColor: string }[] = [];

            for (const score of colOrder) {
              const items = columns[score] || [];
              if (items.length === 0) continue;
              const colCenter = getX(score);

              items.forEach(({ source: s, neutrality: n }, idx) => {
                let yPct: number;
                if (hasNeutrality) {
                  const clampedN = Math.max(-1, Math.min(1, n));
                  // Use 8% → 92% vertical range (was 15% → 85%) so
                  // logos hug the top/bottom edges and the chart box
                  // doesn't show wide empty bands.
                  yPct = 8 + (1 - (clampedN + 1) / 2) * 84;
                } else {
                  if (items.length === 1) {
                    yPct = 50;
                  } else {
                    yPct = 12 + (idx / (items.length - 1)) * 76;
                  }
                }

                const borderColor = hasNeutrality
                  ? n > 0.2 ? "border-emerald-500 dark:border-emerald-400"
                    : n < -0.3 ? "border-red-500 dark:border-red-400"
                    : "border-orange-400 dark:border-orange-500"
                  : "border-slate-200 dark:border-slate-700";

                allLogos.push({ source: s, x: colCenter, y: yPct, neutrality: n, borderColor });
              });
            }

            // Nudge overlapping logos (5 passes)
            for (let pass = 0; pass < 5; pass++) {
              for (let i = 0; i < allLogos.length; i++) {
                for (let j = i + 1; j < allLogos.length; j++) {
                  const dx = allLogos[i].x - allLogos[j].x;
                  const dy = allLogos[i].y - allLogos[j].y;
                  const dist = Math.sqrt(dx * dx + dy * dy);
                  if (dist < 8) {
                    const push = (8 - dist) / 2 + 1;
                    allLogos[i].y = Math.max(5, allLogos[i].y - push);
                    allLogos[j].y = Math.min(95, allLogos[j].y + push);
                  }
                }
              }
            }

            return allLogos.map(({ source: s, x, y, neutrality: n, borderColor }) => (

              <div
                key={s.slug}
                className="absolute group"
                style={{
                  left: `${x}%`,
                  top: `${y}%`,
                  transform: "translate(-50%, -50%)",
                }}
              >
                <SourceBadge source={s} borderColor={borderColor} />
                <div className="hidden md:block absolute -bottom-5 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 dark:bg-white text-white dark:text-slate-900 text-[13px] px-2 py-0.5 whitespace-nowrap pointer-events-none z-20 shadow-lg">
                  {s.name_fa || s.name_en}
                  {hasNeutrality && n !== 0 && <span className="mr-1 font-mono text-[13px]">({n > 0 ? "+" : ""}{n.toFixed(1)})</span>}
                </div>
              </div>
            ));
          })()}
        </div>
      </div>

      {/* Caption */}
      <p dir="rtl" className="text-[13px] text-slate-400 dark:text-slate-500 mt-3 leading-5 mx-6">
        محور افقی جایگاه سیاسی رسانه را نشان می‌دهد — از رسانه‌های درون‌مرزی (راست) تا رسانه‌های برون‌مرزی (چپ).
        {hasNeutrality
          ? <> محور عمودی میزان بی‌طرفی پوشش <strong className="text-slate-600 dark:text-slate-300">فقط در همین خبر</strong> را نشان می‌دهد — رسانه‌هایی که بالاتر قرار دارند پوشش متوازن‌تری داشته‌اند.</>
          : <> محور عمودی پس از تحلیل بعدی، میزان بی‌طرفی هر رسانه <strong className="text-slate-600 dark:text-slate-300">فقط در همین خبر</strong> را نشان خواهد داد.</>}
      </p>

      {/* Subgroup legend — shows which sources fall in each of the 4
          narrative subgroups. Transparency for readers about how we
          classify sources. Computed locally from source metadata so
          this stays in sync with the bar/pie-chart percentages above. */}
      {sources.length > 0 && (
        <div dir="rtl" className="mt-4 mx-6 border-t border-slate-200 dark:border-slate-800 pt-3 space-y-2">
          <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            دسته‌بندی زیرگروه‌ها
          </p>
          {NARRATIVE_GROUP_ORDER.map((group) => {
            const members = sources.filter((s) => narrativeGroupOfSource(s) === group);
            if (members.length === 0) return null;
            return (
              <div key={group} className="flex items-start gap-2 text-[13px]">
                <span
                  className="inline-block w-2 h-2 mt-1.5 shrink-0"
                  style={{ backgroundColor: GROUP_COLORS[group] }}
                />
                <span
                  className="font-bold shrink-0"
                  style={{ color: GROUP_COLORS[group] }}
                >
                  {GROUP_LABELS_FA[group]}:
                </span>
                <span className="text-slate-600 dark:text-slate-400 leading-6">
                  {members.map((m) => m.name_fa || m.name_en || m.slug).join("، ")}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
