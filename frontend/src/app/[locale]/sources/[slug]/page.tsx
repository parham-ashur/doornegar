import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { ArrowLeft, ExternalLink, MapPin, Shield } from "lucide-react";
import SourceBadge from "@/components/source/SourceBadge";
import { getSource } from "@/lib/api";

export default async function SourceProfilePage({
  params: { locale, slug },
}: {
  params: { locale: string; slug: string };
}) {
  setRequestLocale(locale);

  let source;
  try {
    source = await getSource(slug);
  } catch {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-4 py-16 text-center">
        <p className="text-slate-400">خطا در بارگذاری اطلاعات رسانه</p>
      </div>
    );
  }

  const alignmentLabels: Record<string, string> = {
    state: "محافظه‌کار",
    semi_state: "نیمه‌دولتی",
    independent: "مستقل",
    diaspora: "اپوزیسیون",
  };

  const factionalLabels: Record<string, string> = {
    hardline: "اصولگرای تندرو",
    principlist: "اصولگرا",
    reformist: "اصلاح‌طلب",
    moderate: "میانه‌رو",
    opposition: "اپوزیسیون",
    monarchist: "سلطنت‌طلب",
    left: "چپ",
  };

  return (
    <div dir="rtl" className="mx-auto max-w-3xl px-4 py-8">
      <Link
        href={`/${locale}/sources`}
        className="mb-6 inline-flex items-center gap-1 text-sm text-slate-400 hover:text-blue-400"
      >
        <ArrowLeft className="h-4 w-4 rotate-180" />
        بازگشت
      </Link>

      {/* Header */}
      <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">
              {source.name_fa}
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              {source.name_en}
            </p>
          </div>
          <SourceBadge
            alignment={source.state_alignment}
            irgcAffiliated={source.irgc_affiliated}
          />
        </div>

        {source.description_fa && (
          <p className="mt-4 text-sm text-slate-400">
            {source.description_fa}
          </p>
        )}

        <a
          href={source.website_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-1 text-sm text-blue-400 hover:underline"
        >
          {source.website_url}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      {/* Metadata grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-400">
            طبقه‌بندی
          </h3>
          <dl className="space-y-2.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-400">نوع رسانه</dt>
              <dd className="font-medium text-white">
                {alignmentLabels[source.state_alignment] || source.state_alignment}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">مکان</dt>
              <dd className="flex items-center gap-1 font-medium text-white">
                <MapPin className="h-3.5 w-3.5" />
                {source.production_location === "inside_iran"
                  ? "داخل ایران"
                  : "خارج از ایران"}
              </dd>
            </div>
            {source.factional_alignment && (
              <div className="flex justify-between">
                <dt className="text-slate-400">جناح سیاسی</dt>
                <dd className="font-medium text-white">
                  {factionalLabels[source.factional_alignment] || source.factional_alignment}
                </dd>
              </div>
            )}
            {source.irgc_affiliated && (
              <div className="flex justify-between">
                <dt className="text-slate-400">وابستگی</dt>
                <dd className="flex items-center gap-1 font-medium text-red-400">
                  <Shield className="h-3.5 w-3.5" />
                  وابسته به سپاه
                </dd>
              </div>
            )}
          </dl>
        </div>

        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-400">
            اطلاعات فنی
          </h3>
          <dl className="space-y-2.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-400">زبان</dt>
              <dd className="font-medium text-white">
                {source.language === "fa"
                  ? "فارسی"
                  : source.language === "en"
                  ? "انگلیسی"
                  : "دوزبانه"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">فید RSS</dt>
              <dd className="font-medium text-white">
                {source.rss_urls.length > 0
                  ? source.rss_urls.length
                  : "اسکرپ"}
              </dd>
            </div>
            {source.credibility_score != null && (
              <div className="flex justify-between">
                <dt className="text-slate-400">اعتبار</dt>
                <dd className="font-medium text-white">
                  {Math.round(source.credibility_score * 100)}%
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>
    </div>
  );
}
