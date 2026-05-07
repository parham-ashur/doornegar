import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { locales, type Locale } from "@/i18n";

type PageProps = {
  params: { locale: string };
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params: { locale } }: PageProps): Promise<Metadata> {
  if (!locales.includes(locale as Locale)) return {};
  const meta = METADATA[locale as Locale];
  return {
    title: meta.title,
    description: meta.description,
    alternates: {
      canonical: `https://doornegar.org/${locale}/about`,
      languages: {
        fa: "https://doornegar.org/fa/about",
        en: "https://doornegar.org/en/about",
        fr: "https://doornegar.org/fr/about",
        "x-default": "https://doornegar.org/fa/about",
      },
    },
  };
}

const METADATA: Record<Locale, { title: string; description: string }> = {
  fa: {
    title: "روش کار — دورنگر",
    description: "روش گردآوری، طبقه‌بندی، و تحلیل پوشش رسانه‌ای ایران در دورنگر",
  },
  en: {
    title: "Methodology — Doornegar",
    description:
      "How Doornegar gathers, classifies, and analyzes Iranian media coverage. Niloofar's editorial commitments and the source spectrum.",
  },
  fr: {
    title: "Méthodologie — Doornegar",
    description:
      "Comment Doornegar collecte, classe et analyse la couverture médiatique iranienne. Engagements éditoriaux de Niloofar et spectre des sources.",
  },
};

export default function AboutPage({ params: { locale } }: PageProps) {
  if (!locales.includes(locale as Locale)) notFound();
  setRequestLocale(locale);
  const isRtl = locale === "fa";
  const Content = CONTENT[locale as Locale];

  return (
    <article
      dir={isRtl ? "rtl" : "ltr"}
      className="mx-auto max-w-2xl px-4 py-10 md:py-14 leading-relaxed"
    >
      <Content />
    </article>
  );
}

// ─── Per-locale content ─────────────────────────────────────────────
// Long-form editorial prose lives here, not in messages/{locale}.json,
// so the JSON files stay scoped to UI strings. Each persona writes in
// her own register (Niloofar-FA = Ashouri-style analytical Persian,
// Niloofar-EN = NYT, Niloofar-FR = Le Monde).

function FaContent() {
  return (
    <>
      <h1 className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mb-2">
        روش کار
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-8">
        نوشتهٔ نیلوفر — سرپرست تحلیل دورنگر
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          نیلوفر کیست
        </h2>
        <p className="text-slate-700 dark:text-slate-300">
          نیلوفر صدای تحریریهٔ دورنگر است. کارش این نیست که خبر تازه‌ای بسازد؛
          کارش خواندن دقیق پوشش رسانه‌ای موجود است: چه گفته شد، چه نگفته شد، چه
          واژه‌ای به کار رفت، چه واژه‌ای کنار گذاشته شد. تحلیل او بر دادهٔ پوشش
          استوار است، نه بر داوری اخلاقی.
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          طیف رسانه‌ای
        </h2>
        <p className="text-slate-700 dark:text-slate-300 mb-3">
          هر منبع در دورنگر روی یک طیف چهارقسمتی جای می‌گیرد:
        </p>
        <ul className="space-y-2 text-slate-700 dark:text-slate-300 list-disc ps-6">
          <li>
            <strong className="text-slate-900 dark:text-white">دولتی</strong> —
            رسانه‌هایی که به نهادهای حاکمیتی مستقیماً وابسته‌اند (ایرنا، صداوسیما،
            خبرگزاری فارس).
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">نیمه‌دولتی</strong>
            {" "}— رسانه‌هایی با وابستگی غیرمستقیم به نهادهای حاکمیتی یا گروه‌های
            وابسته (تابناک، ایلنا).
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">مستقل</strong> —
            رسانه‌های فعال در داخل ایران بدون وابستگی نهادی روشن (شرق،
            اعتمادآنلاین، خبرآنلاین).
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">برون‌مرزی</strong>
            {" "}— رسانه‌های فارسی‌زبان فعال خارج از ایران (بی‌بی‌سی فارسی، رادیو فردا،
            ایندیپندنت فارسی، ایران اینترنشنال، منوتو، رادیو زمانه).
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          تعهدات تحریریه
        </h2>
        <ul className="space-y-2 text-slate-700 dark:text-slate-300 list-disc ps-6">
          <li>منابع را به نام و طیف معرفی می‌کنیم؛ پرانتز توضیحی به نام منبع
            اضافه نمی‌کنیم. اطلاعات تأمین مالی و وابستگی در صفحهٔ هر منبع آمده.</li>
          <li>وقتی یک منبع تردید کرده، تردید او را حفظ می‌کنیم. «بنا بر گزارش»
            در پارسی همان‌جایی می‌ماند که در متن اصلی بود.</li>
          <li>چارچوب‌بندی تحریری از طریق ساختار جمله و انتخاب فعل بیان می‌شود،
            نه با صفت ارزشی.</li>
          <li>سکوت‌ها به اندازهٔ روایت‌ها مهم‌اند. اگر یک طرف طیف خبری را اصلاً
            پوشش نداد، این خود یک یافتهٔ تحلیلی است.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          چه چیز را وعده نمی‌دهیم
        </h2>
        <p className="text-slate-700 dark:text-slate-300">
          دورنگر داور بی‌طرف نیست. هیچ پلتفرمی که از دل یک سامانهٔ رسانه‌ای
          ایجاد شده باشد نمی‌تواند ادعای خنثی‌بودن مطلق کند. آنچه ما می‌توانیم
          متعهد شویم این است: روش‌مان عمومی است، طبقه‌بندی منابع‌مان قابل
          بازرسی است، و یافته‌ها همیشه با ارجاع به مقالاتی هستند که بر آن‌ها
          متکی شده‌ایم.
        </p>
      </section>
    </>
  );
}

