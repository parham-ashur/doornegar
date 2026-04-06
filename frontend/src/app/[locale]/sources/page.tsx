import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { Radio, Shield, MapPin } from "lucide-react";
import SourceBadge from "@/components/source/SourceBadge";
import { getSources } from "@/lib/api";
import type { Source, StateAlignment } from "@/lib/types";

export default async function SourcesPage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  const t = await getTranslations();

  let sources: Source[] = [];
  try {
    const data = await getSources();
    sources = data.sources;
  } catch {
    // API may not be running
  }

  // Group by state alignment
  const groups: Record<string, Source[]> = {
    state: [],
    semi_state: [],
    independent: [],
    diaspora: [],
  };
  sources.forEach((s) => {
    if (groups[s.state_alignment]) {
      groups[s.state_alignment].push(s);
    }
  });

  const groupLabels: Record<string, { en: string; fa: string; color: string }> = {
    state: { en: "State Media", fa: "رسانه‌های دولتی", color: "border-state" },
    semi_state: { en: "Semi-State Media", fa: "رسانه‌های نیمه‌دولتی", color: "border-semi-state" },
    independent: { en: "Independent Media", fa: "رسانه‌های مستقل", color: "border-independent" },
    diaspora: { en: "Diaspora Media", fa: "رسانه‌های برون‌مرزی", color: "border-diaspora" },
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <Radio className="h-6 w-6 text-diaspora" />
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {t("nav.sources")}
          </h1>
        </div>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {sources.length > 0
            ? locale === "fa"
              ? `${sources.length} رسانه تحت نظارت`
              : `${sources.length} sources monitored`
            : ""}
        </p>
      </div>

      {/* Spectrum visualization */}
      <div className="mb-10 overflow-x-auto">
        <div className="flex min-w-[600px] items-end gap-0">
          {["state", "semi_state", "independent", "diaspora"].map((alignment) => (
            <div
              key={alignment}
              className="flex-1 text-center"
            >
              <div className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                {groupLabels[alignment][locale === "fa" ? "fa" : "en"]}
              </div>
              <div className="flex flex-wrap justify-center gap-1.5 rounded-lg border-t-4 bg-slate-50 p-3 dark:bg-slate-900"
                style={{
                  borderColor:
                    alignment === "state" ? "#dc2626" :
                    alignment === "semi_state" ? "#d97706" :
                    alignment === "independent" ? "#059669" : "#2563eb",
                }}
              >
                {groups[alignment].map((source) => (
                  <Link
                    key={source.slug}
                    href={`/${locale}/sources/${source.slug}`}
                    className="rounded-md bg-white px-2 py-1 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    {locale === "fa" ? source.name_fa : source.name_en}
                    {source.irgc_affiliated && (
                      <Shield className="ms-1 inline h-3 w-3 text-red-500" />
                    )}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Source cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map((source) => (
          <Link key={source.slug} href={`/${locale}/sources/${source.slug}`} className="card group">
            <div className="flex items-start justify-between">
              <h3 className="text-base font-semibold text-slate-900 group-hover:text-diaspora dark:text-white">
                {locale === "fa" ? source.name_fa : source.name_en}
              </h3>
              <SourceBadge
                alignment={source.state_alignment}
                irgcAffiliated={source.irgc_affiliated}
              />
            </div>

            <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
              {locale === "fa" ? source.description_fa : source.description_en}
            </p>

            <div className="mt-3 flex items-center gap-3 text-[11px] text-slate-400 dark:text-slate-500">
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {source.production_location === "inside_iran"
                  ? t("source.inside_iran")
                  : t("source.outside_iran")}
              </span>
              {source.factional_alignment && (
                <span>{source.factional_alignment}</span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
