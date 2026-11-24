"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { api } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";

type Option = { value: string; labels: Record<string, string> };
export type RenderedField = {
  source: "core" | "custom";
  name: string;
  type?: string;
  labels?: Record<string, string>;
  options?: Option[];
  required: boolean;
};
export type RenderedSection = {
  key: string;
  labels: Record<string, string>;
  fields: RenderedField[];
  conditional: boolean;
};
export type Values = Record<string, unknown>;

/** A localised label with the English fallback, then the key. */
export function label(labels: Record<string, string> | undefined, locale: string, key: string) {
  return labels?.[locale] || labels?.en || key;
}

/** The value an input holds, converted to what the server validates. */
export function coerce(type: string | undefined, raw: string | boolean | string[]): unknown {
  if (type === "boolean") return Boolean(raw);
  if (type === "multi_select") return raw;
  if (raw === "") return null;
  if (type === "number") return Number(raw);
  return raw; // decimals stay strings so no precision is lost
}

const INPUT_TYPES: Record<string, string> = {
  number: "number",
  decimal: "text",
  date: "date",
  email: "email",
  phone: "tel",
};

/** Where a form comes from and where it goes: the Studio preview validates; the public
 * admission form submits an application (Phase 6 M7). */
export type FormSource = {
  cacheKey: unknown[];
  render: () => Promise<{ sections: RenderedSection[] }>;
  visibility: (values: Values) => Promise<string[]>;
  submit: (values: Values) => Promise<unknown>;
  submitLabel?: string;
  /** Shown inside the form above the button (for example a hidden honeypot field). */
  extra?: ReactNode;
};

function studioSource(formKey: string): FormSource {
  return {
    cacheKey: ["studio", "form-render", formKey],
    render: () =>
      unwrap(
        api().GET("/api/v1/customization/forms/{key}/render/", {
          params: { path: { key: formKey } },
        }),
      ) as Promise<{ sections: RenderedSection[] }>,
    visibility: async (values) =>
      (
        await unwrap(
          api().POST("/api/v1/customization/forms/{key}/visibility/", {
            params: { path: { key: formKey } },
            body: { values },
          }),
        )
      ).sections,
    submit: (values) =>
      unwrap(
        api().POST("/api/v1/customization/forms/{key}/validate/", {
          params: { path: { key: formKey } },
          body: { values },
        }),
      ),
  };
}

/**
 * Renders a published form. Section visibility is decided by the server (the rules sandbox) on
 * every change; the submission is validated by the server too, and its field errors are shown
 * inline. The browser never evaluates rules itself.
 */
export function DynamicForm({
  formKey,
  source: given,
  onValid,
}: {
  formKey: string;
  source?: FormSource;
  onValid?: (result: unknown) => void;
}) {
  const t = useTranslations("studio.form");
  const locale = useLocale();
  const [fallback] = useState(() => studioSource(formKey));
  const source = given ?? fallback;
  const form = useQuery({ queryKey: source.cacheKey, queryFn: source.render });
  const [values, setValues] = useState<Values>({});
  const [shown, setShown] = useState<string[] | null>(null);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!form.data) return;
    let stale = false;
    const handle = setTimeout(() => {
      void source.visibility(values).then(
        (sections) => !stale && setShown(sections),
        () => !stale && setShown([]), // fail closed: hide conditional sections
      );
    }, 250);
    return () => {
      stale = true;
      clearTimeout(handle);
    };
  }, [form.data, source, values]);

  if (form.isError) return <Alert variant="destructive">{t("unavailable")}</Alert>;
  if (!form.data) return <p className="text-muted-foreground text-sm">{t("loading")}</p>;
  const visible = form.data.sections.filter((s) => !s.conditional || shown?.includes(s.key));
  const set = (name: string, value: unknown) => {
    setDone(false);
    setValues((current) => ({ ...current, [name]: value }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    setFailure(null);
    // Only fields of visible sections are sent (hidden sections must stay empty).
    const names = new Set(visible.flatMap((s) => s.fields.map((f) => f.name)));
    const payload = Object.fromEntries(
      Object.entries(values).filter(([n, v]) => names.has(n) && v !== null && v !== ""),
    );
    try {
      const result = await source.submit(payload);
      setDone(!given); // the caller shows its own outcome
      onValid?.(result);
    } catch (error) {
      if (isApiError(error) && Object.keys(error.fieldErrors).length) setErrors(error.fieldErrors);
      else setFailure(t("failed"));
    }
  };

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => void submit(e)}
      noValidate
      data-testid="dynamic-form"
    >
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      {done ? <Alert>{t("valid")}</Alert> : null}
      {visible.map((section) => (
        <fieldset key={section.key} className="grid gap-3 rounded-md border p-3">
          <legend className="px-1 text-sm font-medium">
            {label(section.labels, locale, section.key)}
          </legend>
          {section.fields.map((field) => (
            <FieldInput
              key={field.name}
              field={field}
              locale={locale}
              value={values[field.name]}
              error={errors[field.name]?.[0]}
              onChange={(v) => set(field.name, v)}
            />
          ))}
        </fieldset>
      ))}
      {source.extra}
      <div>
        <Button type="submit">{source.submitLabel ?? t("check")}</Button>
      </div>
    </form>
  );
}

function FieldInput({
  field,
  locale,
  value,
  error,
  onChange,
}: {
  field: RenderedField;
  locale: string;
  value: unknown;
  error?: string;
  onChange: (value: unknown) => void;
}) {
  const id = `df-${field.name}`;
  const text = label(field.labels, locale, field.name) + (field.required ? " *" : "");
  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(coerce("boolean", e.target.checked))}
        />
        {text}
        {error ? <span className="text-destructive text-xs">{error}</span> : null}
      </label>
    );
  }
  return (
    <Field id={id} label={text} error={error}>
      {(aria) =>
        field.type === "single_select" || field.type === "multi_select" ? (
          <select
            className={SELECT_CLASS}
            multiple={field.type === "multi_select"}
            value={
              (value as string | string[] | undefined) ?? (field.type === "multi_select" ? [] : "")
            }
            onChange={(e) =>
              onChange(
                field.type === "multi_select"
                  ? coerce(
                      "multi_select",
                      [...e.target.selectedOptions].map((o) => o.value),
                    )
                  : coerce(field.type, e.target.value),
              )
            }
            {...aria}
          >
            {field.type === "single_select" ? <option value="" /> : null}
            {(field.options ?? []).map((o) => (
              <option key={o.value} value={o.value}>
                {label(o.labels, locale, o.value)}
              </option>
            ))}
          </select>
        ) : field.type === "long_text" ? (
          <textarea
            className="bg-background w-full rounded-md border p-2 text-sm"
            rows={3}
            value={(value as string | undefined) ?? ""}
            onChange={(e) => onChange(coerce(field.type, e.target.value))}
            {...aria}
          />
        ) : (
          <Input
            type={INPUT_TYPES[field.type ?? ""] ?? "text"}
            value={value === null || value === undefined ? "" : String(value)}
            onChange={(e) => onChange(coerce(field.type, e.target.value))}
            {...aria}
          />
        )
      }
    </Field>
  );
}
