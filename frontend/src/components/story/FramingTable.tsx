"use client";

import { useLocale, useTranslations } from "next-intl";
import { Check } from "lucide-react";
import type { StoryArticleWithBias } from "@/lib/types";

interface FramingTableProps {
  articles: StoryArticleWithBias[];
}

const framingLabelTranslations: Record<string, { en: string; fa: string }> = {
  conflict: { en: "Conflict", fa: "تعارض" },
  human_interest: { en: "Human Interest", fa: "داستان انسانی" },
  economic_impact: { en: "Economic Impact", fa: "تأثیر اقتصادی" },
  morality: { en: "Morality", fa: "اخلاق" },
  responsibility: { en: "Responsibility", fa: "مسئولیت" },
  security: { en: "Security", fa: "امنیت" },
  victimization: { en: "Victimization", fa: "قربانی‌سازی" },
  resistance: { en: "Resistance", fa: "مقاومت" },
  sovereignty: { en: "Sovereignty", fa: "حاکمیت" },
  western_interference: { en: "Western Interference", fa: "دخالت غرب" },
  human_rights: { en: "Human Rights", fa: "حقوق بشر" },
  reform: { en: "Reform", fa: "اصلاحات" },
  stability: { en: "Stability", fa: "ثبات" },
  national_pride: { en: "National Pride", fa: "غرور ملی" },
  corruption: { en: "Corruption", fa: "فساد" },
};

export default function FramingTable({ articles }: FramingTableProps) {
  const locale = useLocale();
  const t = useTranslations();

  // Collect all unique framing labels across articles
  const allLabels = new Set<string>();
  articles.forEach((a) => {
    a.bias_scores?.forEach((bs) => {
      bs.framing_labels?.forEach((l) => allLabels.add(l));
    });
  });

  const labels = Array.from(allLabels).sort();
  if (labels.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-700">
            <th className="pb-2 pe-4 text-start font-medium text-slate-500 dark:text-slate-400">
              {t("bias.framing")}
            </th>
            {articles.map((article) => (
              <th
                key={article.id}
                className="pb-2 px-2 text-center font-medium text-slate-500 dark:text-slate-400"
              >
                <span className="line-clamp-1">
                  {locale === "fa"
                    ? article.source_name_fa
                    : article.source_name_en}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((label) => (
            <tr
              key={label}
              className="border-b border-slate-100 dark:border-slate-800"
            >
              <td className="py-2 pe-4 text-slate-700 dark:text-slate-300">
                {framingLabelTranslations[label]?.[locale === "fa" ? "fa" : "en"] || label}
              </td>
              {articles.map((article) => {
                const hasLabel = article.bias_scores?.some((bs) =>
                  bs.framing_labels?.includes(label)
                );
                return (
                  <td key={article.id} className="py-2 px-2 text-center">
                    {hasLabel && (
                      <Check className="mx-auto h-4 w-4 text-emerald-500" />
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
