"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

import { ATTENDANCE_KEY } from "./register-sheet";
import { todayIso } from "./shared";

/** Attendance reports (Phase 8 M8; plan §8): the day's registers per unit and per-student
 * figures, each with a formula-safe CSV download. The server decides the scope (404 outside it). */
export function ReportsPanel() {
  const t = useTranslations("attendance");
  const { institution, picker } = useInstitutionChoice();
  const [day, setDay] = useState(todayIso());
  const [start, setStart] = useState(`${todayIso().slice(0, 7)}-01`);
  const daily = useQuery({
    queryKey: [...ATTENDANCE_KEY, "report-daily", institution, day],
    enabled: Boolean(institution),
    retry: false,
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/attendance/reports/daily/", {
          params: { query: { institution, date: day } },
        }),
      ),
  });
  const summary = useQuery({
    queryKey: [...ATTENDANCE_KEY, "report-students", institution, start, day],
    enabled: Boolean(institution),
    retry: false,
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/attendance/reports/students/", {
          params: { query: { institution, start, end: day } },
        }),
      ),
  });
  const csv = (path: string, query: Record<string, string>) =>
    `${path}?${new URLSearchParams({ ...query, export: "csv" }).toString()}`;
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {picker}
        <Field id="report-start" label={t("from")}>
          {(aria) => (
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} {...aria} />
          )}
        </Field>
        <Field id="report-day" label={t("to")}>
          {(aria) => (
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} {...aria} />
          )}
        </Field>
      </div>
      {daily.isError && summary.isError ? <p className="text-sm">{t("noReportAccess")}</p> : null}
      {daily.data ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t("dailyStatus", { date: day })}</CardTitle>
            <a
              className="text-primary text-sm underline"
              href={csv("/api/v1/attendance/reports/daily/", { institution, date: day })}
            >
              {t("csv")}
            </a>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm" data-testid="daily-report">
              <thead>
                <tr className="text-left">
                  <th>{t("unit")}</th>
                  <th>{t("state")}</th>
                  <th>{t("status.absent")}</th>
                </tr>
              </thead>
              <tbody>
                {daily.data.map((r) => (
                  <tr key={r.unit} className="border-t">
                    <td>{r.unit_name}</td>
                    <td>{r.state === "missing" ? t("notTaken") : t(`states.${r.state}`)}</td>
                    <td>{r.absent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
      {summary.data ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t("studentSummary")}</CardTitle>
            <a
              className="text-primary text-sm underline"
              href={csv("/api/v1/attendance/reports/students/", { institution, start, end: day })}
            >
              {t("csv")}
            </a>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm" data-testid="student-report">
              <thead>
                <tr className="text-left">
                  <th>{t("student")}</th>
                  <th>{t("unit")}</th>
                  <th>{t("status.absent")}</th>
                  <th>{t("percent")}</th>
                </tr>
              </thead>
              <tbody>
                {summary.data.map((r) => (
                  <tr key={r.student_id} className="border-t">
                    <td>{r.name}</td>
                    <td>{r.unit}</td>
                    <td>{r.absent_days}</td>
                    <td>{r.percent ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
