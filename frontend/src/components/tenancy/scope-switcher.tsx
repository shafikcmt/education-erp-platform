"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";

import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Field } from "@/components/ui/field";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { localName, type TenantContext } from "@/lib/tenancy/context";

export type ScopeKey = string; // "all" or the index of a scope in the context

/** Scope switcher (plan §13.1): "all my scopes", or one of the scopes the member holds a role
 * in. It narrows what the dashboard offers; the API decides every request on its own. */
export function ScopeSwitcher({
  context,
  value,
  onChange,
}: {
  context: TenantContext;
  value: ScopeKey;
  onChange: (value: ScopeKey) => void;
}) {
  const t = useTranslations("tenancy");
  const locale = useLocale();
  const institutions = useQuery({
    queryKey: ["tenant", "institutions"],
    queryFn: () => unwrap(api().GET("/api/v1/institutions/")),
    enabled: context.scopes.some((s) => s.institution),
  });
  const names = new Map((institutions.data ?? []).map((i) => [i.id, localName(i, locale)]));
  const label = (scope: TenantContext["scopes"][number]) => {
    if (scope.scope_type === "tenant") return t("scope.tenant");
    const institution =
      (scope.institution && names.get(scope.institution)) || t("scope.institution");
    return scope.scope_type === "campus" ? `${institution} · ${t("scope.campus")}` : institution;
  };
  if (context.scopes.length < 2) return null;
  return (
    <div className="mb-4 max-w-sm">
      <Field id="scope-switcher" label={t("scope.switcher")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            {...aria}
          >
            <option value="all">{t("scope.all")}</option>
            {context.scopes.map((scope, index) =>
              scope.permissions.length ? (
                <option key={`${scope.institution}-${scope.campus}`} value={String(index)}>
                  {label(scope)}
                </option>
              ) : null,
            )}
          </select>
        )}
      </Field>
    </div>
  );
}

/** Permissions of the selected scope (or of all scopes). */
export function scopePermissions(context: TenantContext | undefined, value: ScopeKey): Set<string> {
  if (!context) return new Set();
  const scopes = value === "all" ? context.scopes : [context.scopes[Number(value)]].filter(Boolean);
  return new Set(scopes.flatMap((scope) => scope?.permissions ?? []));
}
