"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";
import { isEntitled } from "@/lib/tenancy/entitlements";

import { LeaveForm } from "./leave-panel";
import { ATTENDANCE_KEY } from "./register-sheet";
import { monthIso } from "./shared";

/** A child's (or my own) attendance in the portal (Phase 8 M8): the month's days, the year's
 * percentage, a low-attendance flag, leave requests and a leave form. Shown only when the
 * organisation has the attendance module. */
export function PortalAttendance({ studentId }: { studentId: string }) {
  const t = useTranslations("attendance");
  const { data: context } = useTenantContext();
  const enabled = isEntitled(context, "attendance");
  const canRequest = canAnywhere(context, "attendance.leave.request");
  const [month, setMonth] = useState(monthIso());
  const data = useQuery({
    queryKey: [...ATTENDANCE_KEY, "portal", studentId, month],
    enabled: enabled && Boolean(studentId),
    retry: false,
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/attendance/portal/students/{student_id}/", {
          params: { path: { student_id: studentId }, query: { month } },
        }),
      ),
  });
  if (!enabled || !data.data) return null;
  const view = data.data;
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("portalTitle")}</CardTitle>
        {canRequest ? <LeaveForm student={studentId} /> : null}
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="max-w-xs">
          <Field id="portal-month" label={t("month")}>
            {(aria) => (
              <Input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                {...aria}
              />
            )}
          </Field>
        </div>
        <p data-testid="portal-percent">
          {t("yearPercent", { percent: view.percent ?? "—" })} · {t("status.absent")}{" "}
          {view.absent_days} · {t("status.late")} {view.late_days}
        </p>
        {view.flagged ? <p className="font-medium text-red-700">{t("flagged")}</p> : null}
        <ul className="grid grid-cols-2 gap-1 sm:grid-cols-4" data-testid="portal-days">
          {Object.entries(view.days).map(([date, status]) => (
            <li key={date} className="rounded border px-2 py-1">
              {date.slice(8)} · {t(`status.${status as "present"}`)}
            </li>
          ))}
        </ul>
        {!Object.keys(view.days).length ? (
          <p className="text-muted-foreground">{t("noDays")}</p>
        ) : null}
        {view.leave.length ? (
          <ul className="grid gap-1">
            {view.leave.map((l) => (
              <li key={l.id}>
                {l.start_date}
                {l.end_date !== l.start_date ? ` – ${l.end_date}` : ""} ·{" "}
                {t(`leaveStates.${l.state}`)}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
