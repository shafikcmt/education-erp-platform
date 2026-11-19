"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";

import { PageHeader } from "@/components/app/page-header";
import { useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { CONTEXT_KEY, canTenantWide, useTenantContext } from "@/lib/tenancy/context";

const KEY = ["tenant", "support-sessions"];
const OPEN = new Set(["requested", "approved", "active"]);

/** Requested and active support sessions, decisions and history (plan §11, §13.1). Support
 * access is read-only and time-limited; approving needs a fresh step-up. */
export function SupportAccessPage() {
  const t = useTranslations();
  const format = useFormatter();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const { run, failure } = useAction();
  const sessions = useQuery({
    queryKey: KEY,
    queryFn: () => unwrap(api().GET("/api/v1/support-sessions/")),
  });
  const decide = (id: string, kind: "approve" | "reject" | "revoke") =>
    run(async () => {
      const params = { params: { path: { session_id: id } } };
      if (kind === "approve") {
        await unwrap(api().POST("/api/v1/support-sessions/{session_id}/approve/", params));
      } else if (kind === "reject") {
        await unwrap(api().POST("/api/v1/support-sessions/{session_id}/reject/", params));
      } else {
        await unwrap(api().POST("/api/v1/support-sessions/{session_id}/revoke/", params));
      }
      await queryClient.invalidateQueries({ queryKey: KEY });
      await queryClient.invalidateQueries({ queryKey: CONTEXT_KEY });
    });
  const canApprove = canTenantWide(context, "tenancy.support_session.approve");
  const canRevoke = canTenantWide(context, "tenancy.support_session.revoke");
  const when = (value: string | null) =>
    value ? format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" }) : "—";
  return (
    <>
      <PageHeader title={t("tenancy.support.title")} description={t("tenancy.support.subtitle")} />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      {sessions.isSuccess && !sessions.data.length ? (
        <p className="text-muted-foreground text-sm">{t("tenancy.support.none")}</p>
      ) : null}
      <ul className="grid gap-3">
        {(sessions.data ?? []).map((s) => (
          <li key={s.id} className="rounded-md border p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="grid gap-1">
                <p className="font-medium">
                  {t(`tenancy.support.status.${s.status}` as "tenancy.support.status.active")} ·{" "}
                  {s.ticket_ref}
                </p>
                <p className="text-sm">{s.reason}</p>
                <p className="text-muted-foreground text-xs">
                  {t("tenancy.support.requestedAt", { date: when(s.requested_at) })} ·{" "}
                  {t("tenancy.support.minutesValue", { minutes: s.duration_minutes })}
                  {s.starts_at ? ` · ${when(s.starts_at)} – ${when(s.ends_at)}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {s.status === "requested" && canApprove ? (
                  <>
                    <Button size="sm" onClick={() => void decide(s.id, "approve")}>
                      {t("tenancy.support.approve")}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void decide(s.id, "reject")}>
                      {t("tenancy.support.reject")}
                    </Button>
                  </>
                ) : null}
                {OPEN.has(s.status) && canRevoke ? (
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => void decide(s.id, "revoke")}
                  >
                    {t("tenancy.support.revoke")}
                  </Button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
