"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

const STATUSES = ["verified", "pending", "approved", "rejected", "expired"] as const;

/** Sign-up requests (Phase 5 M8): provisioners approve verified requests (P4, the owner is
 * invited) or reject open ones with a reason. */
export function PlatformSignups() {
  const t = useTranslations();
  const format = useFormatter();
  const queryClient = useQueryClient();
  const { run, failure } = useAction();
  const [status, setStatus] = useState<string>("verified");
  const [reason, setReason] = useState("");
  const key = ["platform", "signups", status];
  const rows = useQuery({
    queryKey: key,
    queryFn: () =>
      unwrap(api().GET("/api/v1/platform/signups/", { params: { query: { status } } })),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["platform", "signups"] });
  const approve = (id: string) =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/platform/signups/{signup_id}/approve/", {
          params: { path: { signup_id: id } },
        }),
      );
      await refresh();
    });
  return (
    <>
      <PageHeader title={t("signup.admin.title")} description={t("signup.admin.subtitle")} />
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field id="signup-status" label={t("signup.admin.status")}>
        {(aria) => (
          <select
            className={`${SELECT_CLASS} mb-4`}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            {...aria}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`signup.admin.statuses.${s}`)}
              </option>
            ))}
          </select>
        )}
      </Field>
      {rows.data?.length ? (
        <div className="grid gap-3" data-testid="signups">
          {rows.data.map((row) => (
            <Card key={row.id}>
              <CardContent className="flex flex-wrap items-start justify-between gap-3 pt-6 text-sm">
                <div>
                  <p className="font-medium">
                    {row.organisation_name}{" "}
                    <code className="text-muted-foreground text-xs">{row.slug}</code>
                  </p>
                  <p className="text-muted-foreground">
                    {t(`tenancy.types.${row.institution_type}` as "tenancy.types.school")} ·{" "}
                    {row.institution_name}
                  </p>
                  <p className="text-muted-foreground">
                    {row.email} · {row.default_locale} · {row.timezone} · {row.currency}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {format.dateTime(new Date(row.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                    {row.decision_reason ? ` · ${row.decision_reason}` : ""}
                  </p>
                </div>
                {row.status === "verified" || row.status === "pending" ? (
                  <div className="flex gap-2">
                    {row.status === "verified" ? (
                      <Button size="sm" onClick={() => void approve(row.id)}>
                        {t("signup.admin.approve")}
                      </Button>
                    ) : null}
                    <ActionDialog
                      trigger={
                        <Button size="sm" variant="outline">
                          {t("signup.admin.reject")}
                        </Button>
                      }
                      title={t("signup.admin.reject")}
                      submit={t("signup.admin.reject")}
                      disabled={reason.trim().length < 10}
                      onSubmit={async () => {
                        await unwrap(
                          api().POST("/api/v1/platform/signups/{signup_id}/reject/", {
                            params: { path: { signup_id: row.id } },
                            body: { reason: reason.trim() },
                          }),
                        );
                        setReason("");
                        await refresh();
                      }}
                    >
                      <Field
                        id={`reject-${row.id}`}
                        label={t("signup.admin.reason")}
                        hint={t("signup.admin.reasonHint")}
                      >
                        {(aria) => (
                          <Input
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            {...aria}
                          />
                        )}
                      </Field>
                    </ActionDialog>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">{t("signup.admin.empty")}</p>
      )}
    </>
  );
}
