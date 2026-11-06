import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { Link } from "@/i18n/navigation";

/** Centered, mobile-first layout for the authentication screens. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  const t = useTranslations("common");
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col px-4 py-6">
      <header className="flex items-center justify-between gap-4">
        <Link href="/" className="text-base font-semibold">
          {t("appName")}
        </Link>
        <LocaleSwitcher />
      </header>
      <main id="main" className="flex flex-1 flex-col justify-center py-10">
        {children}
      </main>
    </div>
  );
}
