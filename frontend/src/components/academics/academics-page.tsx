"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, localName, useTenantContext } from "@/lib/tenancy/context";

import { useInstitutionChoice } from "./institution-picker";

const KEY = ["academics"] as const;
const CODE = /^[A-Za-z0-9_.-]{1,32}$/;

function useRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

/** Academic structure of an institution (Phase 6 M7): years, units by the preset's levels,
 * subjects. The levels come from the server (preset and capability flags), never from code. */
export function AcademicsPage() {
  const t = useTranslations("academics");
  const { data: context } = useTenantContext();
  const { institution, picker } = useInstitutionChoice();
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 max-w-sm">{picker}</div>
      {institution ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <YearsCard
            institution={institution}
            manage={canAnywhere(context, "academics.year.manage")}
          />
          <SubjectsCard
            institution={institution}
            manage={canAnywhere(context, "academics.subject.manage")}
          />
          <div className="lg:col-span-2">
            <UnitsCard
              institution={institution}
              manage={canAnywhere(context, "academics.structure.manage")}
            />
          </div>
        </div>
      ) : null}
    </>
  );
}

function YearsCard({ institution, manage }: { institution: string; manage: boolean }) {
  const t = useTranslations("academics");
  const refresh = useRefresh();
  const { run, failure } = useAction();
  const years = useQuery({
    queryKey: [...KEY, "years", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/years/", { params: { query: { institution } } })),
  });
  const empty = { code: "", name: "", start_date: "", end_date: "" };
  const [form, setForm] = useState(empty);
  const valid =
    CODE.test(form.code) && form.name.trim() && form.start_date && form.end_date >= form.start_date;
  const setStatus = (id: string, status: "active" | "closed") =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/academics/years/{year_id}/status/", {
          params: { path: { year_id: id } },
          body: { status },
        }),
      );
      await refresh();
    });
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("years.title")}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t("years.add")}</Button>}
            title={t("years.add")}
            submit={t("save")}
            disabled={!valid}
            onSubmit={async () => {
              await unwrap(
                api().POST("/api/v1/academics/years/", {
                  body: { institution, ...form, name: form.name.trim() },
                }),
              );
              setForm(empty);
              await refresh();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field id="year-code" label={t("code")}>
                {(aria) => (
                  <Input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value.trim() })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="year-name" label={t("name")}>
                {(aria) => (
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="year-start" label={t("years.start")}>
                {(aria) => (
                  <Input
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="year-end" label={t("years.end")}>
                {(aria) => (
                  <Input
                    type="date"
                    value={form.end_date}
                    onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            </div>
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-2">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {years.data?.length ? (
          <ul className="grid gap-2 text-sm" data-testid="years">
            {years.data.map((y) => (
              <li key={y.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {y.name}{" "}
                  <span className="text-muted-foreground text-xs">
                    {y.start_date} – {y.end_date} · {t(`years.statuses.${y.status}`)}
                  </span>
                </span>
                {manage && y.status === "planned" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void setStatus(y.id, "active")}
                  >
                    {t("years.activate")}
                  </Button>
                ) : null}
                {manage && y.status === "active" ? (
                  <Button size="sm" variant="ghost" onClick={() => void setStatus(y.id, "closed")}>
                    {t("years.close")}
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

function SubjectsCard({ institution, manage }: { institution: string; manage: boolean }) {
  const t = useTranslations("academics");
  const refresh = useRefresh();
  const subjects = useQuery({
    queryKey: [...KEY, "subjects", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/subjects/", { params: { query: { institution } } })),
  });
  const empty = { code: "", name: "", subject_type: "core", credits: "" };
  const [form, setForm] = useState(empty);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("subjects.title")}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t("subjects.add")}</Button>}
            title={t("subjects.add")}
            description={t("subjects.creditsHint")}
            submit={t("save")}
            disabled={!CODE.test(form.code) || !form.name.trim()}
            onSubmit={async () => {
              await unwrap(
                api().POST("/api/v1/academics/subjects/", {
                  body: {
                    institution,
                    code: form.code,
                    name: form.name.trim(),
                    subject_type: form.subject_type,
                    credits: form.credits || null,
                  },
                }),
              );
              setForm(empty);
              await refresh();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field id="subject-code" label={t("code")}>
                {(aria) => (
                  <Input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value.trim() })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="subject-name" label={t("name")}>
                {(aria) => (
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="subject-type" label={t("subjects.type")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={form.subject_type}
                    onChange={(e) => setForm({ ...form, subject_type: e.target.value })}
                    {...aria}
                  >
                    {(["core", "elective", "optional", "practical"] as const).map((k) => (
                      <option key={k} value={k}>
                        {t(`subjects.types.${k}`)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Field id="subject-credits" label={t("subjects.credits")}>
                {(aria) => (
                  <Input
                    inputMode="decimal"
                    value={form.credits}
                    onChange={(e) => setForm({ ...form, credits: e.target.value.trim() })}
                    {...aria}
                  />
                )}
              </Field>
            </div>
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent>
        {subjects.data?.length ? (
          <ul className="grid gap-1 text-sm" data-testid="subjects">
            {subjects.data.map((s) => (
              <li key={s.id}>
                {s.name}{" "}
                <span className="text-muted-foreground text-xs">
                  {s.code}
                  {s.credits ? ` · ${t("subjects.creditCount", { credits: s.credits })}` : ""}
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

function UnitsCard({ institution, manage }: { institution: string; manage: boolean }) {
  const t = useTranslations("academics");
  const locale = useLocale();
  const refresh = useRefresh();
  const setup = useQuery({
    queryKey: [...KEY, "setup", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/setup/", { params: { query: { institution } } })),
  });
  const units = useQuery({
    queryKey: [...KEY, "units", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/units/", { params: { query: { institution } } })),
  });
  const levels = setup.data?.levels ?? [];
  const empty = { level_key: "", code: "", name: "", parent: "", capacity: "" };
  const [form, setForm] = useState(empty);
  const level = form.level_key || levels[0] || "";
  // The organisation's own words for its levels (terminology resolved by the server).
  const levelName = (key: string) => setup.data?.level_labels[key] ?? key;
  const rows = units.data ?? [];
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("units.title")}</CardTitle>
        {manage && levels.length ? (
          <ActionDialog
            trigger={<Button size="sm">{t("units.add")}</Button>}
            title={t("units.add")}
            description={t("units.levelsHint")}
            submit={t("save")}
            disabled={!CODE.test(form.code) || !form.name.trim()}
            onSubmit={async () => {
              await unwrap(
                api().POST("/api/v1/academics/units/", {
                  body: {
                    institution,
                    level_key: level,
                    code: form.code,
                    name: form.name.trim(),
                    parent: form.parent || null,
                    capacity: form.capacity ? Number(form.capacity) : null,
                    order: 0,
                  },
                }),
              );
              setForm(empty);
              await refresh();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field id="unit-level" label={t("units.level")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={level}
                    onChange={(e) => setForm({ ...form, level_key: e.target.value })}
                    {...aria}
                  >
                    {levels.map((l) => (
                      <option key={l} value={l}>
                        {levelName(l)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Field id="unit-parent" label={t("units.parent")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={form.parent}
                    onChange={(e) => setForm({ ...form, parent: e.target.value })}
                    {...aria}
                  >
                    <option value="">{t("units.noParent")}</option>
                    {rows.map((u) => (
                      <option key={u.id} value={u.id}>
                        {levelName(u.level_key)} · {localName(u, locale)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Field id="unit-code" label={t("code")}>
                {(aria) => (
                  <Input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value.trim() })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="unit-name" label={t("name")}>
                {(aria) => (
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="unit-capacity" label={t("units.capacity")}>
                {(aria) => (
                  <Input
                    type="number"
                    min={1}
                    value={form.capacity}
                    onChange={(e) => setForm({ ...form, capacity: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            </div>
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent>
        {setup.isSuccess && !levels.length ? <Alert>{t("units.noPreset")}</Alert> : null}
        {rows.length ? (
          <UnitTree rows={rows} parent={null} levelName={levelName} locale={locale} />
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}

type UnitRow = {
  id: string;
  parent: string | null;
  level_key: string;
  code: string;
  name: string;
  name_i18n: unknown;
  capacity: number | null;
};

function UnitTree({
  rows,
  parent,
  levelName,
  locale,
}: {
  rows: UnitRow[];
  parent: string | null;
  levelName: (key: string) => string;
  locale: string;
}) {
  const children = rows.filter((u) => u.parent === parent);
  if (!children.length) return null;
  return (
    <ul
      className={parent ? "mt-1 grid gap-1 border-l ps-4" : "grid gap-1 text-sm"}
      data-testid={parent ? undefined : "units"}
    >
      {children.map((u) => (
        <li key={u.id}>
          <span className="text-muted-foreground text-xs">{levelName(u.level_key)}</span>{" "}
          {localName(u, locale)} <span className="text-muted-foreground text-xs">{u.code}</span>
          <UnitTree rows={rows} parent={u.id} levelName={levelName} locale={locale} />
        </li>
      ))}
    </ul>
  );
}
