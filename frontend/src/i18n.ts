import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";

export const locales = ["fa", "en", "fr"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "fa";

// Locales advertised in the language switcher and sitemap. 'fr' is registered
// in `locales` above so /fr/* routes don't 404, but its messages file is
// currently an English placeholder. Phase 1 of the EN+FR rollout replaces
// fr.json with proper Le Monde-register French and adds 'fr' to this list.
export const advertisedLocales: readonly Locale[] = ["fa", "en"] as const;

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
