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
// 5 min was contributing ~30% of Fluid Active CPU even at low traffic
// (homepage is the most-visited page). 10 min ISR halves regens; the
// homepage data (trending stories, blindspots, weekly digest) only
// shifts on the 6-hourly cron, so a 10-min freshness window doesn't
// affect what readers see.
export const revalidate = 600;

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  return <HomeBody locale={locale} />;
}
