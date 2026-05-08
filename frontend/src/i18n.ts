import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";

export const locales = ["fa", "en", "fr"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "fa";

// Locales advertised in the language switcher, sitemap, and hreflang
// annotations.
//
// 2026-05-08 (Parham): EN + FR HIDDEN from the navbar pending the
// Neon-egress structural fix. The pages still render at /en + /fr
// (so existing inbound links work and search-engine snapshots stay
// fresh), but the locale switcher only offers FA. Re-add "en" and
// "fr" here when egress is back under control AND the pgvector
// migration (or alternative) has shipped + validated.
//
// Why hidden, not removed: removing the routes would 404 every
// existing /en + /fr URL. Hiding from the switcher just stops new
// visitor traffic from being routed there.
export const advertisedLocales: readonly Locale[] = ["fa"] as const;

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
