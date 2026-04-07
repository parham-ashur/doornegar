import { setRequestLocale } from "next-intl/server";
import { EyeOff } from "lucide-react";
import StoryCard from "@/components/story/StoryCard";
import { getBlindspotStories } from "@/lib/api";
import type { StoryBrief } from "@/lib/types";

export default async function BlindspotsPage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);

  let stories: StoryBrief[] = [];
  try {
    stories = await getBlindspotStories(50);
  } catch {
    // API may not be running
  }

  const stateOnly = stories.filter((s) => s.blindspot_type === "state_only");
  const diasporaOnly = stories.filter((s) => s.blindspot_type === "diaspora_only");

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <EyeOff className="h-6 w-6 text-amber-400" />
          <h1 className="text-2xl font-bold text-white">
            نقاط کور
          </h1>
        </div>
        <p className="mt-2 max-w-xl text-sm text-slate-400">
          خبرهایی که فقط توسط یک طرف پوشش داده شده‌اند. این نقاط کور نشان می‌دهند چه چیزی ممکن است از دید شما پنهان بماند.
        </p>
      </div>

      {stories.length === 0 ? (
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 text-center text-slate-400">
          هنوز نقطه کوری شناسایی نشده است
        </div>
      ) : (
        <div className="space-y-10">
          {/* State-only stories */}
          {stateOnly.length > 0 && (
            <section>
              <div className="mb-4 flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-red-500" />
                <h2 className="text-lg font-semibold text-white">
                  فقط در رسانه‌های حکومتی
                </h2>
                <span className="rounded-full bg-red-500/20 text-red-400 ring-1 ring-red-500/30 px-2 py-0.5 text-xs font-medium">
                  {stateOnly.length}
                </span>
              </div>
              <p className="mb-4 text-xs text-slate-400">
                رسانه‌های برون‌مرزی این خبرها را پوشش نداده‌اند
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
                <div className="h-3 w-3 rounded-full bg-blue-500" />
                <h2 className="text-lg font-semibold text-white">
                  فقط در رسانه‌های برون‌مرزی
                </h2>
                <span className="rounded-full bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/30 px-2 py-0.5 text-xs font-medium">
                  {diasporaOnly.length}
                </span>
              </div>
              <p className="mb-4 text-xs text-slate-400">
                رسانه‌های دولتی و نیمه‌دولتی این خبرها را پوشش نداده‌اند
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
