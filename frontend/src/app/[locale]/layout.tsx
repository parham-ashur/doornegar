import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale, getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { Vazirmatn, IBM_Plex_Sans } from "next/font/google";
import { locales } from "@/i18n";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import ChromeGate from "@/components/layout/ChromeGate";
import PageAtmosphere from "@/components/common/PageAtmosphere";
import UmamiTracker from "@/components/common/UmamiTracker";
import "@/styles/globals.css";

// next/font replaces the `@import url("https://fonts.googleapis.com/...")`
// that globals.css used to carry. That import blocked first paint by
// ~400-800ms — the browser had to fetch googleapis CSS, parse it, then
// fetch the actual font files, and only then could text render. With
// next/font the font files are self-hosted under /_next/static/media/
// + preloaded via a rel=preload link + inlined in the initial HTML, so
// the round-trips to fonts.googleapis.com and fonts.gstatic.com
// disappear entirely. display:swap keeps fallback text visible during
// the few ms it still takes to load. CSS variables so globals.css
// references stay unchanged.
// Weight subset audit (2026-04-25): grep across src/ found 0 uses of
// font-thin / font-extralight / font-light. Dropped the 300 weight from
// both fonts — saves 2 Vazirmatn files (arabic + latin subset) and 1
// IBM Plex Sans file on first paint without changing rendered output.
const fontPersian = Vazirmatn({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
  display: "swap",
  variable: "--font-persian",
});
const fontLatin = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-latin",
});

// metadataBase lets Next resolve all relative OG/Twitter image URLs and
// canonical hrefs against the public origin. Without it, Next logs a
// warning and uses a fallback that breaks OG previews on social.
export const metadata: Metadata = {
  metadataBase: new URL("https://doornegar.org"),
  title: {
    default: "دورنگر — شفافیت رسانه‌ای ایران | Doornegar",
    template: "%s — دورنگر",
  },
  description:
    "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران. تحلیل سوگیری، نگاه یک‌جانبه، و چارچوب‌بندی رسانه‌ها. " +
    "Compare Iranian news coverage across state, diaspora, and independent media.",
  keywords: [
    "دورنگر", "شفافیت رسانه", "ایران", "خبر", "سوگیری رسانه",
    "مقایسه پوشش خبری", "نگاه یک‌جانبه", "رسانه‌های فارسی",
    "Doornegar", "Iran", "media transparency", "media bias", "news comparison",
    "BBC Persian", "Iran International", "press freedom", "Persian news",
  ],
  authors: [{ name: "Doornegar" }],
  openGraph: {
    title: "دورنگر — شفافیت رسانه‌ای ایران",
    description: "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران. کدام رسانه چه خبری را پوشش داده؟",
    type: "website",
    locale: "fa_IR",
    alternateLocale: ["en_US"],
    siteName: "Doornegar - دورنگر",
    url: "https://doornegar.org",
  },
  twitter: {
    card: "summary_large_image",
    title: "دورنگر — شفافیت رسانه‌ای ایران",
    description: "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  // Generic hreflang pointing at the locale roots. Per-page routes
  // override this with their own alternates via generateMetadata so
  // /fa/stories/X and /en/stories/X reference each other specifically.
  alternates: {
    canonical: "https://doornegar.org",
    languages: {
      fa: "https://doornegar.org/fa",
      en: "https://doornegar.org/en",
      "x-default": "https://doornegar.org/fa",
    },
  },
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params: { locale },
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  setRequestLocale(locale);
  if (!locales.includes(locale as any)) notFound();

  const messages = await getMessages();
  const isRtl = locale === "fa";

  return (
    <html lang={locale} dir={isRtl ? "rtl" : "ltr"} className={`${fontPersian.variable} ${fontLatin.variable}`}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <link rel="icon" href="/favicon.ico" />
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#0a0e1a" />
        {/* Preconnect intentionally omitted — homepage images go through
            /_next/image (Vercel optimizer), not directly to R2, so a R2
            preconnect was sitting unused (Lighthouse flagged it). When/if
            the hero starts loading directly from R2 (skip-optimizer for
            already-WebP-encoded source), add the preconnect back here. */}
      </head>
      <body className={`min-h-screen bg-white text-slate-900 dark:bg-[#0a0e1a] dark:text-slate-100 ${isRtl ? "font-persian" : "font-latin"}`}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <div className="flex min-h-screen flex-col">
            <ChromeGate>
              <Header />
            </ChromeGate>
            <main className="flex-1">{children}</main>
            <ChromeGate>
              <Footer />
            </ChromeGate>
            <ChromeGate>
              <PageAtmosphere />
            </ChromeGate>
          </div>
        </NextIntlClientProvider>
        <UmamiTracker />
      </body>
    </html>
  );
}
