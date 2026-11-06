"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, ScrollText, ShieldCheck, UserCog, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { IdleWarning } from "@/components/auth/idle-warning";
import { StepUpProvider } from "@/components/auth/step-up";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { Button } from "@/components/ui/button";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { can, type Me, useMe } from "@/lib/auth/me";
import { cn } from "@/lib/utils";

const NAV = [
  {
    href: "/account/security",
    key: "security",
    icon: ShieldCheck,
    permission: "identity.account.view_own",
  },
  { href: "/platform/users", key: "users", icon: Users, permission: "identity.user.view" },
  { href: "/platform/roles", key: "roles", icon: UserCog, permission: "rbac.role.view" },
  { href: "/platform/audit", key: "audit", icon: ScrollText, permission: "audit.event.view" },
] as const;

/** Navigation is permission-driven, but hiding is not security: the API enforces everything. */
export function AppShell({ me: initial, children }: { me: Me; children: ReactNode }) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me = initial } = useMe(initial);

  const signOut = async () => {
    await api().POST("/api/v1/auth/logout/");
    queryClient.clear();
    router.replace("/login");
  };

  const items = NAV.filter((item) => can(me, item.permission));
  return (
    <StepUpProvider mfaEnabled={me.mfa_enabled}>
      <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-4 sm:px-6">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b py-3">
          <Link href="/dashboard" className="text-base font-semibold">
            {t("common.appName")}
          </Link>
          <div className="flex items-center gap-2">
            <LocaleSwitcher pathname={pathname} />
            <span className="text-muted-foreground hidden text-sm sm:inline" data-testid="whoami">
              {me.display_name || me.email}
            </span>
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              <LogOut aria-hidden="true" /> {t("nav.signOut")}
            </Button>
          </div>
        </header>
        <nav aria-label={t("nav.main")} className="-mx-1 flex gap-1 overflow-x-auto py-2">
          {items.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent",
                )}
              >
                <item.icon aria-hidden="true" className="size-4" />
                {t(`nav.${item.key}`)}
              </Link>
            );
          })}
        </nav>
        <main id="main" className="flex-1 py-6">
          {children}
        </main>
      </div>
      <IdleWarning idleTimeoutSeconds={me.session.idle_timeout_seconds} />
    </StepUpProvider>
  );
}
