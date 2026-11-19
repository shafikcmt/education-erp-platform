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
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, localName, useTenantContext } from "@/lib/tenancy/context";

const INVITATIONS_KEY = ["tenant", "invitations"];

function InviteDialog() {
  const t = useTranslations();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const roles = useTenantRoles();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const valid = email.includes("@") && Boolean(role) && scopeComplete(scope);
  return (
    <ActionDialog
      trigger={<Button>{t("tenancy.members.invite")}</Button>}
      title={t("tenancy.members.invite")}
      description={t("tenancy.members.inviteHint")}
      submit={t("tenancy.members.sendInvite")}
      disabled={!valid}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/invitations/", {
            body: { email: email.trim(), role, ...scopeBody(scope) },
          }),
        );
        setEmail("");
        setRole("");
        setScope(EMPTY_SCOPE);
        await queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY });
      }}
    >
      <Field id="inv-email" label={t("auth.email")}>
        {(aria) => (
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} {...aria} />
        )}
      </Field>
      <Field id="inv-role" label={t("tenancy.roleLabel")}>
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
  );
}

/** Members I can see, their status, and open invitations (plan §13.1). */
export function MembersPage() {
  const t = useTranslations();
  const format = useFormatter();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const { run, failure } = useAction();
  const canInvite = canAnywhere(context, "tenancy.member.invite");
  const members = useQuery({
    queryKey: ["tenant", "members"],
    queryFn: () => unwrap(api().GET("/api/v1/members/")),
  });
  const invitations = useQuery({
    queryKey: INVITATIONS_KEY,
    queryFn: () => unwrap(api().GET("/api/v1/invitations/")),
    enabled: canInvite,
  });
  const invitationAction = (id: string, kind: "resend" | "revoke") =>
    run(async () => {
      const params = { params: { path: { invitation_id: id } } };
      if (kind === "resend") {
        await unwrap(api().POST("/api/v1/invitations/{invitation_id}/resend/", params));
      } else {
        await unwrap(api().DELETE("/api/v1/invitations/{invitation_id}/", params));
      }
      await queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY });
    });
  return (
    <>
      <PageHeader
        title={t("tenancy.members.title")}
        description={t("tenancy.members.subtitle")}
        actions={canInvite ? <InviteDialog /> : null}
      />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      <div className="mb-8 overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.members.person")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.statusLabel")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.members.joined")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(members.data ?? []).map((m) => (
              <tr key={m.id} className="border-t">
                <td className="p-3">
                  <Link href={`/members/${m.id}`} className="font-medium underline">
                    {m.display_name || m.email}
                  </Link>
                  {m.display_name ? (
                    <span className="text-muted-foreground block text-xs">{m.email}</span>
                  ) : null}
                </td>
                <td className="p-3">
                  {t(`tenancy.status.${m.status}` as "tenancy.status.active")}
                </td>
                <td className="p-3 text-xs">
                  {m.joined_at
                    ? format.dateTime(new Date(m.joined_at), { dateStyle: "medium" })
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canInvite ? (
        <section>
          <h2 className="mb-3 text-lg font-semibold">{t("tenancy.members.openInvitations")}</h2>
          {invitations.isSuccess && !invitations.data.length ? (
            <p className="text-muted-foreground text-sm">{t("tenancy.members.noInvitations")}</p>
          ) : null}
          <ul className="divide-y rounded-md border">
            {(invitations.data ?? []).map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <div>
                  <p className="font-medium">{inv.email}</p>
                  <p className="text-muted-foreground text-xs">
                    {inv.role_code} ·{" "}
                    {t(`tenancy.scope.${inv.scope_type}` as "tenancy.scope.tenant")} ·{" "}
                    {t("tenancy.members.expires", {
                      date: format.dateTime(new Date(inv.expires_at), { dateStyle: "medium" }),
                    })}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void invitationAction(inv.id, "resend")}
                  >
                    {t("tenancy.members.resend")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void invitationAction(inv.id, "revoke")}
                  >
                    {t("tenancy.members.revoke")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
