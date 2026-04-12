import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { Radio, Shield, MapPin } from "lucide-react";
import SourceBadge from "@/components/source/SourceBadge";
import { getSources } from "@/lib/api";
import type { Source } from "@/lib/types";

export default async function SourcesPage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);

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

  const groupLabels: Record<string, { label: string; color: string }> = {
    state: { label: "رسانه‌های محافظه‌کار", color: "#dc2626" },
    semi_state: { label: "رسانه‌های نیمه‌دولتی", color: "#d97706" },
    independent: { label: "رسانه‌های مستقل", color: "#059669" },
    diaspora: { label: "رسانه‌های اپوزیسیون", color: "#2563eb" },
  };

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <Radio className="h-6 w-6 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">
            رسانه‌ها
          </h1>
        </div>
        <p className="mt-1 text-sm text-slate-400">
          {sources.length > 0 ? `${sources.length} رسانه تحت نظارت` : ""}
        </p>
      </div>

      {/* Spectrum visualization */}
      <div className="mb-10 overflow-x-auto">
        <div className="flex min-w-[600px] items-end gap-0">
          {(["state", "semi_state", "independent", "diaspora"] as const).map((alignment) => (
            <div
              key={alignment}
              className="flex-1 text-center"
            >
              <div className="mb-2 text-xs font-medium text-slate-400">
                {groupLabels[alignment].label}
              </div>
              <div
                className="flex flex-wrap justify-center gap-1.5 rounded-lg border-t-4 bg-slate-900/80 p-3"
                style={{ borderColor: groupLabels[alignment].color }}
              >
                {groups[alignment].map((source) => (
                  <Link
                    key={source.slug}
                    href={`/${locale}/sources/${source.slug}`}
                    className="rounded-md bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300 ring-1 ring-white/[0.06] transition-colors hover:bg-slate-700"
                  >
                    {source.name_fa}
                    {source.irgc_affiliated && (
                      <Shield className="ms-1 inline h-3 w-3 text-red-400" />
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
          <Link
            key={source.slug}
            href={`/${locale}/sources/${source.slug}`}
            className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 group transition-colors hover:ring-white/10"
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
        ))}
      </div>
    </div>
  );
}