function EnContent() {
  return (
    <>
      <h1 className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mb-2">
        Methodology
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-8">
        By Niloofar — editorial lead, Doornegar
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          About Niloofar
        </h2>
        <p className="text-slate-700 dark:text-slate-300 mb-3">
          Niloofar is the byline on Doornegar's analysis. She does not break
          news. She reads the existing coverage carefully — what was said,
          what was not said, which words appeared, which were avoided. The
          analysis sits on coverage data, not moral judgment.
        </p>
        <p className="text-slate-700 dark:text-slate-300">
          She writes for foreign correspondents on the Iran beat, academics
          and policy researchers, and the Anglophone Iranian diaspora —
          readers comfortable with terms like IRGC, the Strait of Hormuz, and
          Khamenei without expansion.
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          The source spectrum
        </h2>
        <p className="text-slate-700 dark:text-slate-300 mb-3">
          Each outlet on Doornegar sits on a four-part spectrum:
        </p>
        <ul className="space-y-2 text-slate-700 dark:text-slate-300 list-disc ps-6">
          <li>
            <strong className="text-slate-900 dark:text-white">State</strong> —
            outlets directly tied to government institutions: IRNA, IRIB,
            Fars News.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">Semi-state</strong>{" "}
            — outlets with indirect ties to government or affiliated
            blocs: Tabnak, ILNA.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">Independent</strong>{" "}
            — outlets operating inside Iran without clear institutional
            affiliation: Sharq Daily, Etemad Online, Khabar Online.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">Diaspora</strong>{" "}
            — Persian-language outlets operating outside Iran: BBC Persian,
            Radio Farda, Independent Persian, Iran International, Manoto,
            Radio Zamaneh.
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          Editorial commitments
        </h2>
        <ul className="space-y-2 text-slate-700 dark:text-slate-300 list-disc ps-6">
          <li>
            Outlets are introduced by name and spectrum position. We do not
            attach funding-disclosure parentheticals to outlet names; that
            information lives on each source's detail page.
          </li>
          <li>
            When a source hedges, the hedge stays. "According to" in Persian
            stays "according to" in English.
          </li>
          <li>
            Editorial framing is carried by sentence structure and verb
            choice, not by judgment-laden adjectives.
          </li>
          <li>
            Silence is data. When one side of the spectrum did not cover a
            story at all, that absence is itself an analytic finding.
          </li>
          <li>
            We use "the regime" for نظام — the broader establishment that
            includes the supreme leader's office, the IRGC, and the
            judiciary — and reserve "the government" for the executive
            specifically.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          What we don't claim
        </h2>
        <p className="text-slate-700 dark:text-slate-300">
          Doornegar is not a neutral arbiter. No platform built from inside
          a media ecosystem can claim absolute neutrality. What we do
          commit to: our method is public, our source classifications are
          inspectable, and our findings always reference the articles they
          rest on.
        </p>
      </section>
    </>
  );
}

