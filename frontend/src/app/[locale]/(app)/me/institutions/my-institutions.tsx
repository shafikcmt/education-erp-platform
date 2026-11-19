"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";

import { PageHeader } from "@/components/app/page-header";
import { Alert } from "@/components/ui/alert";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

/** "My institutions" (plan §13.1, P2): every membership with its sign-in link. Each tenant
 * has its own host and its own sign-in (Q2), so this page only links there. */
export function MyInstitutions() {
  const t = useTranslations("tenancy");
  const memberships = useQuery({
    queryKey: ["me", "memberships"],
    queryFn: () => unwrap(api().GET("/api/v1/me/memberships/")),
  });
  const rows = memberships.data ?? [];
  return (
    <>
      <PageHeader title={t("mine.title")} description={t("mine.subtitle")} />
      {memberships.isSuccess && !rows.length ? <Alert>{t("mine.empty")}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {rows.map((row) => (
          <Card key={row.tenant_id}>
            <CardHeader>
              <CardTitle>{row.name}</CardTitle>
              <CardDescription>
                {t(`status.${row.membership_status}` as "status.active")} ·{" "}
                {t(`tenantStatus.${row.tenant_status}` as "tenantStatus.active")}
              </CardDescription>
              {row.sign_in_url && row.membership_status === "active" ? (
                <a
                  href={row.sign_in_url}
                  className="text-primary inline-flex items-center gap-1 text-sm font-medium underline-offset-4 hover:underline"
                >
                  {t("mine.signIn")} <ExternalLink aria-hidden="true" className="size-4" />
                </a>
              ) : (
                <p className="text-muted-foreground text-sm">{t("mine.hostsDisabled")}</p>
              )}
            </CardHeader>
          </Card>
        ))}
      </div>
    </>
  );
}
