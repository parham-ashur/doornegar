import { getTranslations, setRequestLocale } from "next-intl/server";
import Link from "next/link";
import { ArrowLeft, ArrowRight, ExternalLink, MapPin, Radio, Shield } from "lucide-react";
import SourceBadge from "@/components/source/SourceBadge";
import { getSource } from "@/lib/api";

export default async function SourceProfilePage({
  params: { locale, slug },
}: {
  params: { locale: string; slug: string };
}) {
  setRequestLocale(locale);
  const t = await getTranslations();
  const isRtl = locale === "fa";
  const BackArrow = isRtl ? ArrowRight : ArrowLeft;

  let source;
  try {
    source = await getSource(slug);
  } catch {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 text-center">
        <p className="text-slate-500">{t("common.error")}</p>
      </div>
    );
  }

  const name = locale === "fa" ? source.name_fa : source.name_en;
  const description = locale === "fa" ? source.description_fa : source.description_en;

  const factionalLabels: Record<string, { en: string; fa: string }> = {
    hardline: { en: "Hardline", fa: "اصولگرای تندرو" },
    principlist: { en: "Principlist", fa: "اصولگرا" },
    reformist: { en: "Reformist", fa: "اصلاح‌طلب" },
    moderate: { en: "Moderate", fa: "میانه‌رو" },
    opposition: { en: "Opposition", fa: "اپوزیسیون" },
    monarchist: { en: "Monarchist", fa: "سلطنت‌طلب" },
    left: { en: "Left", fa: "چپ" },
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Link
        href={`/${locale}/sources`}
        className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-diaspora"
      >
        <BackArrow className="h-4 w-4" />
        {t("common.back")}
      </Link>

      {/* Header */}
      <div className="card mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
              {name}
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {/* Show the other language name */}
              {locale === "fa" ? source.name_en : source.name_fa}
            </p>
          </div>
          <SourceBadge
            alignment={source.state_alignment}
            irgcAffiliated={source.irgc_affiliated}
          />
        </div>

        {description && (
          <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
            {description}
          </p>
        )}

        <a
          href={source.website_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-1 text-sm text-diaspora hover:underline"
        >
          {source.website_url}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      {/* Metadata grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-slate-500 dark:text-slate-400">
            {locale === "fa" ? "طبقه‌بندی" : "Classification"}
          </h3>
          <dl className="space-y-2.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-500 dark:text-slate-400">
                {locale === "fa" ? "نوع رسانه" : "Media Type"}
              </dt>
              <dd className="font-medium text-slate-900 dark:text-white">
                {t(`source.${source.state_alignment}`)}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500 dark:text-slate-400">
                {locale === "fa" ? "مکان" : "Location"}
              </dt>
              <dd className="flex items-center gap-1 font-medium text-slate-900 dark:text-white">
                <MapPin className="h-3.5 w-3.5" />
                {source.production_location === "inside_iran"
                  ? t("source.inside_iran")
                  : t("source.outside_iran")}
              </dd>
            </div>
            {source.factional_alignment && (
              <div className="flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">
                  {t("source.factional")}
                </dt>
                <dd className="font-medium text-slate-900 dark:text-white">
                  {factionalLabels[source.factional_alignment]?.[
                    locale === "fa" ? "fa" : "en"
                  ] || source.factional_alignment}
                </dd>
              </div>
            )}
            {source.irgc_affiliated && (
              <div className="flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">
                  {locale === "fa" ? "وابستگی" : "Affiliation"}
                </dt>
                <dd className="flex items-center gap-1 font-medium text-red-600 dark:text-red-400">
                  <Shield className="h-3.5 w-3.5" />
                  {t("source.irgc")}
                </dd>
              </div>
            )}
          </dl>
        </div>

        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-slate-500 dark:text-slate-400">
            {locale === "fa" ? "اطلاعات فنی" : "Technical Info"}
          </h3>
          <dl className="space-y-2.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-500 dark:text-slate-400">
                {locale === "fa" ? "زبان" : "Language"}
              </dt>
              <dd className="font-medium text-slate-900 dark:text-white">
                {source.language === "fa"
                  ? "فارسی"
                  : source.language === "en"
                  ? "English"
                  : "Both"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500 dark:text-slate-400">
                {locale === "fa" ? "فید RSS" : "RSS Feeds"}
              </dt>
              <dd className="font-medium text-slate-900 dark:text-white">
                {source.rss_urls.length > 0
                  ? source.rss_urls.length
                  : locale === "fa"
                  ? "اسکرپ"
                  : "Scraping"}
              </dd>
            </div>
            {source.credibility_score != null && (
              <div className="flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">
                  {t("source.credibility")}
                </dt>
                <dd className="font-medium text-slate-900 dark:text-white">
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
