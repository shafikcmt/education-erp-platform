"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { useTenantRoles } from "@/components/tenancy/scope-picker";
import { ActionDialog, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canTenantWide, localName, useTenantContext } from "@/lib/tenancy/context";

/** Roles of this organisation (plan §13.1, Q5): system copies are read-only and stay in line
 * with their templates; "Clone" makes an editable copy. */
export function TenantRolesPage() {
  const t = useTranslations();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const roles = useTenantRoles();
  const { run, failure } = useAction();
  const [clone, setClone] = useState({ code: "", name: "" });
  const canClone = canTenantWide(context, "rbac.role.clone");
  const canDelete = canTenantWide(context, "rbac.role.delete");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tenant", "roles"] });
  return (
    <>
      <PageHeader title={t("tenancy.roles.title")} description={t("tenancy.roles.subtitle")} />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {(roles.data ?? []).map((role) => (
          <Card key={role.id}>
            <CardHeader>
              <CardTitle>
                {localName(role, locale)}{" "}
                <span className="text-muted-foreground text-xs font-normal">({role.code})</span>
              </CardTitle>
              <CardDescription>
                {role.is_system ? t("roles.system") : t("roles.custom")} ·{" "}
                {t("roles.permissionCount", { count: role.permissions.length })}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {role.permissions.length ? (
                <ul className="text-muted-foreground flex flex-wrap gap-1 text-xs">
                  {role.permissions.map((p) => (
                    <li key={p} className="bg-muted rounded px-2 py-0.5 font-mono">
                      {p}
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {canClone ? (
                  <ActionDialog
                    trigger={
                      <Button variant="outline" size="sm">
                        {t("tenancy.roles.clone")}
                      </Button>
                    }
                    title={t("tenancy.roles.clone")}
                    description={t("tenancy.roles.cloneHint")}
                    submit={t("tenancy.roles.clone")}
                    disabled={!/^[a-z][a-z0-9_]{2,63}$/.test(clone.code) || !clone.name.trim()}
                    onSubmit={async () => {
                      await unwrap(
                        api().POST("/api/v1/roles/{role_id}/clone/", {
                          params: { path: { role_id: role.id } },
                          body: { code: clone.code, name: clone.name.trim() },
                        }),
                      );
                      setClone({ code: "", name: "" });
                      await refresh();
                    }}
                  >
                    <Field id={`clone-name-${role.id}`} label={t("tenancy.roles.name")}>
                      {(aria) => (
                        <Input
                          value={clone.name}
                          onChange={(e) => setClone({ ...clone, name: e.target.value })}
                          {...aria}
                        />
                      )}
                    </Field>
                    <Field
                      id={`clone-code-${role.id}`}
                      label={t("tenancy.code")}
                      hint={t("tenancy.roles.codeHint")}
                    >
                      {(aria) => (
                        <Input
                          value={clone.code}
                          onChange={(e) => setClone({ ...clone, code: e.target.value })}
                          {...aria}
                        />
                      )}
                    </Field>
                  </ActionDialog>
                ) : null}
                {!role.is_system && canDelete ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      void run(async () => {
                        await unwrap(
                          api().DELETE("/api/v1/roles/{role_id}/", {
                            params: { path: { role_id: role.id } },
                          }),
                        );
                        await refresh();
                      })
                    }
                  >
                    {t("tenancy.roles.delete")}
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
