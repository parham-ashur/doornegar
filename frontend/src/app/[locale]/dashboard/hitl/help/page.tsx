"use client";

/**
 * HITL instructions page. One place that explains every control — what
 * each queue is for, when to use the split / freeze / arc-scaffold
 * endpoints, and what the review tiers mean. Parham keeps adding new
 * primitives; without this doc the menu becomes a pile of unmarked
 * buttons.
 */
export default function HitlHelp() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-2">
        راهنمای ابزارهای انسانی در حلقه
      </h1>
      <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-6 leading-6">
        هر ابزار برای رفع یکی از ابهام‌های خط‌لولهٔ خودکار ساخته شده. این صفحه
        هم شرح می‌دهد چه کاری می‌کنند، هم چه موقع باید از هر کدام استفاده کرد.
      </p>

      <Section title="صف بازنگری (Review Queue)">
        <p>
          زمانی که یک خوشه خبری بیش از اندازه بزرگ شده یا بیش از حد طول کشیده،
          خط‌لوله آن را در صف بازنگری علامت می‌زند. سه درجه وجود دارد:
        </p>
        <Ul>
          <li>
            <b>درجهٔ ۱ (هشدار سبک):</b> ۱۰۰+ مقاله یا فاصلهٔ ۳+ روز میان ایجاد و آخرین
            به‌روز رسانی. فقط اطلاع — معمولاً لازم نیست اقدام کنی.
          </li>
          <li>
            <b>درجهٔ ۲ (هشدار جدی):</b> ۱۵۰+ مقاله یا ۵+ روز. خوشه را باز کن و مرور کن.
          </li>
          <li>
            <b>درجهٔ ۳ (پیشنهاد انجماد):</b> ۲۰۰+ مقاله یا ۷+ روز. اگر خوشه چند رویداد
            را در خود جای داده باید <b>تقسیم</b> شود؛ اگر رویداد پایان یافته باید
            <b>منجمد</b> شود تا مقالات تازه وارد آن نشوند.
          </li>
          <li>
            <b>تک‌منبعی:</b> خوشه‌هایی که تمام مقالاتشان از یک رسانه آمده‌اند.
            از رتبه‌بندی روز حذف می‌شوند و برای ادغام یا مخفی‌سازی در صف می‌آیند.
          </li>
        </Ul>
      </Section>

      <Section title="انجماد خوشه (Freeze)">
        <p>
          خوشهٔ منجمد دیگر در مرحلهٔ تطبیق یا ادغام خودکار دخالت نمی‌یابد —
          هیچ مقالهٔ تازه‌ای به آن اضافه نمی‌شود. برای رویدادهایی که پایان یافته‌اند
          استفاده کن تا مانع انباشت دیرهنگام مقالات شود. همیشه قابل بازگشت است.
        </p>
        <Endpoint method="POST" path="/api/v1/admin/hitl/stories/{id}/freeze" />
        <Endpoint method="POST" path="/api/v1/admin/hitl/stories/{id}/unfreeze" />
      </Section>

      <Section title="تقسیم خوشه (Split)">
        <p>
          وقتی متوجه می‌شوی یک خوشه چند رویداد مجزا را در خود نگه داشته،
          هر زیررویداد را با فهرست صریح شناسه‌های مقاله‌اش مشخص کن.
          خوشهٔ مادر منجمد می‌شود و فرزندان در یک قوس روایی (اختیاری) کنار هم قرار می‌گیرند.
          پست‌های تلگرام در دور بعدی خط‌لوله خودکار به خوشهٔ درست منتقل می‌شوند.
        </p>
        <Endpoint method="POST" path="/api/v1/admin/hitl/stories/{id}/split" />
        <p className="mt-2">
          نیلوفر هم می‌تواند در گزارش ممیزی‌اش <code>fix_type: split_story</code>
          پیشنهاد بدهد؛ کافی‌ست در دستور <code>--apply-from</code> تأیید کنی.
        </p>
      </Section>

      <Section title="قوس روایت (Arc Scaffold)">
        <p>
          وقتی از قبل می‌دانی یک روایت طولانی مثل «A سپس B سپس C سپس D» رخ داده،
          می‌توانی عنوان قوس و فصل‌ها را به صورت یکجا تعریف کنی. سیستم برای هر فصل
          تلاش می‌کند خوشهٔ موجود مطابق با عنوان/کلیدواژه پیدا کند؛
          در صورت نبودن، خوشهٔ خالی می‌سازد تا مقالات آینده به آن وصل شوند.
        </p>
        <Endpoint method="POST" path="/api/v1/admin/hitl/arcs/scaffold-preview" note="پیش‌نمایش — هیچ چیز ذخیره نمی‌شود" />
        <Endpoint method="POST" path="/api/v1/admin/hitl/arcs/scaffold" />
      </Section>

      <Section title="صف تصاویر">
        <p>
          صفحهٔ اصلی و «خبرهای مرتبط» در انتهای صفحهٔ خبر، دیگر خبرهایی که فقط لوگوی
          رسانه را به عنوان تصویر دارند نشان نمی‌دهند. این خبرها در صف «خبرهای بدون تصویر»
          (صفحهٔ اول HITL) مرتب‌شده بر اساس اولویت می‌آیند. روی دکمهٔ «انتخاب تصویر»
          بزن تا به صفحهٔ Unsplash بروی — عنوان انگلیسی از پیش در نوار جستجو قرار می‌گیرد
          و خلاصهٔ فارسی خبر در بالای صفحه قابل دیدن است.
        </p>
      </Section>

      <Section title="صف بررسی پست‌های تلگرام (Triage)">
        <p>
          پست‌هایی که امتیاز اتصالشان به خوشه بین ۰٫۳۰ و ۰٫۴۰ است به صورت خودکار متصل نمی‌شوند
          (آستانهٔ خودکار ۰٫۴۰ است). این صف همان «مرز تصمیم» را نشان می‌دهد. می‌توانی پست را به
          خبر درست متصل کنی یا کاملاً از خوشه درآوری‌ش.
        </p>
      </Section>

      <Section title="دسته‌بندی رسانه‌ها و کانال‌ها">
        <p>
          اگر محل تولید یا همسویی سیاسی رسانه یا کانالی اشتباه ثبت شده،
          از این ابزارها استفاده کن. زیرگروه ۴-تایی (اصول‌گرا / اصلاح‌طلب / میانه‌رو / رادیکال)
          مستقیماً از این فیلدها ساخته می‌شود.
        </p>
      </Section>

      <Section title="ممیزی نیلوفر">
        <p>
          نیلوفر نمونه‌ای از خوشه‌های برترین روز را به صورت JSON بیرون می‌دهد؛
          می‌توانی محلی بررسی کنی و سپس با <code>--apply-from</code> اصلاحات را اعمال کنی.
          اصلاحات شامل: تغییر عنوان، بازنویسی روایت‌ها، حذف مقالهٔ بی‌ربط،
          ادغام دو خوشه، تقسیم یک خوشه و نوسازی تحلیل نقص.
        </p>
      </Section>

      <Section title="رخدادهای خوشه (Story Events)">
        <p>
          تمام تصمیم‌های خودکار (اتصال، ایجاد، ادغام، ارتقاء درجه) و اقدام‌های دستی
          (انجماد، تقسیم، ساخت قوس) در جدول <code>story_events</code> ثبت می‌شود.
        </p>
        <Endpoint method="GET" path="/api/v1/admin/hitl/review-queue" note="فهرست خوشه‌های علامت‌زده" />
        <Endpoint method="GET" path="/api/v1/admin/hitl/stories/{id}/events" note="تاریخچهٔ یک خوشه" />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-7 border-t border-slate-200 dark:border-slate-800 pt-5">
      <h2 className="text-[15px] font-black text-slate-900 dark:text-white mb-2">
        {title}
      </h2>
      <div className="text-[13px] text-slate-600 dark:text-slate-300 leading-7 space-y-2">
        {children}
      </div>
    </section>
  );
}

function Ul({ children }: { children: React.ReactNode }) {
  return <ul className="list-disc pr-5 space-y-1">{children}</ul>;
}

function Endpoint({ method, path, note }: { method: string; path: string; note?: string }) {
  return (
    <div
      className="font-mono text-[11px] bg-slate-100 dark:bg-slate-800 px-2 py-1 inline-flex flex-wrap items-center gap-2 mr-2 mb-1"
      dir="ltr"
    >
      <span className="font-black">{method}</span>
      <span>{path}</span>
      {note && <span className="text-slate-500">— {note}</span>}
    </div>
  );
}
