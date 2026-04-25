import { setRequestLocale } from "next-intl/server";
import MobileStoriesExperience from "@/components/story/mobile/MobileStoriesExperience";
import { MOCK_SLOTS } from "@/components/story/mobile/mocks";

export const dynamic = "force-static";

export default function StoriesCarouselLab({
  params: { locale },
}: {
  params: { locale: string };
}) {
  setRequestLocale(locale);
  return <MobileStoriesExperience slots={MOCK_SLOTS} isRtl={locale === "fa"} />;
}
