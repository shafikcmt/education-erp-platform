"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";

import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Field } from "@/components/ui/field";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { localName } from "@/lib/tenancy/context";

export type Scope = {
  scope_type: "tenant" | "institution" | "campus";
  institution: string;
  campus: string;
};
export const EMPTY_SCOPE: Scope = { scope_type: "tenant", institution: "", campus: "" };

export function scopeBody(scope: Scope) {
  return {
    scope_type: scope.scope_type,
    institution: scope.scope_type === "tenant" ? null : scope.institution || null,
    campus: scope.scope_type === "campus" ? scope.campus || null : null,
  };
}

export function scopeComplete(scope: Scope): boolean {
  if (scope.scope_type === "tenant") return true;
  if (!scope.institution) return false;
  return scope.scope_type === "institution" || Boolean(scope.campus);
}

/** Scope picker for a role (plan §13.1): whole organisation, one institution, or one campus.
 * Only institutions and campuses I can see are offered; the API checks the rest. */
export function ScopePicker({ value, onChange }: { value: Scope; onChange: (s: Scope) => void }) {
  const t = useTranslations("tenancy");
  const locale = useLocale();
  const institutions = useQuery({
    queryKey: ["tenant", "institutions"],
    queryFn: () => unwrap(api().GET("/api/v1/institutions/")),
  });
  const campuses = useQuery({
    queryKey: ["tenant", "institution", value.institution, "campuses"],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/institutions/{institution_id}/campuses/", {
          params: { path: { institution_id: value.institution } },
        }),
      ),
    enabled: value.scope_type === "campus" && Boolean(value.institution),
  });
  return (
    <>
      <Field id="scope-type" label={t("scope.label")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={value.scope_type}
            onChange={(e) =>
              onChange({ ...EMPTY_SCOPE, scope_type: e.target.value as Scope["scope_type"] })
            }
            {...aria}
          >
            <option value="tenant">{t("scope.tenant")}</option>
            <option value="institution">{t("scope.institution")}</option>
            <option value="campus">{t("scope.campus")}</option>
          </select>
        )}
      </Field>
      {value.scope_type !== "tenant" ? (
        <Field id="scope-institution" label={t("scope.institution")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={value.institution}
              onChange={(e) => onChange({ ...value, institution: e.target.value, campus: "" })}
              {...aria}
            >
              <option value="">{t("scope.choose")}</option>
              {(institutions.data ?? [])
                .filter((i) => !i.archived_at)
                .map((i) => (
                  <option key={i.id} value={i.id}>
                    {localName(i, locale)}
                  </option>
                ))}
            </select>
          )}
        </Field>
      ) : null}
      {value.scope_type === "campus" && value.institution ? (
        <Field id="scope-campus" label={t("scope.campus")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={value.campus}
              onChange={(e) => onChange({ ...value, campus: e.target.value })}
              {...aria}
            >
              <option value="">{t("scope.choose")}</option>
              {(campuses.data ?? [])
                .filter((c) => !c.archived_at)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {localName(c, locale)}
                  </option>
                ))}
            </select>
          )}
        </Field>
      ) : null}
    </>
  );
}

/** Tenant roles to offer in role pickers. */
export function useTenantRoles(enabled = true) {
  return useQuery({
    queryKey: ["tenant", "roles"],
    queryFn: () => unwrap(api().GET("/api/v1/roles/")),
    enabled,
  });
}
