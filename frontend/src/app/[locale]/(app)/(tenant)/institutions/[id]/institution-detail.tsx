"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ActionDialog, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useErrorMessage } from "@/lib/auth/use-error-message";
import { canAnywhere, localName, useTenantContext } from "@/lib/tenancy/context";

/** One institution and its campuses (plan §13.1). Every action is checked by the API in the
 * scope of its object; the buttons only follow what the context says I may do somewhere. */
export function InstitutionDetail({ id = "" }: { id?: string }) {
  const t = useTranslations();
  const locale = useLocale();
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const { run, failure } = useAction();
  const path = { params: { path: { institution_id: id } } };
  const institution = useQuery({
    queryKey: ["tenant", "institution", id],
    queryFn: () => unwrap(api().GET("/api/v1/institutions/{institution_id}/", path)),
  });
  const campuses = useQuery({
    queryKey: ["tenant", "institution", id, "campuses"],
    queryFn: () => unwrap(api().GET("/api/v1/institutions/{institution_id}/campuses/", path)),
  });
  const [name, setName] = useState("");
  const [campus, setCampus] = useState({ code: "", name: "" });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tenant"] });
  const row = institution.data;
  if (institution.isError) {
    return <Alert variant="destructive">{errorMessage(institution.error)}</Alert>;
  }
  if (!row) return null;
  const archived = Boolean(row.archived_at);
  const campusAction = (campusId: string, kind: "main" | "archive") =>
    run(async () => {
      const params = { params: { path: { campus_id: campusId } } };
      if (kind === "main") {
        await unwrap(
          api().PATCH("/api/v1/campuses/{campus_id}/", { ...params, body: { make_main: true } }),
        );
      } else {
        await unwrap(api().POST("/api/v1/campuses/{campus_id}/archive/", params));
      }
      await refresh();
    });
  return (
    <>
      <PageHeader
        title={localName(row, locale)}
        description={`${t(`tenancy.types.${row.institution_type}`)} · ${row.code}${archived ? ` · ${t("tenancy.archived")}` : ""}`}
        actions={
          archived ? null : (
            <div className="flex flex-wrap gap-2">
              {canAnywhere(context, "tenancy.institution.update") ? (
                <ActionDialog
                  trigger={<Button variant="outline">{t("tenancy.rename")}</Button>}
                  title={t("tenancy.rename")}
                  submit={t("common.save")}
                  disabled={name.trim().length < 2}
                  onSubmit={async () => {
                    await unwrap(
                      api().PATCH("/api/v1/institutions/{institution_id}/", {
                        ...path,
                        body: { name: name.trim() },
                      }),
                    );
                    setName("");
                    await refresh();
                  }}
                >
                  <Field id="rename" label={t("tenancy.institutionName")}>
                    {(aria) => (
                      <Input value={name} onChange={(e) => setName(e.target.value)} {...aria} />
                    )}
                  </Field>
                </ActionDialog>
              ) : null}
              {canAnywhere(context, "tenancy.institution.archive") ? (
                <ActionDialog
                  trigger={<Button variant="destructive">{t("tenancy.archive")}</Button>}
                  title={t("tenancy.archive")}
                  description={t("tenancy.institutions.archiveHint")}
                  submit={t("tenancy.archive")}
                  onSubmit={async () => {
                    await unwrap(
                      api().POST("/api/v1/institutions/{institution_id}/archive/", path),
                    );
                    await refresh();
                  }}
                >
                  {null}
                </ActionDialog>
              ) : null}
            </div>
          )
        }
      />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{t("tenancy.campuses.title")}</h2>
          {!archived && canAnywhere(context, "tenancy.campus.create") ? (
            <ActionDialog
              trigger={<Button size="sm">{t("tenancy.campuses.create")}</Button>}
              title={t("tenancy.campuses.create")}
              description={t("tenancy.campuses.limitHint")}
              submit={t("common.save")}
              disabled={!/^[a-z0-9_-]{1,32}$/.test(campus.code) || campus.name.trim().length < 2}
              onSubmit={async () => {
                await unwrap(
                  api().POST("/api/v1/institutions/{institution_id}/campuses/", {
                    ...path,
                    body: { code: campus.code, name: campus.name.trim(), timezone: "" },
                  }),
                );
                setCampus({ code: "", name: "" });
                await refresh();
              }}
            >
              <Field id="c-name" label={t("tenancy.campuses.name")}>
                {(aria) => (
                  <Input
                    value={campus.name}
                    onChange={(e) => setCampus({ ...campus, name: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="c-code" label={t("tenancy.code")} hint={t("tenancy.codeHint")}>
                {(aria) => (
                  <Input
                    value={campus.code}
                    onChange={(e) => setCampus({ ...campus, code: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            </ActionDialog>
          ) : null}
        </div>
        <ul className="divide-y rounded-md border">
          {(campuses.data ?? []).map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <div>
                <p className="font-medium">
                  {localName(c, locale)}{" "}
                  {c.is_main ? (
                    <span className="bg-muted rounded px-2 py-0.5 text-xs">
                      {t("tenancy.campuses.main")}
                    </span>
                  ) : null}
                </p>
                <p className="text-muted-foreground text-xs">
                  {c.code}
                  {c.archived_at ? ` · ${t("tenancy.archived")}` : ""}
                </p>
              </div>
              {c.archived_at ? null : (
                <div className="flex gap-2">
                  {!c.is_main && canAnywhere(context, "tenancy.campus.update") ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void campusAction(c.id, "main")}
                    >
                      {t("tenancy.campuses.makeMain")}
                    </Button>
                  ) : null}
                  {canAnywhere(context, "tenancy.campus.archive") ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void campusAction(c.id, "archive")}
                    >
                      {t("tenancy.archive")}
                    </Button>
                  ) : null}
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
