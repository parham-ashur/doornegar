import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale, getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { locales } from "@/i18n";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "دورنگر — شفافیت رسانه‌ای ایران | Doornegar",
  description:
    "مقایسه پوشش خبری رسانه‌های داخل و خارج ایران. تحلیل سوگیری، نقاط کور، و چارچوب‌بندی رسانه‌ها. " +
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
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </head>
      <body className={`min-h-screen ${isRtl ? "font-persian" : "font-latin"}`}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <div className="flex min-h-screen flex-col">
            <Header />
            <main className="flex-1">{children}</main>
            <Footer />
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
