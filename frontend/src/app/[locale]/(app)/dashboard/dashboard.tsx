"use client";

import { useTranslations } from "next-intl";

import { PageHeader } from "@/components/app/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";
import { can, useMe } from "@/lib/auth/me";

export function Dashboard() {
  const t = useTranslations();
  const { data: me } = useMe();
  if (!me) return null;
  const cards = [
    {
      href: "/account/security",
      title: t("nav.security"),
      body: t("dashboard.security"),
      show: true,
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
  ].filter((c) => c.show);
  return (
    <>
      <PageHeader
        title={t("dashboard.title", { name: me.display_name || me.email })}
        description={t("dashboard.subtitle")}
      />
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
