import { setRequestLocale } from "next-intl/server";
import HomeBody from "@/components/home/HomeBody";

// Regenerate the rendered HTML every 5 minutes. Inside that window
// every visitor gets a ~0.5s cache hit at the Vercel edge instead of
// the 10–15s full SSR.
//
// Read mode renders <HomeBody /> with no feedback overlay; /rate
// renders the same component with feedbackMode and a FeedbackProvider
// wrapper.
//
// Bumped 600 → 900 (15 min) on 2026-05-06 as Vercel headroom for the
// upcoming /en/ + /fr/ rollout. Per-locale ISR caches multiply
// page-regen work; this bump pre-pays for the multiplier. Underlying
// data shifts only on the 2×/day cron (0 3,15 UTC), so 30-min freshness
// still doesn't affect what readers see — and halves homepage regen
// fan-out (Lever 1 egress cut, 2026-05-31).
export const revalidate = 1800;

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  return <HomeBody locale={locale} />;
}
