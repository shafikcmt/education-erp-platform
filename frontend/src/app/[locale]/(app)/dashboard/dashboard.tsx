"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";
import { can, useMe } from "@/lib/auth/me";
import { OnboardingChecklist } from "@/components/studio/onboarding-checklist";
import { ScopeSwitcher, scopePermissions } from "@/components/tenancy/scope-switcher";
import { useTenantContext } from "@/lib/tenancy/context";
import { useHost } from "@/lib/tenancy/host";

export function Dashboard() {
  const t = useTranslations();
  const { data: me } = useMe();
  const host = useHost();
  const isTenant = host.kind === "tenant";
  const { data: context } = useTenantContext(isTenant);
  const [scope, setScope] = useState("all");
  if (!me) return null;
  const held = scopePermissions(context, scope);
  const has = (code: string) => held.has(code);
  const tenantCards = [
    {
      href: "/institutions",
      title: t("nav.institutions"),
      body: t("dashboard.institutions"),
      show: has("tenancy.institution.view"),
    },
    {
      href: "/members",
      title: t("nav.members"),
      body: t("dashboard.members"),
      show: has("tenancy.member.view"),
    },
    {
      href: "/roles",
      title: t("nav.roles"),
      body: t("dashboard.tenantRoles"),
      show: has("rbac.role.view"),
    },
    {
      href: "/settings",
      title: t("nav.settings"),
      body: t("dashboard.settings"),
      show: has("tenancy.tenant.view"),
    },
    {
      href: "/studio",
      title: t("nav.studio"),
      body: t("dashboard.studio"),
      show: has("customization.config.view"),
    },
    {
      href: "/support-access",
      title: t("nav.supportAccess"),
      body: t("dashboard.supportAccess"),
      show: has("tenancy.support_session.view"),
    },
    {
      href: "/audit",
      title: t("nav.audit"),
      body: t("dashboard.audit"),
      show: has("audit.event.view"),
    },
    {
      href: "/account/security",
      title: t("nav.security"),
      body: t("dashboard.security"),
      show: true,
    },
  ];
  const platformCards = [
    {
      href: "/account/security",
      title: t("nav.security"),
      body: t("dashboard.security"),
      show: true,
    },
    {
      href: "/me/institutions",
      title: t("nav.myInstitutions"),
      body: t("dashboard.myInstitutions"),
      show: true,
    },
    {
      href: "/platform/tenants",
      title: t("nav.tenants"),
      body: t("dashboard.tenants"),
      show: can(me, "tenancy.tenant.view_any"),
    },
    {
      href: "/platform/support-sessions",
      title: t("nav.supportSessions"),
      body: t("dashboard.supportSessions"),
      show: can(me, "tenancy.support_session.request"),
    },
    {
      href: "/platform/users",
      title: t("nav.users"),
      body: t("dashboard.users"),
      show: can(me, "identity.user.view"),
    },
    {
      href: "/platform/roles",
      title: t("nav.roles"),
      body: t("dashboard.roles"),
      show: can(me, "rbac.role.view"),
    },
    {
      href: "/platform/audit",
      title: t("nav.audit"),
      body: t("dashboard.audit"),
      show: can(me, "audit.event.view"),
    },
  ];
  const cards = (isTenant ? tenantCards : platformCards).filter((c) => c.show);
  return (
    <>
      <PageHeader
        title={t("dashboard.title", { name: me.display_name || me.email })}
        description={t("dashboard.subtitle")}
      />
      {isTenant && context ? <OnboardingChecklist context={context} /> : null}
      {isTenant && context ? (
        <ScopeSwitcher context={context} value={scope} onChange={setScope} />
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {cards.map((card) => (
          <Link key={card.href} href={card.href} className="rounded-xl focus-visible:outline-2">
            <Card className="hover:bg-accent/50 h-full transition-colors">
              <CardHeader>
                <CardTitle>{card.title}</CardTitle>
                <CardDescription>{card.body}</CardDescription>
              </CardHeader>
              <CardContent />
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
