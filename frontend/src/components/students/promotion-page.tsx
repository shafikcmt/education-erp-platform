"use client";

import type { Schemas } from "@erp/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { PageHeader } from "@/components/app/page-header";
import { SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

import { useEnrollmentChoices, useStudentsRefresh } from "./shared";

type Row = Schemas["PromotionRow"];
type Decision = "promote" | "repeat" | "complete";

/** Year-end promotion (Phase 7 M9): the server suggests (the published promotion rule, or
 * "complete" at the final level), staff decide each student, and applying runs in one
 * transaction after a fresh step-up. */
export function PromotionPage() {
  const t = useTranslations("students.promotion");
  const { institution, picker } = useInstitutionChoice();
  const { years, leafUnits } = useEnrollmentChoices(institution || undefined);
  const refresh = useStudentsRefresh();
  const { run, failure } = useAction();
  const [form, setForm] = useState({
    year_from: "",
    unit_from: "",
    year_to: "",
    unit_to: "",
    rule_key: "",
  });
  const [rows, setRows] = useState<Row[] | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [done, setDone] = useState<Record<Decision, number> | null>(null);
  const body = {
    year_from: form.year_from,
    unit_from: form.unit_from,
    year_to: form.year_to,
    unit_to: form.unit_to || null,
    rule_key: form.rule_key.trim(),
  };
  const choose = (
    key: "year_from" | "unit_from" | "year_to" | "unit_to",
    options: { id: string; name: string }[],
  ) => (
    <Field
      id={`promotion-${key}`}
      label={t(
        key === "year_from"
          ? "fromYear"
          : key === "year_to"
            ? "toYear"
            : key === "unit_from"
              ? "from"
              : "to",
      )}
    >
      {(aria) => (
        <select
          className={SELECT_CLASS}
          value={form[key]}
          onChange={(e) => {
            setForm({ ...form, [key]: e.target.value });
            setRows(null);
            setDone(null);
          }}
          {...aria}
        >
          <option value="">—</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
  const units = leafUnits.map((u) => ({ id: u.id, name: `${u.name} (${u.code})` }));
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 max-w-sm">{picker}</div>
      <Card>
        <CardContent className="grid gap-4 pt-6">
          {failure ? <Alert variant="destructive">{failure}</Alert> : null}
          {done ? <Alert variant="success">{t("done", done)}</Alert> : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {choose("year_from", years)}
            {choose("unit_from", units)}
            {choose("year_to", years)}
            {choose("unit_to", units)}
            <Field id="promotion-rule" label={t("rule")}>
              {(aria) => (
                <Input
                  value={form.rule_key}
                  onChange={(e) => setForm({ ...form, rule_key: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={!form.year_from || !form.unit_from || !form.year_to}
              onClick={() =>
                void run(async () => {
                  const preview = await unwrap(
                    api().POST("/api/v1/students/promotion/preview/", { body }),
                  );
                  setRows(preview);
                  setDecisions(
                    Object.fromEntries(preview.map((r) => [r.student, r.suggestion as Decision])),
                  );
                  setDone(null);
                })
              }
            >
              {t("preview")}
            </Button>
            {rows?.length ? (
              <Button
                onClick={() =>
                  void run(async () => {
                    const counts = await unwrap(
                      api().POST("/api/v1/students/promotion/apply/", {
                        body: { ...body, decisions },
                      }),
                    );
                    setDone(counts);
                    setRows(null);
                    await refresh();
                  })
                }
              >
                {t("apply")}
              </Button>
            ) : null}
          </div>
          {rows ? (
            <ul className="divide-y text-sm" data-testid="promotion-rows">
              {rows.map((r) => (
                <li
                  key={r.student}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <span>
                    {r.name} <span className="text-muted-foreground text-xs">{r.number}</span>
                    {r.note ? (
                      <span className="text-destructive block text-xs">{r.note}</span>
                    ) : null}
                  </span>
                  <select
                    className={SELECT_CLASS}
                    aria-label={`${t("decision")}: ${r.name}`}
                    value={decisions[r.student] ?? r.suggestion}
                    onChange={(e) =>
                      setDecisions({ ...decisions, [r.student]: e.target.value as Decision })
                    }
                  >
                    {(form.unit_to
                      ? (["promote", "repeat", "complete"] as const)
                      : (["repeat", "complete"] as const)
                    ).map((d) => (
                      <option key={d} value={d}>
                        {t(`decisions.${d}`)}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
    </>
  );
}
