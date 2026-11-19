"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ActionDialog, SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { INSTITUTION_TYPES } from "@/lib/tenancy/constants";
import { canTenantWide, localName, useTenantContext } from "@/lib/tenancy/context";

export const INSTITUTIONS_KEY = ["tenant", "institutions"] as const;

/** Institutions I can see (plan §13.1). The organisation's institution limit is enforced by
 * the API (`limit_exceeded`). */
export function InstitutionsPage() {
  const t = useTranslations();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const institutions = useQuery({
    queryKey: INSTITUTIONS_KEY,
    queryFn: () => unwrap(api().GET("/api/v1/institutions/")),
  });
  const [draft, setDraft] = useState({ code: "", name: "", institution_type: "school" });
  const valid = /^[a-z0-9_-]{1,32}$/.test(draft.code) && draft.name.trim().length >= 2;
  return (
    <>
      <PageHeader
        title={t("tenancy.institutions.title")}
        description={t("tenancy.institutions.subtitle")}
        actions={
          canTenantWide(context, "tenancy.institution.create") ? (
            <ActionDialog
              trigger={<Button>{t("tenancy.institutions.create")}</Button>}
              title={t("tenancy.institutions.create")}
              description={t("tenancy.institutions.limitHint")}
              submit={t("common.save")}
              disabled={!valid}
              onSubmit={async () => {
                await unwrap(
                  api().POST("/api/v1/institutions/", {
                    body: {
                      code: draft.code,
                      name: draft.name.trim(),
                      institution_type:
                        draft.institution_type as (typeof INSTITUTION_TYPES)[number],
                    },
                  }),
                );
                setDraft({ code: "", name: "", institution_type: "school" });
                await queryClient.invalidateQueries({ queryKey: INSTITUTIONS_KEY });
              }}
            >
              <Field id="i-name" label={t("tenancy.institutionName")}>
                {(aria) => (
                  <Input
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="i-code" label={t("tenancy.code")} hint={t("tenancy.codeHint")}>
                {(aria) => (
                  <Input
                    value={draft.code}
                    onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="i-type" label={t("tenancy.institutionType")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={draft.institution_type}
                    onChange={(e) => setDraft({ ...draft, institution_type: e.target.value })}
                    {...aria}
                  >
                    {INSTITUTION_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {t(`tenancy.types.${type}`)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </ActionDialog>
          ) : null
        }
      />
      <div className="grid gap-4 sm:grid-cols-2">
        {(institutions.data ?? []).map((row) => (
          <Link key={row.id} href={`/institutions/${row.id}`} className="rounded-xl">
            <Card className="hover:bg-accent/50 h-full transition-colors">
              <CardHeader>
                <CardTitle>{localName(row, locale)}</CardTitle>
                <CardDescription>
                  {t(`tenancy.types.${row.institution_type}`)} · {row.code}
                  {row.archived_at ? ` · ${t("tenancy.archived")}` : ""}
                </CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
