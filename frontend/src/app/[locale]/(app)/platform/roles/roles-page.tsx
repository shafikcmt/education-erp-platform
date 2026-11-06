"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";

import { PageHeader } from "@/components/app/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";

/** Roles + permission catalog (plan §9). System roles are read-only (enforced by the API). */
export function RolesPage() {
  const t = useTranslations();
  const locale = useLocale();
  const { data: me } = useMe();
  const roles = useQuery({
    queryKey: ["platform", "roles"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/roles/")),
  });
  const catalog = useQuery({
    queryKey: ["platform", "permissions"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/permissions/")),
    enabled: can(me, "rbac.permission.view"),
  });
  const name = (r: { name: string; name_i18n: unknown }) =>
    (r.name_i18n as Record<string, string> | null)?.[locale] ?? r.name;
  const groups = [
    { kind: "platform", title: t("roles.platform") },
    { kind: "template", title: t("roles.templates") },
  ];
  return (
    <>
      <PageHeader title={t("roles.title")} description={t("roles.subtitle")} />
      {groups.map((group) => (
        <section key={group.kind} className="mb-8">
          <h2 className="mb-3 text-lg font-semibold">{group.title}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {(roles.data ?? [])
              .filter((r) => r.kind === group.kind)
              .map((r) => (
                <Card key={r.id}>
                  <CardHeader>
                    <CardTitle>
                      {name(r)}{" "}
                      <span className="text-muted-foreground text-xs font-normal">({r.code})</span>
                    </CardTitle>
                    <CardDescription>
                      {r.is_system ? t("roles.system") : t("roles.custom")} ·{" "}
                      {t("roles.permissionCount", { count: r.permissions.length })}
                    </CardDescription>
                  </CardHeader>
                  {r.permissions.length ? (
                    <CardContent>
                      <ul className="text-muted-foreground flex flex-wrap gap-1 text-xs">
                        {r.permissions.map((p) => (
                          <li key={p} className="bg-muted rounded px-2 py-0.5 font-mono">
                            {p}
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  ) : null}
                </Card>
              ))}
          </div>
        </section>
      ))}
      {catalog.data ? (
        <section>
          <h2 className="mb-3 text-lg font-semibold">{t("roles.catalog")}</h2>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr>
                  <th scope="col" className="p-3 text-start">
                    {t("roles.code")}
                  </th>
                  <th scope="col" className="p-3 text-start">
                    {t("roles.description")}
                  </th>
                  <th scope="col" className="p-3 text-start">
                    {t("roles.flags")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {catalog.data.map((p) => (
                  <tr key={p.code} className="border-t">
                    <td className="p-3 font-mono text-xs">{p.code}</td>
                    <td className="p-3">{p.description}</td>
                    <td className="p-3 text-xs">
                      {[
                        p.requires_mfa && "MFA",
                        p.requires_step_up && t("roles.stepUp"),
                        p.is_sensitive && t("roles.sensitive"),
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}
