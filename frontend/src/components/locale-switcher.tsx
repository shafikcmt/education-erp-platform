import { useLocale, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

/** Accessible language switcher; keeps the current path when switching locale. */
export function LocaleSwitcher({ pathname = "/" }: { pathname?: string }) {
  const t = useTranslations();
  const current = useLocale();
  return (
    <nav aria-label={t("common.language")} className="flex gap-1">
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href={pathname}
          locale={locale}
          lang={locale}
          aria-current={locale === current ? "true" : undefined}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            locale === current
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
          )}
        >
          {t(`locale.${locale}`)}
        </Link>
      ))}
    </nav>
  );
}
