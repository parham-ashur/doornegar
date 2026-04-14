import { setRequestLocale } from "next-intl/server";
import StoriesCarousel from "@/components/stories/StoriesCarousel";
import { buildStoriesSlots } from "@/lib/stories-data";

export const dynamic = "force-dynamic";

export default async function StoriesBetaPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const dir = locale === "fa" ? "rtl" : "ltr";

  const slots = await buildStoriesSlots();

  return <StoriesCarousel slots={slots} dir={dir} />;
}
