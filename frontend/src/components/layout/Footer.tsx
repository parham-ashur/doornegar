import { useTranslations } from "next-intl";

export default function Footer() {
  const t = useTranslations();

  return (
    <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <p className="text-lg font-bold text-slate-900 dark:text-white">
            {t("app.name")}
          </p>
          <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">
            {t("app.description")}
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-600">
            Open source &middot; Free forever
          </p>
        </div>
      </div>
    </footer>
  );
}
