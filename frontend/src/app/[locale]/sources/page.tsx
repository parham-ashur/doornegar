import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { Radio, Shield } from "lucide-react";
import SourcesListWithCompare from "@/components/source/SourcesListWithCompare";
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
    state: { label: "رسانه‌های درون‌مرزی", color: "#dc2626" },
    semi_state: { label: "رسانه‌های نیمه‌دولتی", color: "#d97706" },
    independent: { label: "رسانه‌های مستقل", color: "#059669" },
    diaspora: { label: "رسانه‌های برون‌مرزی", color: "#2563eb" },
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

      {/* Source cards with compare feature */}
      <SourcesListWithCompare sources={sources} locale={locale} />
    </div>
  );
}
