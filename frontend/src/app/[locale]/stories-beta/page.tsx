import { setRequestLocale } from "next-intl/server";
import StoriesCarousel from "@/components/stories/StoriesCarousel";
import type {
  BlindspotSlotData,
  MaxDisagreementSlotData,
  StoryCore,
  StorySlot,
  TelegramSlotData,
} from "@/components/stories/types";

export const dynamic = "force-static";

const STORY_1: StoryCore = {
  id: "demo-1",
  title: "آتش‌بس دو هفته‌ای ایران و آمریکا؛ آزادی خبرنگار آمریکایی و حمله حزب‌الله به صفد",
  sourceCount: 14,
  articleCount: 125,
  progressivePosition:
    "رسانه‌های دیاسپورا بر جزئیات آتش‌بس و پیامدهای منطقه‌ای متمرکز شدند؛ آزادی خبرنگار را به عنوان نشانه‌ای از ضعف دولت تفسیر کردند و از حمله حزب‌الله به صفد به عنوان ادامه‌ی تنش‌های فرا مرزی یاد کردند.",
  conservativePosition:
    "رسانه‌های دولتی توافق آتش‌بس را پیروزی دیپلماتیک جمهوری اسلامی خواندند و آزادی خبرنگار را نشانه‌ی حسن نیت ایران معرفی کردند. از حمله حزب‌الله به صفد با عنوان «پاسخ مقاومت» یاد شد.",
  telegramSummary:
    "کانال‌های تلگرامی اصول‌گرا این رویدادها را شاهدی بر «توازن قدرت جدید» خواندند. در مقابل، کانال‌های منتقد از «پیچیدگی‌های پشت پرده» و ابهام در شرایط آتش‌بس ابراز نگرانی کردند. ۴۳٪ تحلیلگران تداوم آتش‌بس تا پایان سال را پیش‌بینی می‌کنند.",
  media: {
    type: "image",
    src: "https://picsum.photos/seed/doornegar1/900/1600",
  },
};

const STORY_2: StoryCore = {
  id: "demo-2",
  title: "چهل‌وچهارمین شب تجمع‌های کرمان؛ تداوم «شب‌های اقتدار»",
  sourceCount: 9,
  articleCount: 62,
  progressivePosition:
    "گزارش‌های دیاسپورا بر طول‌مدت اعتراضات، آمار بازداشتی‌ها و شعارهای سیاسی تجمع‌کنندگان تاکید کردند.",
  conservativePosition:
    "رسانه‌های داخلی این تجمعات را «مراسم عزاداری» خواندند و بر آرامش شهر و حضور نیروهای امنیتی برای حفظ نظم تمرکز کردند.",
  telegramSummary:
    "کانال‌های تلگرامی در مورد شرایط کرمان نظرات متضاد داشتند؛ برخی از ادامه اعتراضات و برخی از آرامش شهر خبر دادند.",
  media: {
    type: "image",
    src: "https://picsum.photos/seed/doornegar2/900/1600",
  },
};

const STORY_3: StoryCore = {
  id: "demo-3",
  title: "توافق اوپک پلاس بر سر افزایش تولید نفت تا پایان سال",
  sourceCount: 11,
  articleCount: 78,
  media: {
    type: "image",
    src: "https://picsum.photos/seed/doornegar3/900/1600",
  },
};

const BLINDSPOT_A: StoryCore = {
  id: "bs-a",
  title: "گزارش حقوق بشر: ۱۲ حکم اعدام در هفته گذشته",
  sourceCount: 6,
  media: { type: "image", src: "https://picsum.photos/seed/blindA/900/900" },
};

const BLINDSPOT_B: StoryCore = {
  id: "bs-b",
  title: "افتتاح خط لوله‌ی جدید گاز به ترکمنستان",
  sourceCount: 5,
  media: { type: "image", src: "https://picsum.photos/seed/blindB/900/900" },
};

const TELEGRAM_DATA: TelegramSlotData = {
  title: "تحلیل روایت‌های تلگرام",
  predictions: [
    {
      text: "آتش‌بس ایران و آمریکا احتمالاً تا پایان سال ادامه خواهد یافت و مذاکرات به سطح بالاتری می‌رسد.",
      percent: 43,
    },
    {
      text: "اعتراضات کرمان در هفته‌های آینده به شهرهای دیگر نیز سرایت خواهد کرد.",
      percent: 28,
    },
    {
      text: "توافق اوپک پلاس با فشار آمریکا در دو ماه آینده شکسته می‌شود.",
      percent: 19,
    },
  ],
  claims: [
    {
      source: "کانال «اخبار فوری»",
      text: "۷ نفر از بازداشتی‌های اعتراضات کرمان به اعدام محکوم شده‌اند، این خبر هنوز توسط هیچ منبع رسمی تأیید نشده است.",
      verified: false,
      story: STORY_2,
    },
    {
      source: "کانال «روایت»",
      text: "جلسه‌ی غیررسمی میان دیپلمات‌های ایران و آمریکا دیروز در عمان برگزار شد.",
      verified: false,
    },
    {
      source: "کانال «نگاه»",
      text: "طرح جدید وزارت نفت برای افزایش ۵٪ صادرات گاز تصویب شد.",
      verified: true,
    },
  ],
};

const MAX_DISAGREEMENT: MaxDisagreementSlotData = {
  story: {
    id: "md-1",
    title: "اعتراضات در اصفهان؛ روایت‌های متضاد از ریشه‌ها",
    media: { type: "image", src: "https://picsum.photos/seed/maxDA/900/1600" },
  },
  top: {
    sideLabel: "محافظه‌کار",
    percent: 67,
    framing: "رسانه‌های داخلی اعتراضات را به «آشوب‌طلبان مزدور» نسبت دادند و بر نقش رسانه‌های بیگانه تاکید کردند.",
  },
  bottom: {
    sideLabel: "اپوزیسیون",
    percent: 40,
    framing: "رسانه‌های منتقد از نارضایتی مردم، بی‌کاری و مشکلات اقتصادی به عنوان ریشه‌ی اصلی اعتراض یاد کردند.",
  },
};

const BLINDSPOT_DATA: BlindspotSlotData = {
  top: {
    story: BLINDSPOT_A,
    sideLabel: "فقط در دیاسپورا",
    excerpt:
      "رسانه‌های خارج از کشور به تفصیل درباره‌ی صدور احکام اعدام و اسامی محکومان گزارش دادند. رسانه‌های داخلی پوشش نداده‌اند.",
  },
  bottom: {
    story: BLINDSPOT_B,
    sideLabel: "فقط در رسانه‌های دولتی",
    excerpt:
      "رسانه‌های داخلی افتتاح این خط لوله را دستاوردی برای دیپلماسی منطقه‌ای خواندند. دیاسپورا کوچک‌ترین اشاره‌ای نداشت.",
  },
};

export default async function StoriesBetaPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const dir = locale === "fa" ? "rtl" : "ltr";

  const slots: StorySlot[] = [
    { kind: "story", story: STORY_1 },
    { kind: "telegram", data: TELEGRAM_DATA },
    { kind: "story", story: STORY_2 },
    { kind: "blindspot", data: BLINDSPOT_DATA },
    { kind: "story", story: STORY_3 },
    { kind: "maxDisagreement", data: MAX_DISAGREEMENT },
  ];

  return <StoriesCarousel slots={slots} dir={dir} />;
}
