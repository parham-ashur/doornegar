import { setRequestLocale } from "next-intl/server";
import HomeBody from "@/components/home/HomeBody";

// Regenerate the rendered HTML every 5 minutes. Inside that window
// every visitor gets a ~0.5s cache hit at the Vercel edge instead of
// the 10–15s full SSR.
//
// Read mode renders <HomeBody /> with no feedback overlay; /rate
// renders the same component with feedbackMode and a FeedbackProvider
// wrapper.
export const revalidate = 300;

export default async function HomePage({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  return <HomeBody locale={locale} />;
}
