"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import {
  EMPTY_SCOPE,
  type Scope,
  ScopePicker,
  scopeBody,
  scopeComplete,
  useTenantRoles,
} from "@/components/tenancy/scope-picker";
import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useErrorMessage } from "@/lib/auth/use-error-message";
import { canAnywhere, localName, useTenantContext } from "@/lib/tenancy/context";

/** One member: status, role assignments in scopes, removal (plan §13.1). The API applies the
 * guard rails: no escalation, scope coverage, last owner, no acting on oneself. */
export function MemberDetail({ id = "" }: { id?: string }) {
  const t = useTranslations();
  const locale = useLocale();
  const format = useFormatter();
  const router = useRouter();
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const { run, failure } = useAction();
  const path = { params: { path: { member_id: id } } };
  const member = useQuery({
    queryKey: ["tenant", "member", id],
    queryFn: () => unwrap(api().GET("/api/v1/members/{member_id}/", path)),
  });
  const canAssign = canAnywhere(context, "rbac.assignment.view");
  const assignments = useQuery({
    queryKey: ["tenant", "member", id, "assignments"],
    queryFn: () => unwrap(api().GET("/api/v1/members/{member_id}/role-assignments/", path)),
    enabled: canAssign,
  });
  const roles = useTenantRoles(canAnywhere(context, "rbac.assignment.manage"));
  const [role, setRole] = useState("");
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tenant"] });
  const row = member.data;
  if (member.isError) return <Alert variant="destructive">{errorMessage(member.error)}</Alert>;
  if (!row) return null;
  const setStatus = (status: "active" | "suspended") =>
    run(async () => {
      await unwrap(api().PATCH("/api/v1/members/{member_id}/", { ...path, body: { status } }));
      await refresh();
    });
  const revoke = (assignmentId: string) =>
    run(async () => {
      await unwrap(
        api().DELETE("/api/v1/members/{member_id}/role-assignments/{assignment_id}/", {
          params: { path: { member_id: id, assignment_id: assignmentId } },
        }),
      );
      await refresh();
    });
  const scopeText = (a: { scope_type: string }) =>
    t(`tenancy.scope.${a.scope_type}` as "tenancy.scope.tenant");
  return (
    <>
      <PageHeader
        title={row.display_name || row.email}
        description={`${row.email} · ${t(`tenancy.status.${row.status}` as "tenancy.status.active")}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {canAnywhere(context, "tenancy.member.update") && row.status !== "left" ? (
              row.status === "suspended" ? (
                <Button variant="outline" onClick={() => void setStatus("active")}>
                  {t("tenancy.members.reactivate")}
                </Button>
              ) : (
                <Button variant="outline" onClick={() => void setStatus("suspended")}>
                  {t("tenancy.members.suspend")}
                </Button>
              )
            ) : null}
            {canAnywhere(context, "tenancy.member.remove") && row.status !== "left" ? (
              <ActionDialog
                trigger={<Button variant="destructive">{t("tenancy.members.remove")}</Button>}
                title={t("tenancy.members.remove")}
                description={t("tenancy.members.removeHint")}
                submit={t("tenancy.members.remove")}
                onSubmit={async () => {
                  await unwrap(api().DELETE("/api/v1/members/{member_id}/", path));
                  await refresh();
                  router.replace("/members");
                }}
              >
                {null}
              </ActionDialog>
            ) : null}
          </div>
        }
      />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      {canAssign ? (
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">{t("tenancy.members.assignments")}</h2>
            {canAnywhere(context, "rbac.assignment.manage") && row.status !== "left" ? (
              <ActionDialog
                trigger={<Button size="sm">{t("tenancy.members.grant")}</Button>}
                title={t("tenancy.members.grant")}
                description={t("tenancy.members.grantHint")}
                submit={t("tenancy.members.grant")}
                disabled={!role || !scopeComplete(scope)}
                onSubmit={async () => {
                  await unwrap(
                    api().POST("/api/v1/members/{member_id}/role-assignments/", {
                      ...path,
                      body: { role, ...scopeBody(scope), reason: "" },
                    }),
                  );
                  setRole("");
                  setScope(EMPTY_SCOPE);
                  await refresh();
                }}
              >
                <Field id="grant-role" label={t("tenancy.roleLabel")}>
                  {(aria) => (
                    <select
                      className={SELECT_CLASS}
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      {...aria}
                    >
                      <option value="">{t("tenancy.scope.choose")}</option>
                      {(roles.data ?? []).map((r) => (
                        <option key={r.id} value={r.id}>
                          {localName(r, locale)}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <ScopePicker value={scope} onChange={setScope} />
              </ActionDialog>
            ) : null}
          </div>
          <ul className="divide-y rounded-md border">
            {(assignments.data ?? []).map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <div>
                  <p className="font-medium">{a.role_name}</p>
                  <p className="text-muted-foreground text-xs">
                    {scopeText(a)} ·{" "}
                    {a.revoked_at
                      ? t("tenancy.members.revokedOn", {
                          date: format.dateTime(new Date(a.revoked_at), { dateStyle: "medium" }),
                        })
                      : t("tenancy.members.since", {
                          date: format.dateTime(new Date(a.valid_from), { dateStyle: "medium" }),
                        })}
                  </p>
                </div>
                {!a.revoked_at && canAnywhere(context, "rbac.assignment.manage") ? (
                  <Button variant="ghost" size="sm" onClick={() => void revoke(a.id)}>
                    {t("tenancy.members.revoke")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
