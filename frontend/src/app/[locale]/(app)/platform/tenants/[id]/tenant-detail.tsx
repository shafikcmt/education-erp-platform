"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ReasonDialog } from "@/components/tenancy/reason-dialog";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/** Registry entry of one tenant (plan §13.1): status, limits, owner invitation. Registry
 * fields only; the platform never sees tenant data here (D8). */
export function TenantDetail({ id = "" }: { id?: string }) {
  const t = useTranslations();
  const format = useFormatter();
  const { data: me } = useMe();
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const key = ["platform", "tenants", "detail", id];
  const tenant = useQuery({
    queryKey: key,
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/platform/tenants/{tenant_id}/", { params: { path: { tenant_id: id } } }),
      ),
  });
  const [limits, setLimits] = useState({ institutions: "", campuses: "" });
  const [ownerEmail, setOwnerEmail] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["platform", "tenants"] });
  const path = { params: { path: { tenant_id: id } } };
  const row = tenant.data;
  if (tenant.isError) return <Alert variant="destructive">{errorMessage(tenant.error)}</Alert>;
  if (!row) return null;
  const sendOwner = async () => {
    setFailure(null);
    setNotice(null);
    try {
      await unwrap(
        api().POST("/api/v1/platform/tenants/{tenant_id}/owner-invitation/", {
          ...path,
          body: { email: ownerEmail.trim() },
        }),
      );
      setOwnerEmail("");
      setNotice(t("tenancy.tenants.ownerInvited"));
    } catch (error) {
      setFailure(errorMessage(error));
    }
  };
  return (
    <>
      <PageHeader
        title={row.name}
        description={`${row.slug} · ${t(`tenancy.tenantStatus.${row.status}` as "tenancy.tenantStatus.active")}`}
        actions={
          can(me, "tenancy.tenant.suspend") ? (
            row.status === "active" ? (
              <ReasonDialog
                variant="destructive"
                trigger={t("tenancy.tenants.suspend")}
                title={t("tenancy.tenants.suspend")}
                description={t("tenancy.tenants.suspendHint")}
                confirm={t("tenancy.tenants.suspend")}
                onConfirm={async (reason) => {
                  await unwrap(
                    api().POST("/api/v1/platform/tenants/{tenant_id}/suspend/", {
                      ...path,
                      body: { reason },
                    }),
                  );
                  await refresh();
                }}
              />
            ) : row.status === "suspended" ? (
              <ReasonDialog
                trigger={t("tenancy.tenants.reactivate")}
                title={t("tenancy.tenants.reactivate")}
                description={t("tenancy.tenants.reactivateHint")}
                confirm={t("tenancy.tenants.reactivate")}
                onConfirm={async (reason) => {
                  await unwrap(
                    api().POST("/api/v1/platform/tenants/{tenant_id}/reactivate/", {
                      ...path,
                      body: { reason },
                    }),
                  );
                  await refresh();
                }}
              />
            ) : null
          ) : null
        }
      />
      {notice ? <Alert className="mb-4">{notice}</Alert> : null}
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("tenancy.tenants.registry")}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">{t("tenancy.defaultLanguage")}</dt>
              <dd>{row.default_locale}</dd>
              <dt className="text-muted-foreground">{t("tenancy.timezone")}</dt>
              <dd>{row.timezone}</dd>
              <dt className="text-muted-foreground">{t("tenancy.currency")}</dt>
              <dd>{row.currency}</dd>
              <dt className="text-muted-foreground">{t("tenancy.created")}</dt>
              <dd>{format.dateTime(new Date(row.created_at), { dateStyle: "medium" })}</dd>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("tenancy.limits")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <p className="text-sm">
              {t("tenancy.limitsValue", {
                institutions: row.limits.max_institutions ?? 0,
                campuses: row.limits.max_campuses ?? 0,
              })}
            </p>
            {row.limits_override_reason ? (
              <p className="text-muted-foreground text-xs">
                {t("tenancy.tenants.overrideReason", { reason: row.limits_override_reason })}
              </p>
            ) : null}
            {can(me, "tenancy.limit.override") ? (
              <ReasonDialog
                trigger={t("tenancy.tenants.overrideLimits")}
                title={t("tenancy.tenants.overrideLimits")}
                description={t("tenancy.tenants.overrideHint")}
                confirm={t("common.save")}
                extra={
                  <div className="grid grid-cols-2 gap-3">
                    <Field id="max-institutions" label={t("tenancy.maxInstitutions")}>
                      {(aria) => (
                        <Input
                          type="number"
                          min={1}
                          inputMode="numeric"
                          value={limits.institutions}
                          onChange={(e) => setLimits({ ...limits, institutions: e.target.value })}
                          {...aria}
                        />
                      )}
                    </Field>
                    <Field id="max-campuses" label={t("tenancy.maxCampuses")}>
                      {(aria) => (
                        <Input
                          type="number"
                          min={1}
                          inputMode="numeric"
                          value={limits.campuses}
                          onChange={(e) => setLimits({ ...limits, campuses: e.target.value })}
                          {...aria}
                        />
                      )}
                    </Field>
                  </div>
                }
                onConfirm={async (reason) => {
                  await unwrap(
                    api().PUT("/api/v1/platform/tenants/{tenant_id}/limits/", {
                      ...path,
                      body: {
                        reason,
                        max_institutions:
                          Number(limits.institutions) || (row.limits.max_institutions ?? 1),
                        max_campuses: Number(limits.campuses) || (row.limits.max_campuses ?? 1),
                      },
                    }),
                  );
                  await refresh();
                }}
              />
            ) : null}
          </CardContent>
        </Card>
        {can(me, "tenancy.tenant.create") && row.status === "active" ? (
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>{t("tenancy.tenants.ownerInvitation")}</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                className="flex flex-wrap items-end gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (ownerEmail.includes("@")) void sendOwner();
                }}
              >
                <div className="min-w-64 flex-1">
                  <Field id="owner-email" label={t("tenancy.ownerEmail")}>
                    {(aria) => (
                      <Input
                        type="email"
                        value={ownerEmail}
                        onChange={(e) => setOwnerEmail(e.target.value)}
                        {...aria}
                      />
                    )}
                  </Field>
                </div>
                <Button type="submit" disabled={!ownerEmail.includes("@")}>
                  {t("tenancy.tenants.sendOwnerInvitation")}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </>
  );
}
