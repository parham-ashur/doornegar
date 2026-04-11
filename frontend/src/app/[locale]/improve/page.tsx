"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";

export default function ImproveRedirect() {
  const router = useRouter();
  const locale = useLocale();

  useEffect(() => {
    router.replace(`/${locale}/rate`);
  }, [router, locale]);

  return (
    <div dir="rtl" className="mx-auto max-w-2xl px-4 py-16 text-center">
      <p className="text-sm text-slate-500">در حال انتقال به صفحه بازخورد...</p>
    </div>
  );
}
