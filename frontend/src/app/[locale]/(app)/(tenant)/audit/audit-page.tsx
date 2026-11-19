"use client";

import { useQuery } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canTenantWide, useTenantContext } from "@/lib/tenancy/context";

/** This organisation's audit log (plan §13.1). IPs are masked; revealing one needs a fresh
 * step-up and is itself audited. */
export function TenantAuditPage() {
  const t = useTranslations();
  const format = useFormatter();
  const { data: context } = useTenantContext();
  const { run, failure } = useAction();
  const [cursor, setCursor] = useState<string | undefined>();
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const events = useQuery({
    queryKey: ["tenant", "audit", cursor],
    queryFn: () => unwrap(api().GET("/api/v1/audit-events/", { params: { query: { cursor } } })),
  });
  const reveal = (id: string) =>
    run(async () => {
      const result = await unwrap(
        api().POST("/api/v1/audit-events/{event_id}/reveal-ip/", {
          params: { path: { event_id: id } },
        }),
      );
      setRevealed((current) => ({ ...current, [id]: result.ip }));
    });
  const next = events.data?.next ? new URL(events.data.next).searchParams.get("cursor") : null;
  const canReveal = canTenantWide(context, "audit.event.view_ip");
  return (
    <>
      <PageHeader title={t("audit.title")} description={t("tenancy.audit.subtitle")} />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
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
                {t("audit.ip")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(events.data?.results ?? []).map((e) => (
              <tr key={e.id} className="border-t">
                <td className="p-3 text-xs">
                  {format.dateTime(new Date(e.occurred_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </td>
                <td className="p-3 font-mono text-xs">{e.action}</td>
                <td className="p-3 text-xs">{e.outcome}</td>
                <td className="p-3 text-xs">
                  {revealed[e.id] ?? e.ip_masked}
                  {canReveal && e.ip_masked && !revealed[e.id] ? (
                    <Button variant="ghost" size="sm" onClick={() => void reveal(e.id)}>
                      {t("audit.reveal")}
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {next ? (
        <Button variant="outline" className="mt-4" onClick={() => setCursor(next)}>
          {t("tenancy.audit.older")}
        </Button>
      ) : null}
    </>
  );
}
