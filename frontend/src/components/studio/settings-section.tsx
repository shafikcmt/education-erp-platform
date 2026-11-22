"use client";

import { useQuery } from "@tanstack/react-query";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { localName } from "@/lib/tenancy/context";

import { STUDIO_KEY, useStudioRefresh } from "./shared";

type Terms = Record<string, Record<string, string>>;
type Row = { locale: string; key: string; label: string };

function toRows(terms: Terms): Row[] {
  return Object.entries(terms).flatMap(([locale, map]) =>
    Object.entries(map).map(([key, label]) => ({ locale, key, label })),
  );
}

function toTerms(rows: Row[]): Terms {
  const out: Terms = {};
  for (const row of rows) {
    if (!row.locale || !row.key || !row.label) continue;
    (out[row.locale] ??= {})[row.key] = row.label;
  }
  return out;
}

/** The draft document: the current one with the edited keys replaced (empty = inherit). */
export function buildDocument(
  base: Record<string, unknown>,
  edits: { week: string; month: string; rows: Row[] },
): Record<string, unknown> {
  const data: Record<string, unknown> = { ...base };
  const put = (key: string, value: unknown, keep: boolean) => {
    if (keep) data[key] = value;
    else delete data[key];
  };
  put("tenancy.week_start", Number(edits.week), Boolean(edits.week));
  put("tenancy.academic_year_start_month", Number(edits.month), Boolean(edits.month));
  const terms = toTerms(edits.rows);
  put("customization.terminology", terms, Object.keys(terms).length > 0);
  return data;
}

