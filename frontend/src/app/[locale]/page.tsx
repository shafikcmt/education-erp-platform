import { ArrowRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";

export default function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  setRequestLocale(locale);
  const t = useTranslations();

  return (
    <div className="mx-auto flex min-h-dvh max-w-3xl flex-col px-4 py-6 sm:px-6">
      <header className="flex items-center justify-between gap-4">
        <span className="text-base font-semibold">{t("common.appName")}</span>
        <LocaleSwitcher pathname="/" />
      </header>
      <main id="main" className="flex flex-1 flex-col justify-center gap-6 py-16">
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">
          {t("home.heading")}
        </h1>
        <p className="text-muted-foreground max-w-2xl text-lg text-pretty">{t("home.tagline")}</p>
        <p className="bg-muted text-muted-foreground w-fit rounded-md border px-3 py-2 text-sm">
          {t("home.status")}
        </p>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/login">
              {t("home.signIn")}
              <ArrowRight aria-hidden="true" className="rtl:rotate-180" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/system">{t("home.systemLink")}</Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
