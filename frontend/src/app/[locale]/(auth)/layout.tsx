import { getTranslations } from "next-intl/server";
import type { CSSProperties, ReactNode } from "react";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { Link } from "@/i18n/navigation";
import { getServerHost } from "@/lib/api/server";
import { brandStyle } from "@/lib/tenancy/branding";

/** Centered, mobile-first layout for the authentication screens. On a tenant host it shows
 * the organisation's name and colour (plan §13.1, from `/public/tenant/`). */
export default async function AuthLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("common");
  const host = await getServerHost();
  const tenant = host.kind === "tenant" ? host.tenant : null;
  return (
    <div
      className="mx-auto flex min-h-dvh max-w-md flex-col px-4 py-6"
      style={brandStyle(tenant?.branding) as CSSProperties}
    >
      <header className="flex items-center justify-between gap-4">
        <Link href="/" className="text-primary text-base font-semibold" data-testid="brand">
          {tenant?.name ?? t("appName")}
        </Link>
        <LocaleSwitcher />
      </header>
      <main id="main" className="flex flex-1 flex-col justify-center py-10">
        {children}
      </main>
    </div>
  );
}
