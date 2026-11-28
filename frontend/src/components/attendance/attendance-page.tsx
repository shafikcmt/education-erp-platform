"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { Tabs } from "@/components/admissions/shared";
import { PageHeader } from "@/components/app/page-header";
import { useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { LeavePanel } from "./leave-panel";
import { ReportsPanel } from "./reports-panel";
import { ATTENDANCE_KEY, RegisterSheet } from "./register-sheet";
import { todayIso } from "./shared";
import { StaffRegisterPanel } from "./staff-register-panel";

type Tab = "today" | "registers" | "leave" | "staff" | "reports";

/** Attendance (Phase 8 M8): today's registers for teachers with the quick-mark screen, an
 * institution's registers for coordinators, leave requests, the staff register and reports.
 * Each tab shows only with its permission; the server decides what each list contains. */
export function AttendancePage() {
  const t = useTranslations("attendance");
  const { data: context } = useTenantContext();
  const has = (code: string) => canAnywhere(context, code);
  const tabs: Tab[] = [];
  if (has("attendance.record.mark") || has("attendance.record.manage")) tabs.push("today");
  if (has("attendance.record.view") || has("attendance.record.manage")) tabs.push("registers");
  if (has("attendance.leave.request") || has("attendance.leave.review")) tabs.push("leave");
  if (has("attendance.staff.mark") || has("attendance.staff.view")) tabs.push("staff");
  if (has("attendance.report.view")) tabs.push("reports");
  const [active, setActive] = useState<Tab | null>(null);
  const current: Tab = active ?? tabs[0] ?? "today";
  const [open, setOpen] = useState("");
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      {open ? (
        <RegisterSheet registerId={open} onClose={() => setOpen("")} />
      ) : (
        <>
          {tabs.length > 1 ? (
            <Tabs
              label={t("title")}
              tabs={tabs}
              current={current}
              onChange={setActive}
              name={(key) => t(`tabs.${key}`)}
            />
          ) : null}
          {current === "today" ? <TodayPanel onOpen={setOpen} /> : null}
          {current === "registers" ? <RegistersPanel onOpen={setOpen} /> : null}
          {current === "leave" ? <LeavePanel /> : null}
          {current === "staff" ? <StaffRegisterPanel /> : null}
          {current === "reports" ? <ReportsPanel /> : null}
        </>
      )}
    </>
  );
}

function TodayPanel({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useTranslations("attendance");
  const queryClient = useQueryClient();
  const { run, failure } = useAction();
  const [day, setDay] = useState(todayIso());
  const due = useQuery({
    queryKey: [...ATTENDANCE_KEY, "due", day],
    queryFn: () =>
      unwrap(api().GET("/api/v1/attendance/due/", { params: { query: { date: day } } })),
  });
  const open = (row: {
    kind: string;
    unit: string;
    offering: string | null;
    register: { id: string } | null;
  }) =>
    run(async () => {
      if (row.register) {
        onOpen(row.register.id);
        return;
      }
      const created = await unwrap(
        api().POST("/api/v1/attendance/registers/", {
          body: {
            kind: row.kind as "daily" | "period",
            date: day,
            unit: row.kind === "daily" ? row.unit : null,
            offering: row.offering,
            sequence: 1,
          },
        }),
      );
      await queryClient.invalidateQueries({ queryKey: ATTENDANCE_KEY });
      onOpen(created.register.id);
    });
  return (
    <div className="grid gap-4">
      <div className="max-w-xs">
        <Field id="today-date" label={t("date")}>
          {(aria) => (
            <Input
              type="date"
              value={day}
              max={todayIso()}
              onChange={(e) => setDay(e.target.value)}
              {...aria}
            />
          )}
        </Field>
      </div>
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      {due.data && !due.data.length ? (
        <p className="text-muted-foreground text-sm">{t("nothingDue")}</p>
      ) : null}
      <ul className="grid gap-2 sm:grid-cols-2" data-testid="due-list">
        {(due.data ?? []).map((row) => (
          <li key={`${row.kind}-${row.unit}-${row.offering ?? ""}`}>
            <Card>
              <CardContent className="flex items-center justify-between gap-3 pt-6">
                <div>
                  <p className="font-medium">
                    {row.unit_name}
                    {row.subject_name ? ` · ${row.subject_name}` : ""}
                  </p>
                  <p className="text-muted-foreground text-sm">
                    {t(`kinds.${row.kind}`)} ·{" "}
                    {row.register ? t(`states.${row.register.state}`) : t("notTaken")}
                  </p>
                </div>
                <Button onClick={() => void open(row)}>
                  {row.register ? t("openRegister") : t("take")}
                </Button>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RegistersPanel({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useTranslations("attendance");
  const { institution, picker } = useInstitutionChoice();
  const [day, setDay] = useState(todayIso());
  const list = useQuery({
    queryKey: [...ATTENDANCE_KEY, "registers", institution, day],
    enabled: Boolean(institution),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/attendance/registers/", {
          params: { query: { institution, date: day } },
        }),
      ),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("tabs.registers")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          {picker}
          <Field id="registers-date" label={t("date")}>
            {(aria) => (
              <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} {...aria} />
            )}
          </Field>
        </div>
        {list.data && !list.data.length ? (
          <p className="text-muted-foreground text-sm">{t("noRegisters")}</p>
        ) : null}
        <ul className="grid gap-2">
          {(list.data ?? []).map((r) => (
            <li
              key={r.id}
              className="flex items-center justify-between gap-3 rounded-md border p-3"
            >
              <span>
                {r.unit_name}
                {r.subject_name ? ` · ${r.subject_name}` : ""} · {t(`states.${r.state}`)}
              </span>
              <Button size="sm" variant="outline" onClick={() => onOpen(r.id)}>
                {t("openRegister")}
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
