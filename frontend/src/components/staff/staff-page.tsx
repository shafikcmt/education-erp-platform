"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { PageHeader } from "@/components/app/page-header";
import { useEnrollmentChoices } from "@/components/students/shared";
import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

const KEY = ["staff"] as const;
const CODE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/;
const EMPLOYMENT = ["permanent", "contract", "part_time", "visiting", "volunteer"] as const;

function useRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

/** Staff of an institution (Phase 7 M9): the directory, departments and designations, and the
 * class teachers (advisors) of units. A profile may have no login (support staff). */
export function StaffPage() {
  const t = useTranslations("staff");
  const { data: context } = useTenantContext();
  const can = (code: string) => canAnywhere(context, code);
  const { institution, picker } = useInstitutionChoice();
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 max-w-sm">{picker}</div>
      {institution ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="lg:col-span-2">
            <Directory institution={institution} manage={can("staff.profile.manage")} />
          </div>
          <Structure
            institution={institution}
            kind="departments"
            manage={can("staff.structure.manage")}
          />
          <Structure
            institution={institution}
            kind="designations"
            manage={can("staff.structure.manage")}
          />
          {can("academics.offering.view") ? (
            <div className="lg:col-span-2">
              <Advisors institution={institution} manage={can("academics.offering.manage")} />
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function useStructure(institution: string, kind: "departments" | "designations") {
  return useQuery({
    queryKey: [...KEY, kind, institution],
    queryFn: () =>
      kind === "departments"
        ? unwrap(api().GET("/api/v1/staff/departments/", { params: { query: { institution } } }))
        : unwrap(api().GET("/api/v1/staff/designations/", { params: { query: { institution } } })),
  });
}

function Directory({ institution, manage }: { institution: string; manage: boolean }) {
  const t = useTranslations("staff");
  const refresh = useRefresh();
  const departments = useStructure(institution, "departments");
  const designations = useStructure(institution, "designations");
  const empty = {
    name: "",
    number: "",
    phone: "",
    email: "",
    joining_date: "",
    department: "",
    designation: "",
    employment_type: "permanent",
  };
  const [form, setForm] = useState(empty);
  const list = useQuery({
    queryKey: [...KEY, "profiles", institution],
    queryFn: () => unwrap(api().GET("/api/v1/staff/", { params: { query: { institution } } })),
  });
  const select = (
    key: "department" | "designation",
    rows: { id: string; name: string; archived: boolean }[] | undefined,
  ) => (
    <Field id={`staff-${key}`} label={t(`fields.${key}`)}>
      {(aria) => (
        <select
          className={SELECT_CLASS}
          value={form[key]}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          {...aria}
        >
          <option value="">—</option>
          {(rows ?? [])
            .filter((r) => !r.archived)
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
        </select>
      )}
    </Field>
  );
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("directory")}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t("add")}</Button>}
            title={t("add")}
            description={t("numberHint")}
            submit={t("save")}
            disabled={!form.name.trim()}
            onSubmit={async () => {
              const values = Object.fromEntries(
                (["name", "phone", "email", "joining_date"] as const)
                  .filter((k) => form[k].trim())
                  .map((k) => [k, form[k].trim()]),
              );
              await unwrap(
                api().POST("/api/v1/staff/", {
                  body: {
                    institution,
                    values,
                    number: form.number.trim(),
                    links: {
                      department: form.department || null,
                      designation: form.designation || null,
                      employment_type: form.employment_type as (typeof EMPLOYMENT)[number],
                    },
                  },
                }),
              );
              setForm(empty);
              await refresh();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {(["name", "number", "phone", "email", "joining_date"] as const).map((key) => (
                <Field key={key} id={`staff-${key}`} label={t(`fields.${key}`)}>
                  {(aria) => (
                    <Input
                      type={key === "joining_date" ? "date" : key === "email" ? "email" : "text"}
                      value={form[key]}
                      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                      {...aria}
                    />
                  )}
                </Field>
              ))}
              {select("department", departments.data)}
              {select("designation", designations.data)}
              <Field id="staff-employment" label={t("fields.employment_type")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={form.employment_type}
                    onChange={(e) => setForm({ ...form, employment_type: e.target.value })}
                    {...aria}
                  >
                    {EMPLOYMENT.map((k) => (
                      <option key={k} value={k}>
                        {t(`employment.${k}`)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </div>
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent>
        {list.data?.length ? (
          <ul className="divide-y text-sm" data-testid="staff">
            {list.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="font-medium">{row.name}</span>
                <span className="text-muted-foreground text-xs">
                  {[row.number, row.designation_name, row.department_name]
                    .filter(Boolean)
                    .join(" · ")}
                  {row.has_login ? "" : ` · ${t("noLogin")}`}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}

function Structure({
  institution,
  kind,
  manage,
}: {
  institution: string;
  kind: "departments" | "designations";
  manage: boolean;
}) {
  const t = useTranslations("staff");
  const refresh = useRefresh();
  const rows = useStructure(institution, kind);
  const [form, setForm] = useState({ code: "", name: "" });
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t(`${kind}.title`)}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t(`${kind}.add`)}</Button>}
            title={t(`${kind}.add`)}
            submit={t("save")}
            disabled={!CODE.test(form.code) || !form.name.trim()}
            onSubmit={async () => {
              const body = { institution, code: form.code, name: form.name.trim() };
              if (kind === "departments") {
                await unwrap(
                  api().POST("/api/v1/staff/departments/", {
                    body: { ...body, kind: "academic" },
                  }),
                );
              } else {
                await unwrap(api().POST("/api/v1/staff/designations/", { body }));
              }
              setForm({ code: "", name: "" });
              await refresh();
            }}
          >
            {(["code", "name"] as const).map((key) => (
              <Field key={key} id={`${kind}-${key}`} label={t(`fields.${key}`)}>
                {(aria) => (
                  <Input
                    value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            ))}
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent>
        {rows.data?.length ? (
          <ul className="grid gap-1 text-sm">
            {rows.data.map((row) => (
              <li key={row.id}>
                {row.name} <span className="text-muted-foreground text-xs">{row.code}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}

function Advisors({ institution, manage }: { institution: string; manage: boolean }) {
  const t = useTranslations("staff");
  const refresh = useRefresh();
  const { run, failure } = useAction();
  const { years } = useEnrollmentChoices(institution);
  const units = useQuery({
    queryKey: ["academics", "units", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/units/", { params: { query: { institution } } })),
  });
  const profiles = useQuery({
    queryKey: [...KEY, "profiles", institution],
    enabled: manage,
    queryFn: () => unwrap(api().GET("/api/v1/staff/", { params: { query: { institution } } })),
  });
  const advisors = useQuery({
    queryKey: [...KEY, "advisors", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/staff/advisors/", { params: { query: { institution } } })),
  });
  const [form, setForm] = useState({ year: "", unit: "", staff: "" });
  const choose = (key: keyof typeof form, options: { id: string; label: string }[]) => (
    <Field id={`advisor-${key}`} label={t(`advisors.${key}`)}>
      {(aria) => (
        <select
          className={SELECT_CLASS}
          value={form[key]}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          {...aria}
        >
          <option value="">—</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("advisors.title")}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t("advisors.add")}</Button>}
            title={t("advisors.add")}
            description={t("advisors.hint")}
            submit={t("save")}
            disabled={!form.year || !form.unit || !form.staff}
            onSubmit={async () => {
              await unwrap(
                api().POST("/api/v1/staff/advisors/", { body: { ...form, is_primary: true } }),
              );
              setForm({ year: "", unit: "", staff: "" });
              await refresh();
            }}
          >
            {choose(
              "year",
              years.map((y) => ({ id: y.id, label: y.name })),
            )}
            {choose(
              "unit",
              (units.data ?? []).map((u) => ({ id: u.id, label: `${u.name} (${u.code})` })),
            )}
            {choose(
              "staff",
              (profiles.data ?? [])
                .filter((p) => p.has_login && p.status === "active")
                .map((p) => ({ id: p.id, label: p.name })),
            )}
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-2">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {advisors.data?.length ? (
          <ul className="grid gap-1 text-sm" data-testid="advisors">
            {advisors.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {row.unit_name} · {row.year_name} · {row.staff_name}
                  {row.is_primary ? "" : ` (${t("advisors.assistant")})`}
                </span>
                {manage ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      void run(async () => {
                        await unwrap(
                          api().DELETE("/api/v1/staff/advisors/{advisor_id}/", {
                            params: { path: { advisor_id: row.id } },
                          }),
                        );
                        await refresh();
                      })
                    }
                  >
                    {t("advisors.remove")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
