"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { useStepUp } from "@/components/auth/step-up";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { useErrorMessage } from "@/lib/auth/use-error-message";

export function UserDetail({ id }: { id: string }) {
  const t = useTranslations();
  const { data: me } = useMe();
  const { withStepUp } = useStepUp();
  const errorMessage = useErrorMessage();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [reason, setReason] = useState("");
  const [grantRole, setGrantRole] = useState("");
  const path = { params: { path: { user_id: id } } };
  const user = useQuery({
    queryKey: ["platform", "user", id],
    queryFn: () => unwrap(api().GET("/api/v1/platform/users/{user_id}/", path)),
  });
  const assignments = useQuery({
    queryKey: ["platform", "user", id, "roles"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/users/{user_id}/platform-roles/", path)),
  });
  const roles = useQuery({
    queryKey: ["platform", "roles"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/roles/")),
    enabled: can(me, "rbac.platform_role.assign") && can(me, "rbac.role.view"),
  });
  const done = (text: string) => {
    setMessage({ ok: true, text });
    void user.refetch();
    void assignments.refetch();
  };
  const action = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => withStepUp(fn),
    onError: (error) => setMessage({ ok: false, text: errorMessage(error) }),
  });
  const run = (fn: () => Promise<unknown>, text: string) =>
    action.mutate(fn, { onSuccess: () => done(text) });

  const u = user.data;
  if (user.isError) return <Alert variant="destructive">{errorMessage(user.error)}</Alert>;
  if (!u) return <p className="text-muted-foreground text-sm">{t("common.loading")}</p>;
  const platformRoles = (roles.data ?? []).filter((r) => r.kind === "platform");
  return (
    <>
      <PageHeader title={u.email} description={u.display_name || undefined} />
      {message ? (
        <Alert variant={message.ok ? "success" : "destructive"} className="mb-4">
          {message.text}
        </Alert>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("users.account")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <p>
              {t("users.status")}:{" "}
              {!u.is_active
                ? t("users.deactivated")
                : u.activated_at
                  ? t("users.active")
                  : t("users.pending")}
            </p>
            {"mfa_enabled" in u ? (
              <p>
                {t("account.mfa")}: {u.mfa_enabled ? t("common.on") : t("common.off")} ·{" "}
                {t("users.activeSessions", { count: u.active_sessions })}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {can(me, "identity.user.deactivate") ? (
                u.is_active ? (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() =>
                      run(
                        () =>
                          unwrap(api().POST("/api/v1/platform/users/{user_id}/deactivate/", path)),
                        t("users.deactivatedDone"),
                      )
                    }
                  >
                    {t("users.deactivate")}
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() =>
                      run(
                        () =>
                          unwrap(api().POST("/api/v1/platform/users/{user_id}/reactivate/", path)),
                        t("users.reactivatedDone"),
                      )
                    }
                  >
                    {t("users.reactivate")}
                  </Button>
                )
              ) : null}
              {can(me, "identity.session.revoke_any") ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    run(
                      () =>
                        unwrap(
                          api().POST("/api/v1/platform/users/{user_id}/sessions/revoke/", path),
                        ),
                      t("users.sessionsRevoked"),
                    )
                  }
                >
                  {t("users.revokeSessions")}
                </Button>
              ) : null}
              {can(me, "identity.user.create") && !u.activated_at ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    run(
                      () =>
                        unwrap(
                          api().POST("/api/v1/platform/users/{user_id}/activation/resend/", path),
                        ),
                      t("users.activationSent"),
                    )
                  }
                >
                  {t("users.resendActivation")}
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
        {can(me, "identity.mfa.reset") ? (
          <Card>
            <CardHeader>
              <CardTitle>{t("users.resetMfa")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <Field id="mfa-reset-reason" label={t("users.reason")} hint={t("users.reasonHint")}>
                {(aria) => (
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} {...aria} />
                )}
              </Field>
              <Button
                variant="destructive"
                size="sm"
                className="justify-self-start"
                disabled={reason.trim().length < 5}
                onClick={() =>
                  run(
                    () =>
                      unwrap(
                        api().POST("/api/v1/platform/users/{user_id}/mfa/reset/", {
                          ...path,
                          body: { reason },
                        }),
                      ),
                    t("users.mfaResetDone"),
                  )
                }
              >
                {t("users.resetMfa")}
              </Button>
            </CardContent>
          </Card>
        ) : null}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("users.platformRoles")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <ul className="divide-y rounded-md border">
              {(assignments.data ?? []).map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2 p-3 text-sm">
                  <span className="font-medium">{a.role_code}</span>
                  {can(me, "rbac.platform_role.assign") ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        run(
                          () =>
                            unwrap(
                              api().DELETE(
                                "/api/v1/platform/users/{user_id}/platform-roles/{assignment_id}/",
                                {
                                  params: { path: { user_id: id, assignment_id: a.id } },
                                },
                              ),
                            ),
                          t("users.roleRevoked"),
                        )
                      }
                    >
                      {t("account.revoke")}
                    </Button>
                  ) : null}
                </li>
              ))}
              {assignments.data?.length === 0 ? (
                <li className="text-muted-foreground p-3 text-sm">—</li>
              ) : null}
            </ul>
            {can(me, "rbac.platform_role.assign") && platformRoles.length ? (
              <div className="flex flex-wrap items-end gap-2">
                <Field id="grant-role" label={t("users.grantRole")}>
                  {(aria) => (
                    <select
                      className="bg-background h-10 rounded-md border px-3 text-sm"
                      value={grantRole}
                      onChange={(e) => setGrantRole(e.target.value)}
                      {...aria}
                    >
                      <option value="">—</option>
                      {platformRoles.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field id="grant-reason" label={t("users.reason")}>
                  {(aria) => (
                    <Input value={reason} onChange={(e) => setReason(e.target.value)} {...aria} />
                  )}
                </Field>
                <Button
                  disabled={!grantRole || reason.trim().length < 5}
                  onClick={() =>
                    run(
                      () =>
                        unwrap(
                          api().POST("/api/v1/platform/users/{user_id}/platform-roles/", {
                            ...path,
                            body: { role: grantRole, reason },
                          }),
                        ),
                      t("users.roleGranted"),
                    )
                  }
                >
                  {t("users.grant")}
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
