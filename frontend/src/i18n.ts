import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";

export const locales = ["fa", "en", "fr"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "fa";

// Locales advertised in the language switcher, sitemap, and hreflang
// annotations. All three locales now ship — fr.json was replaced with
// a proper Le Monde-register translation in Phase 1 (commit lands
// alongside this file change), and the methodology page at
// /[locale]/about/ has per-locale content.
//
// Note: per-story translations (story-detail body, narratives, doornama)
// still rely on Phase 2's translation pipeline. Until Phase 2 ships, the
// per-locale story pages render Persian content with an English/French
// UI chrome. Hreflang per-story should remain conservative (canonical
// to /fa/X when no per-story translation exists) — that conditional
// logic lives in `[locale]/stories/[id]/page.tsx` generateMetadata.
export const advertisedLocales: readonly Locale[] = ["fa", "en", "fr"] as const;

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;

  // Validate locale, fall back to default if invalid
  if (!locale || !locales.includes(locale as Locale)) {
    locale = defaultLocale;
  }

  return {
    locale,
    messages: (await import(`./messages/${locale}.json`)).default,
  };
});
