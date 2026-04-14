"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { MapPin, Shield, Check } from "lucide-react";
import SourceBadge from "@/components/source/SourceBadge";
import SourceComparison from "@/components/source/SourceComparison";
import type { Source } from "@/lib/types";

interface Props {
  sources: Source[];
  locale: string;
}

export default function SourcesListWithCompare({ sources, locale }: Props) {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = useCallback(
    (slug: string) => {
      setSelected((prev) => {
        if (prev.includes(slug)) return prev.filter((s) => s !== slug);
        if (prev.length >= 2) return [prev[1], slug];
        return [...prev, slug];
      });
    },
    [],
  );

  const clearSelection = useCallback(() => setSelected([]), []);

  const sourceA =
    selected.length === 2
      ? sources.find((s) => s.slug === selected[0]) ?? null
      : null;
  const sourceB =
    selected.length === 2
      ? sources.find((s) => s.slug === selected[1]) ?? null
      : null;

  return (
    <>
      {/* Comparison panel */}
      {sourceA && sourceB && (
        <SourceComparison
          sourceA={sourceA}
          sourceB={sourceB}
          onClose={clearSelection}
        />
      )}

      {/* Hint when 1 selected */}
      {selected.length === 1 && (
        <div className="mb-4 text-[12px] text-slate-400 border border-dashed border-slate-700 px-3 py-2">
          یک رسانه دیگر برای مقایسه انتخاب کنید
        </div>
      )}

      {/* Source cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map((source) => {
          const isSelected = selected.includes(source.slug);
          return (
            <div
              key={source.slug}
              className={`relative bg-slate-900/80 ring-1 rounded-2xl p-5 group transition-colors ${
                isSelected
                  ? "ring-blue-500"
                  : "ring-white/[0.06] hover:ring-white/10"
              }`}
            >
              {/* Compare toggle */}
              <button
                onClick={() => toggle(source.slug)}
                className={`absolute top-3 left-3 flex items-center gap-1 text-[10px] px-2 py-1 transition-colors ${
                  isSelected
                    ? "bg-blue-600 text-white"
                    : "bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
                }`}
              >
                {isSelected && <Check className="h-3 w-3" />}
                مقایسه
              </button>

              <Link
                href={`/${locale}/sources/${source.slug}`}
                className="block"
              >
                <div className="flex items-start justify-between">
                  <h3 className="text-base font-semibold text-white group-hover:text-blue-400">
                    {source.name_fa}
                  </h3>
                  <SourceBadge
                    alignment={source.state_alignment}
                    irgcAffiliated={source.irgc_affiliated}
                  />
                </div>

                <p className="mt-2 line-clamp-2 text-xs text-slate-400">
                  {source.description_fa}
                </p>

                <div className="mt-3 flex items-center gap-3 text-[11px] text-slate-500">
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3 w-3" />
                    {source.production_location === "inside_iran"
                      ? "داخل ایران"
                      : "خارج از ایران"}
                  </span>
                  {source.factional_alignment && (
                    <span>{source.factional_alignment}</span>
                  )}
                </div>
              </Link>
            </div>
          );
        })}
      </div>
    </>
  );
}
