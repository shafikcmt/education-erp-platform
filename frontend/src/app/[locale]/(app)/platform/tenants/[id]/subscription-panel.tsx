"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ReasonDialog } from "@/components/tenancy/reason-dialog";
import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/** One tenant's plan, trial, add-ons and module overrides (P18; ADR-054). Every change needs
 * a reason and a fresh step-up; the API checks both and recomputes the entitlements. */
export function SubscriptionPanel({ tenantId }: { tenantId: string }) {
  const t = useTranslations("billing");
  const format = useFormatter();
  const { data: me } = useMe();
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const key = ["platform", "tenants", "subscription", tenantId];
  const path = { params: { path: { tenant_id: tenantId } } };
  const sub = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api().GET("/api/v1/platform/tenants/{tenant_id}/subscription/", path)),
  });
  const manage = can(me, "billing.subscription.manage");
  const plans = useQuery({
    queryKey: ["platform", "billing", "plans"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/plans/")),
    enabled: manage && can(me, "billing.plan.view"),
  });
  const addons = useQuery({
    queryKey: ["platform", "billing", "addons"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/addons/")),
    enabled: manage && can(me, "billing.plan.view"),
  });
  const [plan, setPlan] = useState("");
  const [days, setDays] = useState("14");
  const [addon, setAddon] = useState("");
  const [override, setOverride] = useState({ module: "", kind: "grant" });
  const save = (data: unknown) => queryClient.setQueryData(key, data);
  if (sub.isError) return <Alert variant="destructive">{errorMessage(sub.error)}</Alert>;
  const row = sub.data;
  if (!row) return null;
  const activePlans = (plans.data ?? []).filter((p) => !p.archived);
  const planSelect = (
    <Field id="sub-plan" label={t("plan")}>
      {(aria) => (
        <select
          className={SELECT_CLASS}
          value={plan}
          onChange={(e) => setPlan(e.target.value)}
          {...aria}
        >
          <option value="">{t("choose")}</option>
          {activePlans.map((p) => (
            <option key={p.code} value={p.code}>
              {p.name}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
  return (
    <Card className="md:col-span-2" data-testid="subscription-panel">
      <CardHeader>
        <CardTitle>{t("subscription")}</CardTitle>
        <CardDescription>{t("platform.subscriptionHint")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t("plan")}</dt>
          <dd data-testid="sub-plan-name">{row.plan ? row.plan.name : t("noPlan")}</dd>
          <dt className="text-muted-foreground">{t("status")}</dt>
          <dd>{row.status ? t(`statuses.${row.status}` as "statuses.active") : "-"}</dd>
          {row.trial_ends_at ? (
            <>
              <dt className="text-muted-foreground">{t("trialEnds")}</dt>
              <dd>{format.dateTime(new Date(row.trial_ends_at), { dateStyle: "medium" })}</dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">{t("enabledModules")}</dt>
          <dd className="text-xs">
            {row.modules
              .filter((m) => m.enabled)
              .map((m) => m.code)
              .join(", ")}
          </dd>
        </dl>
        {row.addons.length ? (
          <div className="grid gap-2 text-sm">
            <h3 className="font-medium">{t("addons")}</h3>
            <ul className="grid gap-2">
              {row.addons.map((a) => (
                <li key={a.code} className="flex flex-wrap items-center justify-between gap-2">
                  <span>{a.name}</span>
                  {manage ? (
                    <ReasonDialog
                      variant="destructive"
                      trigger={t("platform.removeAddon")}
                      title={t("platform.removeAddon")}
                      description={a.name}
                      confirm={t("platform.removeAddon")}
                      onConfirm={async (reason) =>
                        save(
                          await unwrap(
                            api().POST(
                              "/api/v1/platform/tenants/{tenant_id}/subscription/addons/{code}/remove/",
                              {
                                params: { path: { tenant_id: tenantId, code: a.code } },
                                body: { reason },
                              },
                            ),
                          ),
                        )
                      }
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {row.overrides.length ? (
          <div className="grid gap-2 text-sm">
            <h3 className="font-medium">{t("overrides")}</h3>
            <ul className="grid gap-2">
              {row.overrides.map((o) => (
                <li key={o.module} className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    <code className="text-xs">{o.module}</code> ·{" "}
                    {t(`kinds.${o.kind}` as "kinds.grant")} · {o.reason}
                  </span>
                  {manage ? (
                    <ReasonDialog
                      trigger={t("platform.endOverride")}
                      title={t("platform.endOverride")}
                      description={o.module}
                      confirm={t("platform.endOverride")}
                      onConfirm={async (reason) =>
                        save(
                          await unwrap(
                            api().POST(
                              "/api/v1/platform/tenants/{tenant_id}/subscription/overrides/{module}/end/",
                              {
                                params: { path: { tenant_id: tenantId, module: o.module } },
                                body: { reason },
                              },
                            ),
                          ),
                        )
                      }
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {manage ? (
          <div className="flex flex-wrap gap-2">
            <ReasonDialog
              trigger={t("platform.assignPlan")}
              title={t("platform.assignPlan")}
              description={t("platform.assignPlanHint")}
              confirm={t("platform.assignPlan")}
              extra={planSelect}
              onConfirm={async (reason) =>
                save(
                  await unwrap(
                    api().POST("/api/v1/platform/tenants/{tenant_id}/subscription/plan/", {
                      ...path,
                      body: { plan, reason },
                    }),
                  ),
                )
              }
            />
            <ReasonDialog
              trigger={t("platform.startTrial")}
              title={t("platform.startTrial")}
              description={t("platform.startTrialHint")}
              confirm={t("platform.startTrial")}
              extra={
                <>
                  {planSelect}
                  <Field id="sub-days" label={t("trialLength")}>
                    {(aria) => (
                      <Input
                        type="number"
                        min={1}
                        max={365}
                        inputMode="numeric"
                        value={days}
                        onChange={(e) => setDays(e.target.value)}
                        {...aria}
                      />
                    )}
                  </Field>
                </>
              }
              onConfirm={async (reason) =>
                save(
                  await unwrap(
                    api().POST("/api/v1/platform/tenants/{tenant_id}/subscription/trial/", {
                      ...path,
                      body: { plan, days: Number(days), reason },
                    }),
                  ),
                )
              }
            />
            <ReasonDialog
              trigger={t("platform.addAddon")}
              title={t("platform.addAddon")}
              description={t("platform.addAddonHint")}
              confirm={t("platform.addAddon")}
              extra={
                <Field id="sub-addon" label={t("addon")}>
                  {(aria) => (
                    <select
                      className={SELECT_CLASS}
                      value={addon}
                      onChange={(e) => setAddon(e.target.value)}
                      {...aria}
                    >
                      <option value="">{t("choose")}</option>
                      {(addons.data ?? [])
                        .filter((a) => !a.archived)
                        .map((a) => (
                          <option key={a.code} value={a.code}>
                            {a.name}
                          </option>
                        ))}
                    </select>
                  )}
                </Field>
              }
              onConfirm={async (reason) =>
                save(
                  await unwrap(
                    api().POST("/api/v1/platform/tenants/{tenant_id}/subscription/addons/", {
                      ...path,
                      body: { addon, reason },
                    }),
                  ),
                )
              }
            />
            <ReasonDialog
              trigger={t("platform.setOverride")}
              title={t("platform.setOverride")}
              description={t("platform.setOverrideHint")}
              confirm={t("platform.setOverride")}
              extra={
                <div className="grid grid-cols-2 gap-3">
                  <Field id="ov-module" label={t("module")}>
                    {(aria) => (
                      <select
                        className={SELECT_CLASS}
                        value={override.module}
                        onChange={(e) => setOverride({ ...override, module: e.target.value })}
                        {...aria}
                      >
                        <option value="">{t("choose")}</option>
                        {row.modules
                          .filter((m) => m.source !== "platform")
                          .map((m) => m.code)
                          .concat((addons.data ?? []).flatMap((a) => (a.module ? [a.module] : [])))
                          .filter((c, i, all) => all.indexOf(c) === i)
                          .sort()
                          .map((code) => (
                            <option key={code} value={code}>
                              {code}
                            </option>
                          ))}
                      </select>
                    )}
                  </Field>
                  <Field id="ov-kind" label={t("kind")}>
                    {(aria) => (
                      <select
                        className={SELECT_CLASS}
                        value={override.kind}
                        onChange={(e) => setOverride({ ...override, kind: e.target.value })}
                        {...aria}
                      >
                        <option value="grant">{t("kinds.grant")}</option>
                        <option value="revoke">{t("kinds.revoke")}</option>
                      </select>
                    )}
                  </Field>
                </div>
              }
              onConfirm={async (reason) =>
                save(
                  await unwrap(
                    api().POST("/api/v1/platform/tenants/{tenant_id}/subscription/overrides/", {
                      ...path,
                      body: {
                        module: override.module,
                        kind: override.kind as "grant",
                        reason,
                      },
                    }),
                  ),
                )
              }
            />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
