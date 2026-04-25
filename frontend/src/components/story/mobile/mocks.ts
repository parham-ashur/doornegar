import type { MobileStorySlot } from "./types";

const GRADIENT_BG = (a: string, b: string) =>
  `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 9' preserveAspectRatio='none'>` +
      `<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>` +
      `<stop offset='0%' stop-color='${a}'/><stop offset='100%' stop-color='${b}'/></linearGradient></defs>` +
      `<rect width='16' height='9' fill='url(#g)'/></svg>`,
  )}`;

export const MOCK_SLOTS: MobileStorySlot[] = [
  {
    id: "slot-1",
    kind: "story",
    title_fa: "تشدید تنش‌ها در مرز شرقی",
    title_en: "Tensions escalate on the eastern border",
    summary_fa:
      "گزارش‌های متناقض از درگیری مرزی؛ رسانه‌های داخلی بر دفاع و رسانه‌های برون‌مرزی بر تلفات تأکید می‌کنند.",
    summary_en:
      "Conflicting reports from the border; domestic outlets stress defense, diaspora outlets emphasize casualties.",
    imageUrl: GRADIENT_BG("#1e3a8a", "#0f172a"),
  },
  {
    id: "slot-2",
    kind: "story",
    title_fa: "مذاکرات هسته‌ای: گام‌های آرام در ژنو",
    title_en: "Nuclear talks: quiet steps in Geneva",
    summary_fa:
      "دور تازه گفت‌وگوها بدون اطلاعیه رسمی؛ منابع از پیشرفت محدود اما واقعی خبر می‌دهند.",
    summary_en:
      "A new round with no formal announcement; sources describe limited but real progress.",
    imageUrl: GRADIENT_BG("#064e3b", "#020617"),
  },
  {
    id: "slot-3",
    kind: "blindspot",
    title_fa: "نگاه یک‌جانبه: اعتراض‌های صنفی پرستاران",
    title_en: "Blind spot: nurses' labor protests",
    pairId: "pair-blindspot-1",
    sides: [
      {
        label_fa: "پوشش رسانه‌های داخلی",
        label_en: "Domestic coverage",
        body_fa:
          "اعتراض‌ها در سرفصل‌های داخلی بازتاب گسترده‌ای دارد؛ خواسته‌ها مطالبه‌گری حرفه‌ای توصیف می‌شود.",
        body_en:
          "Domestic outlets cover the protests broadly, framing demands as professional advocacy.",
        tone: "state",
      },
      {
        label_fa: "پوشش رسانه‌های برون‌مرزی",
        label_en: "Diaspora coverage",
        body_fa:
          "این اعتراض‌ها در رسانه‌های فارسی‌زبان خارج تقریباً نادیده گرفته شده‌اند.",
        body_en:
          "Persian-language diaspora outlets have largely ignored these protests.",
        tone: "diaspora",
      },
    ],
    imageUrl: GRADIENT_BG("#7c2d12", "#1c0a05"),
  },
  {
    id: "slot-4",
    kind: "max_disagreement",
    title_fa: "بیشترین اختلاف: وضعیت اقتصادی خانوار",
    title_en: "Max disagreement: household economy",
    pairId: "pair-disagree-1",
    sides: [
      {
        label_fa: "روایت داخلی",
        label_en: "Domestic narrative",
        body_fa:
          "رشد تولید و کنترل تورم؛ شاخص‌های مثبت در گزارش‌های رسمی.",
        body_en: "Production growth and inflation control; positive indicators in official reports.",
        tone: "state",
      },
      {
        label_fa: "روایت برون‌مرزی",
        label_en: "Diaspora narrative",
        body_fa:
          "کاهش قدرت خرید و گسترش فقر شهری؛ روایت‌های میدانی از سفره خانوار.",
        body_en: "Falling purchasing power and urban poverty; field reports from household tables.",
        tone: "diaspora",
      },
    ],
    imageUrl: GRADIENT_BG("#312e81", "#020617"),
  },
  {
    id: "slot-5",
    kind: "telegram",
    title_fa: "تحلیل تلگرام: واکنش‌ها به سفر منطقه‌ای",
    title_en: "Telegram analysis: reactions to a regional trip",
    telegram: {
      predictions_fa: [
        "احتمال امضای تفاهم‌نامه اقتصادی پیش از پایان ماه",
        "افزایش رفت‌وآمد دیپلماتیک در سه هفته آینده",
        "اعلام پروژه ترانزیتی مشترک تا فصل بعد",
      ],
      claims: [
        { text_fa: "سفر بدون هیأت تجاری انجام شده است.", credibility: "verified" },
        { text_fa: "توافق امنیتی محرمانه‌ای امضا شده.", credibility: "suspect" },
        { text_fa: "دو طرف بر سر دالار تجاری توافق کرده‌اند.", credibility: "unverified" },
      ],
    },
    imageUrl: GRADIENT_BG("#0f172a", "#000000"),
  },
  {
    id: "slot-6",
    kind: "story",
    title_fa: "سیل در شمال؛ امدادرسانی و خلأ گزارش‌گری میدانی",
    title_en: "Floods in the north; relief and the field-reporting gap",
    summary_fa:
      "تصاویر شهروندی پیش از خبرگزاری‌ها منتشر می‌شود؛ پوشش رسمی با تأخیر همراه است.",
    summary_en:
      "Citizen footage outpaces newsrooms; official coverage lags behind.",
    imageUrl: GRADIENT_BG("#155e75", "#020617"),
  },
];
