"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Eye,
  Headset,
  LayoutDashboard,
  LogOut,
  School,
  ScrollText,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { IdleWarning } from "@/components/auth/idle-warning";
import { StepUpProvider } from "@/components/auth/step-up";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { Button } from "@/components/ui/button";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { can, type Me, useMe } from "@/lib/auth/me";
import { canAnywhere, type TenantContext, useTenantContext } from "@/lib/tenancy/context";
import { type HostInfo, HostProvider } from "@/lib/tenancy/host";
import { cn } from "@/lib/utils";

type NavItem = { href: string; key: string; icon: typeof ShieldCheck; show: boolean };

function platformNav(me: Me): NavItem[] {
  return [
    { href: "/account/security", key: "security", icon: ShieldCheck, show: true },
    { href: "/me/institutions", key: "myInstitutions", icon: School, show: true },
    {
      href: "/platform/tenants",
      key: "tenants",
      icon: Building2,
      show: can(me, "tenancy.tenant.view_any"),
    },
    {
      href: "/platform/support-sessions",
      key: "supportSessions",
      icon: Headset,
      show: can(me, "tenancy.support_session.request"),
    },
    { href: "/platform/users", key: "users", icon: Users, show: can(me, "identity.user.view") },
    { href: "/platform/roles", key: "roles", icon: UserCog, show: can(me, "rbac.role.view") },
    {
      href: "/platform/audit",
      key: "audit",
      icon: ScrollText,
      show: can(me, "audit.event.view"),
    },
  ];
}

function tenantNav(context: TenantContext | undefined): NavItem[] {
  const has = (code: string) => canAnywhere(context, code);
  return [
    { href: "/dashboard", key: "home", icon: LayoutDashboard, show: true },
    {
      href: "/institutions",
      key: "institutions",
      icon: School,
      show: has("tenancy.institution.view"),
    },
    { href: "/members", key: "members", icon: Users, show: has("tenancy.member.view") },
    { href: "/roles", key: "roles", icon: UserCog, show: has("rbac.role.view") },
    { href: "/settings", key: "settings", icon: Settings, show: has("tenancy.tenant.view") },
    {
      href: "/support-access",
      key: "supportAccess",
      icon: Headset,
      show: has("tenancy.support_session.view"),
    },
    { href: "/audit", key: "audit", icon: ScrollText, show: has("audit.event.view") },
    { href: "/account/security", key: "security", icon: ShieldCheck, show: true },
  ];
}

/** "Platform support has read-only access until …" (plan §13.1), for every member. */
function SupportBanner({ context }: { context: TenantContext | undefined }) {
  const t = useTranslations("tenancy");
  const format = useFormatter();
  const active = context?.support_banner ?? [];
  if (!active.length) return null;
  const until = new Date(Math.max(...active.map((s) => Date.parse(s.ends_at))));
  return (
    <div
      role="status"
      className="mt-3 flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
    >
      <Eye aria-hidden="true" className="size-4 shrink-0" />
      {context?.is_support_session
        ? t("banner.youAreSupport", {
            until: format.dateTime(until, { dateStyle: "medium", timeStyle: "short" }),
          })
        : t("banner.supportActive", {
            until: format.dateTime(until, { dateStyle: "medium", timeStyle: "short" }),
          })}
    </div>
  );
}

/** Navigation is permission-driven, but hiding is not security: the API enforces everything. */
export function AppShell({
  me: initial,
  host,
  children,
}: {
  me: Me;
  host: HostInfo;
  children: ReactNode;
}) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me = initial } = useMe(initial);
  const isTenant = host.kind === "tenant";
  const { data: context } = useTenantContext(isTenant);

  const signOut = async () => {
    await api().POST("/api/v1/auth/logout/");
    queryClient.clear();
    router.replace("/login");
  };

  const items = (isTenant ? tenantNav(context) : platformNav(me)).filter((item) => item.show);
  return (
    <HostProvider host={host}>
      <StepUpProvider mfaEnabled={me.mfa_enabled}>
        <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-4 sm:px-6">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b py-3">
            <Link href="/dashboard" className="text-base font-semibold" data-testid="brand">
              {isTenant ? host.tenant.name : t("common.appName")}
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
          {isTenant ? <SupportBanner context={context} /> : null}
          <nav aria-label={t("nav.main")} className="-mx-1 flex gap-1 overflow-x-auto py-2">
            {items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
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
                  {t(`nav.${item.key}` as "nav.main")}
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
    </HostProvider>
  );
}
