import { setRequestLocale } from "next-intl/server";
import { FeedbackProvider } from "@/components/home/FeedbackOverlay";
import HomeBody from "@/components/home/HomeBody";

// /rate renders the same homepage as `/`, but with feedback overlays
// on every story card and `?feedback=1` appended to story links so
// the story page enters feedback mode too.
//
// Shorter ISR window than `/` because rater traffic is small and we
// want their actions to surface quickly when reviewing.
export const revalidate = 60;

export default async function RatePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <FeedbackProvider>
      <HomeBody locale={locale} feedbackMode />
    </FeedbackProvider>
  );
}