function FrContent() {
  return (
    <>
      <h1 className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mb-2">
        Méthodologie
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-8">
        Par Niloofar — responsable éditoriale, Doornegar
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          À propos de Niloofar
        </h2>
        <p className="text-slate-700 dark:text-slate-300 mb-3">
          Niloofar est la signature des analyses de Doornegar. Elle ne fait
          pas de scoop. Elle relit la couverture existante avec attention :
          ce qui a été dit, ce qui a été tu, quels termes sont apparus,
          lesquels ont été écartés. L'analyse repose sur les données de
          couverture, pas sur le jugement moral.
        </p>
        <p className="text-slate-700 dark:text-slate-300">
          Elle écrit pour les journalistes spécialistes du Moyen-Orient,
          les universitaires et chercheurs en politique iranienne, et la
          diaspora iranienne francophone — un lectorat qui maîtrise sans
          glose des termes comme « les Gardiens de la révolution », « le
          détroit d'Ormuz » ou « Khamenei ».
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          Le spectre des sources
        </h2>
        <p className="text-slate-700 dark:text-slate-300 mb-3">
          Chaque média répertorié sur Doornegar se situe sur un spectre
          en quatre parties :
        </p>
        <ul className="space-y-2 text-slate-700 dark:text-slate-300 list-disc ps-6">
          <li>
            <strong className="text-slate-900 dark:text-white">État</strong> —
            médias directement rattachés aux institutions gouvernementales :
            IRNA, IRIB, Fars News.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">Semi-étatique</strong>
            {" "}— médias liés indirectement au pouvoir ou à des blocs affiliés :
            Tabnak, ILNA.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">Indépendant</strong>
            {" "}— médias en activité en Iran, sans affiliation institutionnelle
            claire : Sharq, Etemad Online, Khabar Online.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-white">Diaspora</strong>
            {" "}— médias persanophones opérant hors d'Iran : BBC Persan, Radio
            Farda, Independent Persian, Iran International, Manoto, Radio
            Zamaneh.
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          Engagements éditoriaux
        </h2>
        <ul className="space-y-2 text-slate-700 dark:text-slate-300 list-disc ps-6">
          <li>
            Les médias sont présentés par leur nom et leur position sur le
            spectre. Aucune parenthèse de divulgation de financement
            accolée au nom du média : ces éléments figurent sur la page de
            chaque source.
          </li>
          <li>
            Lorsqu'une source nuance, la nuance demeure. « Selon… » en
            persan reste « selon… » en français.
          </li>
          <li>
            Le cadrage éditorial passe par la structure de la phrase et le
            choix des verbes, pas par des adjectifs de jugement.
          </li>
          <li>
            Le silence est une donnée. Quand un côté du spectre n'a pas du
            tout couvert un sujet, cette absence est en soi un constat
            d'analyse.
          </li>
          <li>
            Nous traduisons « نظام » par « le régime » — l'établissement
            au sens large qui inclut le bureau du Guide suprême, les
            Gardiens de la révolution et le pouvoir judiciaire — et
            réservons « le gouvernement » à la fonction exécutive
            spécifiquement.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
          Ce que nous ne prétendons pas
        </h2>
        <p className="text-slate-700 dark:text-slate-300">
          Doornegar n'est pas un arbitre neutre. Aucune plateforme bâtie
          depuis l'intérieur d'un écosystème médiatique ne peut prétendre
          à la neutralité absolue. Ce à quoi nous nous engageons : notre
          méthode est publique, notre classement des sources est
          inspectable, et nos constats renvoient toujours aux articles
          sur lesquels ils s'appuient.
        </p>
      </section>
    </>
  );
}

const CONTENT: Record<Locale, () => JSX.Element> = {
  fa: FaContent,
  en: EnContent,
  fr: FrContent,
};
