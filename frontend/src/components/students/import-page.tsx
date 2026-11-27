"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { PageHeader } from "@/components/app/page-header";
import { SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { postToSlot } from "@/lib/files/upload";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { useEnrollmentChoices } from "./shared";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const MAX_BYTES = 5 * 1024 * 1024;
const FIELDS = {
  students: [
    "name",
    "number",
    "date_of_birth",
    "gender",
    "phone",
    "email",
    "guardian_name",
    "guardian_phone",
    "guardian_email",
    "guardian_relation",
    "unit",
    "roll_number",
  ],
  staff: [
    "name",
    "number",
    "gender",
    "phone",
    "email",
    "joining_date",
    "department",
    "designation",
    "employment_type",
  ],
} as const;
type Kind = keyof typeof FIELDS;
const RUNNING = new Set(["validating", "applying"]);

/** The CSV header, read in the browser to suggest the mapping (XLSX columns are typed). */
export async function csvHeader(file: File): Promise<string[]> {
  const head = await file.slice(0, 64 * 1024).text();
  const line = head.replace(/^﻿/, "").split(/\r?\n/)[0] ?? "";
  return line
    .split(",")
    .map((c) => c.trim().replace(/^"|"$/g, ""))
    .filter(Boolean);
}

async function waitUntilReady(id: string): Promise<void> {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const file = await unwrap(
      api().GET("/api/v1/files/{file_id}/", { params: { path: { file_id: id } } }),
    );
    if (file.status === "ready") return;
    if (file.status === "rejected") throw new Error("rejected");
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("timeout");
}

/** Bulk import (Phase 7 M9; ADR-072): upload, map the columns, a dry run that writes nothing,
 * then apply; every row is checked by the same rules as a single entry. */
export function ImportPage() {
  const t = useTranslations("students.import");
  const { data: context } = useTenantContext();
  const kinds = (["students", "staff"] as const).filter((k) =>
    canAnywhere(context, k === "students" ? "students.student.import" : "staff.profile.manage"),
  );
  const { institution, picker } = useInstitutionChoice();
  const { years } = useEnrollmentChoices(institution || undefined);
  const { run, failure } = useAction();
  const [kind, setKind] = useState<Kind | "">("");
  const chosenKind: Kind | undefined = kind || kinds[0];
  const [file, setFile] = useState<{ id: string; columns: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [year, setYear] = useState("");
  const [jobId, setJobId] = useState("");
  const job = useQuery({
    queryKey: ["imports", jobId],
    enabled: Boolean(jobId),
    queryFn: () =>
      unwrap(api().GET("/api/v1/imports/{job_id}/", { params: { path: { job_id: jobId } } })),
    refetchInterval: (query) =>
      RUNNING.has(query.state.data?.status ?? "validating") ? 1500 : false,
  });
  const upload = (chosen: File) =>
    run(async () => {
      if (chosen.size > MAX_BYTES) throw new Error(t("file"));
      setBusy(true);
      try {
        const type = chosen.name.toLowerCase().endsWith(".xlsx") ? XLSX : "text/csv";
        const slot = await unwrap(
          api().POST("/api/v1/files/uploads/", {
            body: {
              purpose: "students.import",
              name: chosen.name,
              size: chosen.size,
              content_type: type,
            },
          }),
        );
        await postToSlot(slot, chosen);
        await unwrap(
          api().POST("/api/v1/files/{file_id}/confirm/", {
            params: { path: { file_id: slot.file.id } },
          }),
        );
        await waitUntilReady(slot.file.id);
        const columns = type === "text/csv" ? await csvHeader(chosen) : [];
        setFile({ id: slot.file.id, columns });
        setMapping(
          Object.fromEntries(
            (chosenKind ? FIELDS[chosenKind] : []).flatMap((field) => {
              const match = columns.find((c) => c.toLowerCase().replace(/[\s-]+/g, "_") === field);
              return match ? [[field, match]] : [];
            }),
          ),
        );
        setJobId("");
      } finally {
        setBusy(false);
      }
    });
  const start = () =>
    run(async () => {
      if (!chosenKind || !file) return;
      const body = Object.fromEntries(
        Object.entries(mapping)
          .filter(([, column]) => column.trim())
          .map(([field, column]) => [column.trim(), field]),
      );
      const created = await unwrap(
        api().POST("/api/v1/imports/", {
          body: {
            institution,
            kind: chosenKind,
            file: file.id,
            mapping: body,
            options: chosenKind === "students" && year ? { year } : {},
          },
        }),
      );
      setJobId(created.id);
    });
  const apply = () =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/imports/{job_id}/apply/", { params: { path: { job_id: jobId } } }),
      );
      await job.refetch();
    });
  const current = job.data;
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="grid gap-4">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        <Card>
          <CardContent className="grid gap-3 pt-6 sm:grid-cols-3">
            {picker}
            <Field id="import-kind" label={t("kind")}>
              {(aria) => (
                <select
                  className={SELECT_CLASS}
                  value={chosenKind ?? ""}
                  onChange={(e) => {
                    setKind(e.target.value as Kind);
                    setFile(null);
                    setJobId("");
                  }}
                  {...aria}
                >
                  {kinds.map((k) => (
                    <option key={k} value={k}>
                      {t(`kinds.${k}`)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field id="import-file" label={t("file")}>
              {(aria) => (
                <Input
                  type="file"
                  accept=".csv,.xlsx,text/csv"
                  disabled={busy || !chosenKind}
                  onChange={(e) => {
                    const chosen = e.target.files?.[0];
                    if (chosen) void upload(chosen);
                  }}
                  {...aria}
                />
              )}
            </Field>
            {busy ? <p className="text-muted-foreground text-sm">{t("uploading")}</p> : null}
          </CardContent>
        </Card>
        {file && chosenKind ? (
          <Card>
            <CardHeader>
              <CardTitle>{t("mapping")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <p className="text-muted-foreground text-sm">{t("ready")}</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {FIELDS[chosenKind].map((field) => (
                  <Field key={field} id={`map-${field}`} label={t(`targets.${field}`)}>
                    {(aria) =>
                      file.columns.length ? (
                        <select
                          className={SELECT_CLASS}
                          value={mapping[field] ?? ""}
                          onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
                          {...aria}
                        >
                          <option value="">{t("skip")}</option>
                          {file.columns.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <Input
                          value={mapping[field] ?? ""}
                          placeholder={t("column")}
                          onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
                          {...aria}
                        />
                      )
                    }
                  </Field>
                ))}
                {chosenKind === "students" ? (
                  <Field id="import-year" label={t("year")}>
                    {(aria) => (
                      <select
                        className={SELECT_CLASS}
                        value={year}
                        onChange={(e) => setYear(e.target.value)}
                        {...aria}
                      >
                        <option value="">—</option>
                        {years.map((y) => (
                          <option key={y.id} value={y.id}>
                            {y.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </Field>
                ) : null}
              </div>
              <div>
                <Button
                  disabled={!mapping.name?.trim() || Boolean(jobId)}
                  onClick={() => void start()}
                >
                  {t("start")}
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
        {current ? (
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>
                {t("status")}: {t(`statuses.${current.status}`)}
              </CardTitle>
              <div className="flex gap-2">
                {current.status === "validated" && current.ok_rows > 0 ? (
                  <Button onClick={() => void apply()}>{t("apply")}</Button>
                ) : null}
                {current.report.length ? (
                  <Button variant="outline" asChild>
                    <a href={`/api/v1/imports/${current.id}/report/`}>{t("report")}</a>
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm">
              {current.error ? <Alert variant="destructive">{current.error}</Alert> : null}
              {current.total_rows ? (
                <p data-testid="import-summary">
                  {t("rows", { ok: current.ok_rows, total: current.total_rows })}
                </p>
              ) : null}
              {current.report.some((r) => !r.ok) ? (
                <table className="w-full border-collapse text-xs" data-testid="import-errors">
                  <thead>
                    <tr>
                      <th className="border p-1 text-left">{t("row")}</th>
                      <th className="border p-1 text-left">{t("errors")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.report
                      .filter((r) => !r.ok)
                      .slice(0, 200)
                      .map((r) => (
                        <tr key={r.row}>
                          <td className="border p-1">{r.row}</td>
                          <td className="border p-1">
                            {Object.entries(r.errors)
                              .map(([k, v]) => `${k}: ${v}`)
                              .join("; ")}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </>
  );
}
