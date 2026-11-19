"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { useStepUp } from "@/components/auth/step-up";
import { PageHeader } from "@/components/app/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useErrorMessage } from "@/lib/auth/use-error-message";

const OPEN = new Set(["requested", "approved", "active"]);

/** Platform staff: request read-only support access to one tenant, list and end their own
 * sessions (P6, plan §11). Tenant data is read on the tenant host, never here. */
export function OwnSupportSessions() {
  const t = useTranslations();
  const format = useFormatter();
  const errorMessage = useErrorMessage();
  const { withStepUp } = useStepUp();
  const queryClient = useQueryClient();
  const key = ["platform", "support-sessions"];
  const sessions = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api().GET("/api/v1/platform/support-sessions/")),
  });
  // Support staff hold tenancy.tenant.view_any, so the tenant is picked from the registry.
  const registry = useQuery({
    queryKey: ["platform", "tenants", "active"],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/platform/tenants/", {
          params: { query: { status: "active", page_size: 100 } },
        }),
      ),
  });
  const [form, setForm] = useState({ tenant: "", reason: "", ticket_ref: "", minutes: "60" });
  const [failure, setFailure] = useState<string | null>(null);
  const valid =
    /^[0-9a-f-]{36}$/i.test(form.tenant.trim()) &&
    form.reason.trim().length >= 10 &&
    form.ticket_ref.trim().length > 0;
  const request = async () => {
    setFailure(null);
    try {
      await withStepUp(() =>
        unwrap(
          api().POST("/api/v1/platform/support-sessions/", {
            body: {
              tenant: form.tenant.trim(),
              reason: form.reason.trim(),
              ticket_ref: form.ticket_ref.trim(),
              minutes: Number(form.minutes),
            },
          }),
        ),
      );
      setForm({ tenant: "", reason: "", ticket_ref: "", minutes: "60" });
      await queryClient.invalidateQueries({ queryKey: key });
    } catch (error) {
      setFailure(errorMessage(error));
    }
  };
  const end = async (sessionId: string) => {
    setFailure(null);
    try {
      await withStepUp(() =>
        unwrap(
          api().POST("/api/v1/platform/support-sessions/{session_id}/end/", {
            params: { path: { session_id: sessionId } },
          }),
        ),
      );
      await queryClient.invalidateQueries({ queryKey: key });
    } catch (error) {
      setFailure(errorMessage(error));
    }
  };
  const when = (value: string | null) =>
    value ? format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" }) : "—";
  return (
    <>
      <PageHeader
        title={t("tenancy.support.ownTitle")}
        description={t("tenancy.support.ownSubtitle")}
      />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>{t("tenancy.support.request")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-2"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              if (valid) void request();
            }}
          >
            <Field id="s-tenant" label={t("tenancy.support.tenant")}>
              {(aria) => (
                <select
                  className="bg-background h-10 rounded-md border px-3 text-sm"
                  value={form.tenant}
                  onChange={(e) => setForm({ ...form, tenant: e.target.value })}
                  {...aria}
                >
                  <option value="">{t("tenancy.support.chooseTenant")}</option>
                  {(registry.data?.results ?? []).map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name} ({row.slug})
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field id="s-ticket" label={t("tenancy.support.ticket")}>
              {(aria) => (
                <Input
                  value={form.ticket_ref}
                  maxLength={64}
                  onChange={(e) => setForm({ ...form, ticket_ref: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="s-reason" label={t("tenancy.reason")} hint={t("tenancy.reasonHint")}>
              {(aria) => (
                <Input
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="s-minutes" label={t("tenancy.support.minutes")}>
              {(aria) => (
                <select
                  className="bg-background h-10 rounded-md border px-3 text-sm"
                  value={form.minutes}
                  onChange={(e) => setForm({ ...form, minutes: e.target.value })}
                  {...aria}
                >
                  {[15, 30, 60, 120].map((m) => (
                    <option key={m} value={m}>
                      {t("tenancy.support.minutesValue", { minutes: m })}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={!valid}>
                {t("tenancy.support.request")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.slug")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.statusLabel")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.support.window")}
              </th>
              <th scope="col" className="p-3 text-start">
                <span className="sr-only">{t("tenancy.actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {(sessions.data ?? []).map((row) => (
              <tr key={row.session_id} className="border-t">
                <td className="p-3 font-mono text-xs">{row.tenant_slug}</td>
                <td className="p-3">
                  {t(`tenancy.support.status.${row.status}` as "tenancy.support.status.active")}
                </td>
                <td className="p-3 text-xs">
                  {when(row.starts_at)} – {when(row.ends_at)}
                </td>
                <td className="p-3 text-end">
                  {OPEN.has(row.status) ? (
                    <Button variant="outline" size="sm" onClick={() => void end(row.session_id)}>
                      {t("tenancy.support.end")}
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
