"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

import { STUDIO_KEY, useCatalog, useStudioRefresh } from "./shared";

const TYPES = [
  "text",
  "long_text",
  "number",
  "decimal",
  "date",
  "boolean",
  "single_select",
  "multi_select",
  "email",
  "phone",
] as const;

/** "value = label" lines → options of a choice field. */
function parseOptions(text: string, locale: string) {
  return text
    .split("\n")
    .map((line) => line.split("="))
    .filter(([value, label]) => value?.trim() && label?.trim())
    .map(([value, label]) => ({ value: value!.trim(), labels: { [locale]: label!.trim() } }));
}

export function FieldsSection() {
  const t = useTranslations("studio");
  const locale = useLocale();
  const refresh = useStudioRefresh();
  const catalog = useCatalog();
  const { run, failure } = useAction();
  const entities = Object.keys((catalog.data?.entities as Record<string, string>) ?? {});
  const [entity, setEntity] = useState("tenancy.institution");
  const query = useQuery({
    queryKey: [...STUDIO_KEY, "fields", entity],
    queryFn: () =>
      unwrap(api().GET("/api/v1/customization/fields/", { params: { query: { entity } } })),
  });
  const empty = { key: "", type: "text", en: "", bn: "", required: false, options: "" };
  const [form, setForm] = useState(empty);
  const choice = form.type === "single_select" || form.type === "multi_select";
  const deprecate = (id: string) =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/customization/fields/{field_id}/deprecate/", {
          params: { path: { field_id: id } },
        }),
      );
      await refresh();
    });
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("sections.fields")}</CardTitle>
        <ActionDialog
          trigger={<Button size="sm">{t("fields.add")}</Button>}
          title={t("fields.add")}
          description={t("fields.addHint")}
          submit={t("fields.add")}
          disabled={!/^[a-z][a-z0-9_]{1,63}$/.test(form.key) || !form.en.trim()}
          onSubmit={async () => {
            const labels: Record<string, string> = { en: form.en.trim() };
            if (form.bn.trim()) labels.bn = form.bn.trim();
            await unwrap(
              api().POST("/api/v1/customization/fields/", {
                body: {
                  entity,
                  key: form.key,
                  field_type: form.type,
                  labels,
                  required: form.required,
                  ...(choice ? { options: parseOptions(form.options, "en") } : {}),
                },
              }),
            );
            setForm(empty);
            await refresh();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="field-key" label={t("key")} hint={t("keyHint")}>
              {(aria) => (
                <Input
                  value={form.key}
                  onChange={(e) => setForm({ ...form, key: e.target.value.trim() })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="field-type" label={t("fields.type")}>
              {(aria) => (
                <select
                  className={SELECT_CLASS}
                  value={form.type}
                  onChange={(e) => setForm({ ...form, type: e.target.value })}
                  {...aria}
                >
                  {TYPES.map((type) => (
                    <option key={type} value={type}>
                      {t(`fieldTypes.${type}`)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field id="field-en" label={t("fields.labelEn")}>
              {(aria) => (
                <Input
                  value={form.en}
                  onChange={(e) => setForm({ ...form, en: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="field-bn" label={t("fields.labelBn")}>
              {(aria) => (
                <Input
                  value={form.bn}
                  onChange={(e) => setForm({ ...form, bn: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
          </div>
          {choice ? (
            <Field id="field-options" label={t("fields.options")} hint={t("fields.optionsHint")}>
              {(aria) => (
                <textarea
                  className="bg-background w-full rounded-md border p-2 text-sm"
                  rows={4}
                  value={form.options}
                  onChange={(e) => setForm({ ...form, options: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
          ) : null}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.required}
              onChange={(e) => setForm({ ...form, required: e.target.checked })}
            />
            {t("fields.required")}
          </label>
        </ActionDialog>
      </CardHeader>
      <CardContent className="grid gap-3">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        <Field id="field-entity" label={t("fields.entity")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={entity}
              onChange={(e) => setEntity(e.target.value)}
              {...aria}
            >
              {entities.map((code) => (
                <option key={code} value={code}>
                  {t(`entities.${code.replace(".", "_")}` as "entities.tenancy_institution")}
                </option>
              ))}
            </select>
          )}
        </Field>
        {query.data?.length ? (
          <ul className="divide-y text-sm" data-testid="fields-list">
            {query.data.map((field) => {
              const labels = field.labels as Record<string, string>;
              return (
                <li
                  key={field.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <span>
                    {labels[locale] ?? labels.en}{" "}
                    <code className="text-muted-foreground text-xs">{field.key}</code>
                    <span className="text-muted-foreground block text-xs">
                      {t(`fieldTypes.${field.field_type}` as "fieldTypes.text")}
                      {field.required ? ` · ${t("fields.required")}` : ""}
                      {field.deprecated_at ? ` · ${t("fields.deprecated")}` : ""}
                    </span>
                  </span>
                  {field.deprecated_at ? null : (
                    <Button size="sm" variant="ghost" onClick={() => void deprecate(field.id)}>
                      {t("fields.deprecate")}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