/** Organisation or institution settings and terminology: draft → publish → rollback. */
export function SettingsSection() {
  const t = useTranslations("studio");
  const locale = useLocale();
  const format = useFormatter();
  const refresh = useStudioRefresh();
  const { run, failure } = useAction();
  const [institution, setInstitution] = useState("");
  const scope = institution ? { institution } : {};
  const institutions = useQuery({
    queryKey: ["tenant", "institutions"],
    queryFn: () => unwrap(api().GET("/api/v1/institutions/")),
  });
  const state = useQuery({
    queryKey: [...STUDIO_KEY, "config", institution],
    queryFn: () => unwrap(api().GET("/api/v1/customization/config/", { params: { query: scope } })),
  });
  const [edits, setEdits] = useState<{ week?: string; month?: string; rows?: Row[] }>({});
  const row = state.data;
  if (state.isError) return <Alert variant="destructive">{t("noAccess")}</Alert>;
  if (!row) return null;
  const base = (row.draft?.data ?? row.published?.data ?? {}) as Record<string, unknown>;
  const effective = row.effective as Record<string, unknown>;
  const week = edits.week ?? String(base["tenancy.week_start"] ?? "");
  const month = edits.month ?? String(base["tenancy.academic_year_start_month"] ?? "");
  const rows = edits.rows ?? toRows((base["customization.terminology"] as Terms) ?? {});
  const document = () => {
    // Start from the current document so keys this screen does not edit are kept.
    return buildDocument(base, { week, month: row.scope === "campus" ? "" : month, rows });
  };
  const after = async () => {
    setEdits({});
    await refresh();
  };
  const save = () =>
    run(async () => {
      await unwrap(
        api().PUT("/api/v1/customization/config/", {
          body: { ...scope, data: document(), note: "" },
        }),
      );
      await after();
    });
  const publish = () =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/customization/config/publish/", { body: { ...scope, note: "" } }),
      );
      await after();
    });
  const discard = () =>
    run(async () => {
      await unwrap(api().DELETE("/api/v1/customization/config/", { params: { query: scope } }));
      await after();
    });
  const rollback = (number: number) =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/customization/config/rollback/", {
          body: { ...scope, number, note: "" },
        }),
      );
      await after();
    });
  const setRow = (index: number, patch: Partial<Row>) =>
    setEdits({ ...edits, rows: rows.map((r, i) => (i === index ? { ...r, ...patch } : r)) });
  return (
    <div className="grid gap-4">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field id="config-scope" label={t("scope")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={institution}
            onChange={(e) => {
              setInstitution(e.target.value);
              setEdits({});
            }}
            {...aria}
          >
            <option value="">{t("wholeOrganisation")}</option>
            {(institutions.data ?? []).map((i) => (
              <option key={i.id} value={i.id}>
                {localName(i, locale)}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.title")}</CardTitle>
          <CardDescription>
            {row.draft
              ? t("settings.draftOpen", { number: row.draft.number })
              : t("settings.noDraft")}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              id="week-start"
              label={t("settings.weekStart")}
              hint={t("settings.effective", { value: String(effective["tenancy.week_start"]) })}
            >
              {(aria) => (
                <select
                  className={SELECT_CLASS}
                  value={week}
                  onChange={(e) => setEdits({ ...edits, week: e.target.value })}
                  {...aria}
                >
                  <option value="">{t("settings.inherit")}</option>
                  {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                    <option key={d} value={d}>
                      {t(`weekdays.${d}` as "weekdays.1")}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field
              id="year-start"
              label={t("settings.yearStart")}
              hint={t("settings.effective", {
                value: String(effective["tenancy.academic_year_start_month"]),
              })}
            >
              {(aria) => (
                <select
                  className={SELECT_CLASS}
                  value={month}
                  onChange={(e) => setEdits({ ...edits, month: e.target.value })}
                  {...aria}
                >
                  <option value="">{t("settings.inherit")}</option>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <option key={m} value={m}>
                      {format.dateTime(new Date(2026, m - 1, 1), { month: "long" })}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <div className="grid gap-2" data-testid="terminology">
            <h3 className="text-sm font-medium">{t("settings.terminology")}</h3>
            <p className="text-muted-foreground text-xs">{t("settings.terminologyHint")}</p>
            {rows.map((r, index) => (
              <div key={index} className="grid grid-cols-[4rem_1fr_1fr_auto] gap-2">
                <Input
                  aria-label={t("settings.locale")}
                  value={r.locale}
                  onChange={(e) => setRow(index, { locale: e.target.value.trim() })}
                />
                <Input
                  aria-label={t("settings.term")}
                  value={r.key}
                  onChange={(e) => setRow(index, { key: e.target.value.trim() })}
                />
                <Input
                  aria-label={t("settings.label")}
                  value={r.label}
                  onChange={(e) => setRow(index, { label: e.target.value })}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEdits({ ...edits, rows: rows.filter((_, i) => i !== index) })}
                >
                  {t("remove")}
                </Button>
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              className="justify-self-start"
              onClick={() =>
                setEdits({ ...edits, rows: [...rows, { locale, key: "unit.class", label: "" }] })
              }
            >
              {t("settings.addTerm")}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void save()}>{t("saveDraft")}</Button>
            {row.draft ? (
              <>
                <Button variant="outline" onClick={() => void publish()}>
                  {t("publish")}
                </Button>
                <Button variant="ghost" onClick={() => void discard()}>
                  {t("discard")}
                </Button>
              </>
            ) : null}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("history")}</CardTitle>
        </CardHeader>
        <CardContent>
          {row.history.length ? (
            <ul className="grid gap-2 text-sm" data-testid="history">
              {row.history.map((v) => (
                <li key={v.number} className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    {t("version", { number: v.number })} ·{" "}
                    {t(`statuses.${v.status}` as "statuses.published")}
                    {v.published_at
                      ? ` · ${format.dateTime(new Date(v.published_at), { dateStyle: "medium", timeStyle: "short" })}`
                      : ""}
                  </span>
                  {v.status === "archived" ? (
                    <Button variant="ghost" size="sm" onClick={() => void rollback(v.number)}>
                      {t("rollback")}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("noHistory")}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
