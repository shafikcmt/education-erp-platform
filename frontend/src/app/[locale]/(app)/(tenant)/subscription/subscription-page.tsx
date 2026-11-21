"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";

import { PageHeader } from "@/components/app/page-header";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useErrorMessage } from "@/lib/auth/use-error-message";
import { usagePercent } from "@/lib/tenancy/entitlements";

/** The organisation's plan, modules and limits (read-only; plan §7). Changes are made by the
 * platform team; the API enforces modules and limits on every request. */
export function SubscriptionPage() {
  const t = useTranslations("billing");
  const format = useFormatter();
  const errorMessage = useErrorMessage();
  const query = useQuery({
    queryKey: ["tenant", "subscription"],
    queryFn: () => unwrap(api().GET("/api/v1/tenant/subscription/")),
  });
  if (query.isError) return <Alert variant="destructive">{errorMessage(query.error)}</Alert>;
  const row = query.data;
  if (!row) return null;
  const enabled = row.modules.filter((m) => m.enabled);
  const disabled = row.modules.filter((m) => !m.enabled);
  return (
    <>
      <PageHeader title={t("tenant.title")} description={t("tenant.subtitle")} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("plan")}</CardTitle>
            <CardDescription>{t("tenant.planHint")}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">{t("plan")}</dt>
              <dd data-testid="plan-name">{row.plan ? row.plan.name : t("noPlan")}</dd>
              <dt className="text-muted-foreground">{t("status")}</dt>
              <dd data-testid="plan-status">
                {row.status ? t(`statuses.${row.status}` as "statuses.active") : t("noPlan")}
              </dd>
              {row.trial_ends_at ? (
                <>
                  <dt className="text-muted-foreground">{t("trialEnds")}</dt>
                  <dd>{format.dateTime(new Date(row.trial_ends_at), { dateStyle: "medium" })}</dd>
                </>
              ) : null}
              {row.addons.length ? (
                <>
                  <dt className="text-muted-foreground">{t("addons")}</dt>
                  <dd>{row.addons.map((a) => a.name).join(", ")}</dd>
                </>
              ) : null}
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("limits")}</CardTitle>
            <CardDescription>{t("tenant.limitsHint")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {Object.entries(row.limits).map(([key, usage]) => (
              <div key={key} className="grid gap-1 text-sm" data-testid={`limit-${key}`}>
                <div className="flex justify-between">
                  <span>{t(`limitNames.${key}` as "limitNames.max_campuses")}</span>
                  <span className="tabular-nums">
                    {t("usage", { used: usage.used, limit: usage.limit })}
                  </span>
                </div>
                <div
                  className="bg-muted h-2 overflow-hidden rounded-full"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={usage.limit}
                  aria-valuenow={usage.used}
                  aria-label={t(`limitNames.${key}` as "limitNames.max_campuses")}
                >
                  <div
                    className="bg-primary h-full rounded-full"
                    style={{ width: `${usagePercent(usage)}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>{t("modules")}</CardTitle>
            <CardDescription>{t("tenant.modulesHint")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <ModuleList title={t("enabledModules")} items={enabled} on />
            {disabled.length ? (
              <ModuleList title={t("unavailableModules")} items={disabled} on={false} />
            ) : null}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function ModuleList({
  title,
  items,
  on,
}: {
  title: string;
  items: { code: string; reason: string }[];
  on: boolean;
}) {
  const t = useTranslations("billing");
  const Icon = on ? CheckCircle2 : CircleSlash;
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <ul className="grid gap-1 text-sm" data-testid={on ? "modules-enabled" : "modules-disabled"}>
        {items.map((m) => (
          <li key={m.code} className="flex items-center gap-2">
            <Icon
              aria-hidden="true"
              className={on ? "size-4 text-emerald-600" : "text-muted-foreground size-4"}
            />
            <code className="text-xs">{m.code}</code>
            {m.reason ? (
              <span className="text-muted-foreground text-xs">
                {t(`reasons.${m.reason}` as "reasons.not_built")}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
