import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale, getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { locales } from "@/i18n";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import ChromeGate from "@/components/layout/ChromeGate";
import PageAtmosphere from "@/components/common/PageAtmosphere";
import WelcomeModal from "@/components/common/WelcomeModal";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "دورنگر — شفافیت رسانه‌ای ایران | Doornegar",
  description:
    "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران. تحلیل سوگیری، نگاه یک‌جانبه، و چارچوب‌بندی رسانه‌ها. " +
    "Compare Iranian news coverage across state, diaspora, and independent media.",
  keywords: [
    "دورنگر", "شفافیت رسانه", "ایران", "خبر", "سوگیری رسانه",
    "Doornegar", "Iran", "media transparency", "media bias", "news comparison",
    "BBC Persian", "Iran International", "press freedom",
  ],
  authors: [{ name: "Doornegar" }],
  openGraph: {
    title: "دورنگر — شفافیت رسانه‌ای ایران",
    description: "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران. کدام رسانه چه خبری را پوشش داده؟",
    type: "website",
    locale: "fa_IR",
    siteName: "Doornegar - دورنگر",
  },
  twitter: {
    card: "summary_large_image",
    title: "دورنگر — شفافیت رسانه‌ای ایران",
    description: "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران",
  },
  robots: {
    index: true,
    follow: true,
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
    <html lang={locale} dir={isRtl ? "rtl" : "ltr"}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <link rel="icon" href="/favicon.ico" />
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#0a0e1a" />
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
            <ChromeGate>
              <WelcomeModal />
            </ChromeGate>
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
