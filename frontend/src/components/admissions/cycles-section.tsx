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
import { canAnywhere, localName, useTenantContext } from "@/lib/tenancy/context";

import { CyclePanel } from "./cycle-panel";
import { ADMISSIONS_KEY, useAdmissionsRefresh } from "./shared";

const NEXT: Record<string, ("open" | "closed" | "archived")[]> = {
  draft: ["open"],
  open: ["closed"],
  closed: ["open", "archived"],
};

/** Admission cycles of an institution; choosing one opens its applications, tests and merit. */
export function CyclesSection({ institution }: { institution: string }) {
  const t = useTranslations("admissions");
  const locale = useLocale();
  const { data: context } = useTenantContext();
  const manage = canAnywhere(context, "admissions.cycle.manage");
  const refresh = useAdmissionsRefresh();
  const { run, failure } = useAction();
  const cycles = useQuery({
    queryKey: [...ADMISSIONS_KEY, "cycles", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/admissions/cycles/", { params: { query: { institution } } })),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const setStatus = (id: string, status: "open" | "closed" | "archived") =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/admissions/cycles/{cycle_id}/status/", {
          params: { path: { cycle_id: id } },
          body: { status },
        }),
      );
      await refresh();
    });
  if (cycles.isError) return <Alert variant="destructive">{t("noAccess")}</Alert>;
  const current = cycles.data?.find((c) => c.id === selected);
  return (
    <div className="grid gap-4">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("cycles.title")}</CardTitle>
          {manage ? <CreateCycle institution={institution} /> : null}
        </CardHeader>
        <CardContent>
          {cycles.data?.length ? (
            <ul className="grid gap-3 text-sm" data-testid="cycles">
              {cycles.data.map((c) => (
                <li key={c.id} className="grid gap-1 rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">
                      {localName(c, locale)}{" "}
                      <span className="text-muted-foreground text-xs">
                        {c.opens_on} – {c.closes_on} · {t(`cycles.statuses.${c.status}`)}
                      </span>
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {manage && c.status !== "archived" ? (
                        <AddTarget institution={institution} cycle={c.id} />
                      ) : null}
                      {manage
                        ? (NEXT[c.status] ?? []).map((next) => (
                            <Button
                              key={next}
                              size="sm"
                              variant="outline"
                              onClick={() => void setStatus(c.id, next)}
                            >
                              {t(`cycles.to.${next}`)}
                            </Button>
                          ))
                        : null}
                      <Button
                        size="sm"
                        variant={selected === c.id ? "default" : "ghost"}
                        aria-expanded={selected === c.id}
                        onClick={() => setSelected(selected === c.id ? null : c.id)}
                      >
                        {t("cycles.manage")}
                      </Button>
                    </div>
                  </div>
                  <p className="text-muted-foreground text-xs">
                    {c.targets.length
                      ? c.targets
                          .map((g) => t("cycles.target", { unit: g.unit_name, seats: g.capacity }))
                          .join(" · ")
                      : t("cycles.noTargets")}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("cycles.none")}</p>
          )}
        </CardContent>
      </Card>
      {current ? <CyclePanel key={current.id} cycle={current} /> : null}
    </div>
  );
}

function CreateCycle({ institution }: { institution: string }) {
  const t = useTranslations("admissions");
  const refresh = useAdmissionsRefresh();
  const years = useQuery({
    queryKey: [...ADMISSIONS_KEY, "years", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/years/", { params: { query: { institution } } })),
  });
  const empty = {
    year: "",
    code: "",
    name: "",
    opens_on: "",
    closes_on: "",
    form_key: "",
    workflow_key: "",
    merit_rule_key: "",
    numbering_key: "",
  };
  const [form, setForm] = useState(empty);
  const year = form.year || years.data?.find((y) => y.status !== "closed")?.id || "";
  const valid =
    year &&
    /^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$/.test(form.code) &&
    form.name.trim() &&
    form.opens_on &&
    form.closes_on >= form.opens_on &&
    form.form_key;
  const text = (key: keyof typeof empty, type = "text", hint?: string) => (
    <Field id={`cycle-${key}`} label={t(`cycles.fields.${key}`)} hint={hint}>
      {(aria) => (
        <Input
          type={type}
          value={form[key]}
          onChange={(e) => setForm({ ...form, [key]: e.target.value.trim() })}
          {...aria}
        />
      )}
    </Field>
  );
  return (
    <ActionDialog
      trigger={<Button size="sm">{t("cycles.add")}</Button>}
      title={t("cycles.add")}
      description={t("cycles.bindingsHint")}
      submit={t("save")}
      disabled={!valid}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/admissions/cycles/", {
            body: { institution, ...form, year, name: form.name.trim() },
          }),
        );
        setForm(empty);
        await refresh();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="cycle-year" label={t("cycles.fields.year")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={year}
              onChange={(e) => setForm({ ...form, year: e.target.value })}
              {...aria}
            >
              {(years.data ?? [])
                .filter((y) => y.status !== "closed")
                .map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.name}
                  </option>
                ))}
            </select>
          )}
        </Field>
        {text("code")}
        <Field id="cycle-name" label={t("cycles.fields.name")}>
          {(aria) => (
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              {...aria}
            />
          )}
        </Field>
        {text("opens_on", "date")}
        {text("closes_on", "date")}
        {text("form_key")}
        {text("workflow_key")}
        {text("merit_rule_key")}
        {text("numbering_key")}
      </div>
    </ActionDialog>
  );
}

function AddTarget({ institution, cycle }: { institution: string; cycle: string }) {
  const t = useTranslations("admissions");
  const locale = useLocale();
  const refresh = useAdmissionsRefresh();
  const units = useQuery({
    queryKey: [...ADMISSIONS_KEY, "units", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/units/", { params: { query: { institution } } })),
  });
  const [unit, setUnit] = useState("");
  const [capacity, setCapacity] = useState("");
  return (
    <ActionDialog
      trigger={
        <Button size="sm" variant="outline">
          {t("cycles.addTarget")}
        </Button>
      }
      title={t("cycles.addTarget")}
      submit={t("save")}
      disabled={!unit || !(Number(capacity) >= 1)}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/admissions/cycles/{cycle_id}/targets/", {
            params: { path: { cycle_id: cycle } },
            body: { unit, capacity: Number(capacity) },
          }),
        );
        setUnit("");
        setCapacity("");
        await refresh();
      }}
    >
      <Field id="target-unit" label={t("cycles.unit")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            {...aria}
          >
            <option value="" />
            {(units.data ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {localName(u, locale)} ({u.code})
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field id="target-capacity" label={t("cycles.capacity")}>
        {(aria) => (
          <Input
            type="number"
            min={1}
            value={capacity}
            onChange={(e) => setCapacity(e.target.value)}
            {...aria}
          />
        )}
      </Field>
    </ActionDialog>
  );
}
