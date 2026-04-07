"use client";

import { Check } from "lucide-react";
import type { StoryArticleWithBias } from "@/lib/types";

interface FramingTableProps {
  articles: StoryArticleWithBias[];
}

const framingLabels: Record<string, string> = {
  conflict: "تعارض",
  human_interest: "داستان انسانی",
  economic_impact: "تأثیر اقتصادی",
  morality: "اخلاق",
  responsibility: "مسئولیت",
  security: "امنیت",
  victimization: "قربانی‌سازی",
  resistance: "مقاومت",
  sovereignty: "حاکمیت",
  western_interference: "دخالت غرب",
  human_rights: "حقوق بشر",
  reform: "اصلاحات",
  stability: "ثبات",
  national_pride: "غرور ملی",
  corruption: "فساد",
};

export default function FramingTable({ articles }: FramingTableProps) {
  const allLabels = new Set<string>();
  articles.forEach((a) => {
    a.bias_scores?.forEach((bs) => {
      bs.framing_labels?.forEach((l) => allLabels.add(l));
    });
  });

  const labels = Array.from(allLabels).sort();
  if (labels.length === 0) return null;

  return (
    <div className="overflow-x-auto" dir="rtl">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/[0.06]">
            <th className="pb-2 pe-4 text-start font-medium text-slate-400">
              چارچوب‌بندی
            </th>
            {articles.map((article) => (
              <th
                key={article.id}
                className="pb-2 px-2 text-center font-medium text-slate-400"
              >
                <span className="line-clamp-1">
                  {article.source_name_fa}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((label) => (
            <tr
              key={label}
              className="border-b border-white/[0.04]"
            >
              <td className="py-2 pe-4 text-slate-300">
                {framingLabels[label] || label}
              </td>
              {articles.map((article) => {
                const hasLabel = article.bias_scores?.some((bs) =>
                  bs.framing_labels?.includes(label)
                );
                return (
                  <td key={article.id} className="py-2 px-2 text-center">
                    {hasLabel && (
                      <Check className="mx-auto h-4 w-4 text-emerald-400" />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
