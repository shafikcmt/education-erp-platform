"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ActionDialog, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { ATTENDANCE_KEY } from "./register-sheet";
import { todayIso } from "./shared";

/** Leave requests (Phase 8 M8; plan §6): the requests I can see, a decision for reviewers and
 * cancelling. New requests come from the portal (children, oneself) or from {@link LeaveForm}. */
export function LeavePanel() {
  const t = useTranslations("attendance");
  const { data: context } = useTenantContext();
  const reviewer = canAnywhere(context, "attendance.leave.review");
  const queryClient = useQueryClient();
  const { run, failure } = useAction();
  const list = useQuery({
    queryKey: [...ATTENDANCE_KEY, "leave"],
    queryFn: () => unwrap(api().GET("/api/v1/attendance/leave/")),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ATTENDANCE_KEY });
  const cancel = (id: string) =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/attendance/leave/{leave_id}/cancel/", {
          params: { path: { leave_id: id } },
        }),
      );
      await refresh();
    });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("tabs.leave")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {list.data && !list.data.length ? (
          <p className="text-muted-foreground text-sm">{t("noLeave")}</p>
        ) : null}
        <ul className="grid gap-2" data-testid="leave-list">
          {(list.data ?? []).map((row) => (
            <li
              key={row.id}
              className="grid gap-2 rounded-md border p-3 sm:flex sm:items-center sm:justify-between"
            >
              <div className="text-sm">
                <p className="font-medium">{row.student_name || row.staff_name}</p>
                <p>
                  {row.start_date}
                  {row.end_date !== row.start_date ? ` – ${row.end_date}` : ""} · {row.reason}
                </p>
                <p className="text-muted-foreground">{t(`leaveStates.${row.state}`)}</p>
              </div>
              <div className="flex gap-2">
                {reviewer && row.state === "pending" ? (
                  <DecideDialog id={row.id} onDone={refresh} />
                ) : null}
                {row.state === "pending" ||
                (row.state === "approved" && row.start_date > todayIso()) ? (
                  <Button size="sm" variant="outline" onClick={() => void cancel(row.id)}>
                    {t("cancelLeave")}
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function DecideDialog({ id, onDone }: { id: string; onDone: () => Promise<unknown> }) {
  const t = useTranslations("attendance");
  const [note, setNote] = useState("");
  const [approve, setApprove] = useState(true);
  return (
    <ActionDialog
      trigger={<Button size="sm">{t("decide")}</Button>}
      title={t("decide")}
      submit={approve ? t("approve") : t("reject")}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/attendance/leave/{leave_id}/decide/", {
            params: { path: { leave_id: id } },
            body: { approve, note },
          }),
        );
        await onDone();
      }}
    >
      <div className="flex gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" checked={approve} onChange={() => setApprove(true)} />
          {t("approve")}
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" checked={!approve} onChange={() => setApprove(false)} />
          {t("reject")}
        </label>
      </div>
      <Field id="leave-note" label={t("note")}>
        {(aria) => <Input value={note} onChange={(e) => setNote(e.target.value)} {...aria} />}
      </Field>
    </ActionDialog>
  );
}

/** Request leave for a student (portal) or a staff member (one's own profile). */
export function LeaveForm({ student, staff }: { student?: string; staff?: string }) {
  const t = useTranslations("attendance");
  const queryClient = useQueryClient();
  const [start, setStart] = useState(todayIso());
  const [end, setEnd] = useState(todayIso());
  const [reason, setReason] = useState("");
  return (
    <ActionDialog
      trigger={<Button variant="outline">{t("requestLeave")}</Button>}
      title={t("requestLeave")}
      submit={t("send")}
      disabled={!reason.trim() || end < start}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/attendance/leave/", {
            body: {
              student: student ?? null,
              staff: staff ?? null,
              start_date: start,
              end_date: end,
              half_day: false,
              reason,
            },
          }),
        );
        setReason("");
        await queryClient.invalidateQueries({ queryKey: ATTENDANCE_KEY });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="leave-start" label={t("from")}>
          {(aria) => (
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} {...aria} />
          )}
        </Field>
        <Field id="leave-end" label={t("to")}>
          {(aria) => (
            <Input
              type="date"
              value={end}
              min={start}
              onChange={(e) => setEnd(e.target.value)}
              {...aria}
            />
          )}
        </Field>
      </div>
      <Field id="leave-reason" label={t("reason")}>
        {(aria) => (
          <Input
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
            {...aria}
          />
        )}
      </Field>
    </ActionDialog>
  );
}
