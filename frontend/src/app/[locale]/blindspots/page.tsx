import { getTranslations, setRequestLocale } from "next-intl/server";
import { AlertTriangle, EyeOff } from "lucide-react";
import StoryCard from "@/components/story/StoryCard";
import { getBlindspotStories } from "@/lib/api";
import type { StoryBrief } from "@/lib/types";

export default async function BlindspotsPage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  const t = await getTranslations();

  let stories: StoryBrief[] = [];
  try {
    stories = await getBlindspotStories(50);
  } catch {
    // API may not be running
  }

  const stateOnly = stories.filter((s) => s.blindspot_type === "state_only");
  const diasporaOnly = stories.filter((s) => s.blindspot_type === "diaspora_only");

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <EyeOff className="h-6 w-6 text-amber-600" />
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {t("nav.blindspots")}
          </h1>
        </div>
        <p className="mt-2 max-w-xl text-sm text-slate-500 dark:text-slate-400">
          {locale === "fa"
            ? "خبرهایی که فقط توسط یک طرف پوشش داده شده‌اند. این نقاط کور نشان می‌دهند چه چیزی ممکن است از دید شما پنهان بماند."
            : "Stories covered by only one side. These blind spots reveal what you might be missing depending on which media you follow."}
        </p>
      </div>

      {stories.length === 0 ? (
        <div className="card text-center text-slate-500 dark:text-slate-400">
          {locale === "fa"
            ? "هنوز نقطه کوری شناسایی نشده است"
            : "No blind spots detected yet"}
        </div>
      ) : (
        <div className="space-y-10">
          {/* State-only stories */}
          {stateOnly.length > 0 && (
            <section>
              <div className="mb-4 flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-state" />
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                  {t("story.state_only")}
                </h2>
                <span className="rounded-full bg-state-light px-2 py-0.5 text-xs font-medium text-state-dark dark:bg-red-900/30 dark:text-red-300">
                  {stateOnly.length}
                </span>
              </div>
              <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
                {locale === "fa"
                  ? "رسانه‌های برون‌مرزی این خبرها را پوشش نداده‌اند"
                  : "Diaspora and independent media did not cover these stories"}
              </p>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {stateOnly.map((story) => (
                  <StoryCard key={story.id} story={story} />
                ))}
              </div>
            </section>
          )}

          {/* Diaspora-only stories */}
          {diasporaOnly.length > 0 && (
            <section>
              <div className="mb-4 flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-diaspora" />
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                  {t("story.diaspora_only")}
                </h2>
                <span className="rounded-full bg-diaspora-light px-2 py-0.5 text-xs font-medium text-diaspora-dark dark:bg-blue-900/30 dark:text-blue-300">
                  {diasporaOnly.length}
                </span>
              </div>
              <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
                {locale === "fa"
                  ? "رسانه‌های دولتی و نیمه‌دولتی این خبرها را پوشش نداده‌اند"
                  : "State and semi-state media did not cover these stories"}
              </p>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {diasporaOnly.map((story) => (
                  <StoryCard key={story.id} story={story} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
