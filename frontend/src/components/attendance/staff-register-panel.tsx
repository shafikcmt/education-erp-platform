"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

import { ATTENDANCE_KEY } from "./register-sheet";
import { STATUSES, type Status, todayIso } from "./shared";

type Row = { status: Status; check_in: string; check_out: string };

/** The staff daily register (Phase 8 M8; plan §5): HR marks the institution, a front desk its
 * campus; check-in and check-out are optional; approved leave is pre-filled. */
export function StaffRegisterPanel() {
  const t = useTranslations("attendance");
  const queryClient = useQueryClient();
  const { run, failure } = useAction();
  const { institution, picker } = useInstitutionChoice();
  const [day, setDay] = useState(todayIso());
  // Only the marker's edits are state; everything else is derived from the server response.
  const [edits, setEdits] = useState<Record<string, Partial<Row>>>({});
  const [reason, setReason] = useState("");
  const register = useQuery({
    queryKey: [...ATTENDANCE_KEY, "staff", institution, day],
    enabled: Boolean(institution),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/attendance/staff/register/", {
          params: { query: { institution, date: day } },
        }),
      ),
  });
  const data = register.data;
  const rows = useMemo(() => {
    const out: Record<string, Row> = {};
    for (const r of data?.rows ?? []) {
      out[r.staff_id] = {
        status: r.status as Status,
        check_in: r.check_in ?? "",
        check_out: r.check_out ?? "",
        ...edits[r.staff_id],
      };
    }
    return out;
  }, [data, edits]);
  const save = () =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/attendance/staff/register/save/", {
          body: {
            institution,
            date: day,
            reason,
            entries: Object.entries(rows).map(([staff, r]) => ({
              staff,
              status: r.status,
              check_in: r.check_in || null,
              check_out: r.check_out || null,
            })),
          },
        }),
      );
      setEdits({});
      await queryClient.invalidateQueries({ queryKey: ATTENDANCE_KEY });
    });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("tabs.staff")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          {picker}
          <Field id="staff-date" label={t("date")}>
            {(aria) => (
              <Input
                type="date"
                value={day}
                max={todayIso()}
                onChange={(e) => {
                  setEdits({});
                  setDay(e.target.value);
                }}
                {...aria}
              />
            )}
          </Field>
        </div>
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {data?.outside_window ? (
          <Field id="staff-reason" label={t("reason")} hint={t("reasonHint")}>
            {(aria) => (
              <Input value={reason} onChange={(e) => setReason(e.target.value)} {...aria} />
            )}
          </Field>
        ) : null}
        <ul className="grid gap-2" data-testid="staff-register">
          {(data?.rows ?? []).map((r) => {
            const row = rows[r.staff_id];
            if (!row) return null;
            const set = (patch: Partial<Row>) =>
              setEdits({ ...edits, [r.staff_id]: { ...edits[r.staff_id], ...patch } });
            return (
              <li
                key={r.staff_id}
                className="grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-center"
              >
                <span>
                  {r.name} <span className="text-muted-foreground text-xs">{r.number}</span>
                  {r.on_leave ? <span className="ml-2 text-xs">({t("onLeave")})</span> : null}
                </span>
                <select
                  className={SELECT_CLASS}
                  aria-label={t("choose", { name: r.name })}
                  value={row.status}
                  disabled={!data?.can_mark}
                  onChange={(e) => set({ status: e.target.value as Status })}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {t(`status.${s}`)}
                    </option>
                  ))}
                </select>
                <Input
                  type="time"
                  aria-label={t("checkIn", { name: r.name })}
                  value={row.check_in}
                  disabled={!data?.can_mark}
                  onChange={(e) => set({ check_in: e.target.value })}
                />
                <Input
                  type="time"
                  aria-label={t("checkOut", { name: r.name })}
                  value={row.check_out}
                  disabled={!data?.can_mark}
                  onChange={(e) => set({ check_out: e.target.value })}
                />
              </li>
            );
          })}
        </ul>
        {data?.can_mark && data.rows.length ? (
          <div>
            <Button disabled={data.outside_window && !reason.trim()} onClick={() => void save()}>
              {t("save")}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
