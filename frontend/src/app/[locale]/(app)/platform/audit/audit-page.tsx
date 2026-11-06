"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { useStepUp } from "@/components/auth/step-up";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { useErrorMessage } from "@/lib/auth/use-error-message";

function cursorOf(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return new URL(url, "http://x").searchParams.get("cursor") ?? undefined;
}

/** Audit log with masked IPs; reveal needs audit.event.view_ip + step-up and is itself audited. */
export function AuditPage() {
  const t = useTranslations();
  const { data: me } = useMe();
  const { withStepUp } = useStepUp();
  const errorMessage = useErrorMessage();
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const events = useQuery({
    queryKey: ["platform", "audit", action, outcome, cursor],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/platform/audit-events/", {
          params: { query: { action: action || undefined, outcome: outcome || undefined, cursor } },
        }),
      ),
  });
  const reveal = async (id: string) => {
    setFailure(null);
    try {
      const result = await withStepUp(() =>
        unwrap(
          api().POST("/api/v1/platform/audit-events/{event_id}/reveal-ip/", {
            params: { path: { event_id: id } },
          }),
        ),
      );
      setRevealed((r) => ({ ...r, [id]: result.ip }));
    } catch (error) {
      setFailure(errorMessage(error));
    }
  };
  const formatter = new Intl.DateTimeFormat(undefined, { dateStyle: "short", timeStyle: "medium" });
  return (
    <>
      <PageHeader title={t("audit.title")} description={t("audit.subtitle")} />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      <div className="mb-4 flex flex-wrap gap-4">
        <Field id="audit-action" label={t("audit.action")}>
          {(aria) => (
            <Input
              value={action}
              placeholder="identity.login.failed"
              onChange={(e) => {
                setAction(e.target.value.trim());
                setCursor(undefined);
              }}
              {...aria}
            />
          )}
        </Field>
        <Field id="audit-outcome" label={t("audit.outcome")}>
          {(aria) => (
            <select
              className="bg-background h-10 rounded-md border px-3 text-sm"
              value={outcome}
              onChange={(e) => {
                setOutcome(e.target.value);
                setCursor(undefined);
              }}
              {...aria}
            >
              <option value="">{t("audit.any")}</option>
              <option value="success">success</option>
              <option value="failure">failure</option>
              <option value="denied">denied</option>
            </select>
          )}
        </Field>
      </div>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr>
              <th scope="col" className="p-3 text-start">
                {t("audit.time")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("audit.action")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("audit.outcome")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("audit.actor")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("audit.ip")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(events.data?.results ?? []).map((e) => (
              <tr key={e.id} className="border-t align-top">
                <td className="p-3 whitespace-nowrap">
                  {formatter.format(new Date(e.occurred_at))}
                </td>
                <td className="p-3 font-mono text-xs">
                  {e.action}
                  {Object.keys(e.metadata as object).length ? (
                    <div className="text-muted-foreground mt-1">{JSON.stringify(e.metadata)}</div>
                  ) : null}
                </td>
                <td className="p-3">{e.outcome}</td>
                <td className="p-3 font-mono text-xs">{e.actor_user_id ?? e.actor_type}</td>
                <td className="p-3 whitespace-nowrap">
                  {revealed[e.id] ?? e.ip_masked}
                  {e.ip_masked && !revealed[e.id] && can(me, "audit.event.view_ip") ? (
                    <Button
                      size="sm"
                      variant="link"
                      className="ms-1 h-auto px-0"
                      onClick={() => void reveal(e.id)}
                    >
                      {t("audit.reveal")}
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!events.data?.previous}
          onClick={() => setCursor(cursorOf(events.data?.previous))}
        >
          {t("common.previous")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!events.data?.next}
          onClick={() => setCursor(cursorOf(events.data?.next))}
        >
          {t("common.next")}
        </Button>
      </div>
    </>
  );
}
