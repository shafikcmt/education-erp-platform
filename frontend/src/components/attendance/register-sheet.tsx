"use client";

import type { Schemas } from "@erp/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { STATUSES, type Status, changedEntries, countByStatus, nextStatus } from "./shared";

type Detail = Schemas["RegisterDetail"];
export const ATTENDANCE_KEY = ["attendance"] as const;

const TONE: Record<Status, string> = {
  present:
    "border-emerald-600 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
  absent: "border-red-600 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100",
  late: "border-amber-600 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  excused: "border-sky-600 bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100",
  leave: "border-violet-600 bg-violet-50 text-violet-900 dark:bg-violet-950 dark:text-violet-100",
};

function initialStatuses(detail: Detail): Record<string, Status> {
  return Object.fromEntries(detail.roster.map((r) => [r.student_id, r.status as Status]));
}

/** The quick-mark screen (Phase 8 M8; plan §4, §13): one large button per student, everyone
 * starting with the configured default; a tap cycles present → absent → late. Save sends the
 * whole change with the register's version; a newer version on the server (409) is shown and
 * the marker reloads. Past the edit window a reason (and step-up) is needed; locked registers
 * need an unlock by a manager. */
export function RegisterSheet({
  registerId,
  onClose,
}: {
  registerId: string;
  onClose: () => void;
}) {
  const t = useTranslations("attendance");
  const register = useQuery({
    queryKey: [...ATTENDANCE_KEY, "register", registerId],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/attendance/registers/{register_id}/", {
          params: { path: { register_id: registerId } },
        }),
      ),
  });
  if (!register.data) {
    return <p className="text-muted-foreground text-sm">{t("loading")}</p>;
  }
  // A new version from the server (save, reload) remounts the sheet with fresh statuses.
  return (
    <RegisterBody
      key={`${register.data.register.version}-${register.dataUpdatedAt}`}
      detail={register.data}
      registerId={registerId}
      onClose={onClose}
      reload={() => register.refetch()}
    />
  );
}

function RegisterBody({
  detail,
  registerId,
  onClose,
  reload: refetch,
}: {
  detail: Detail;
  registerId: string;
  onClose: () => void;
  reload: () => Promise<unknown>;
}) {
  const t = useTranslations("attendance");
  const queryClient = useQueryClient();
  const { run, failure } = useAction();
  const initial = useMemo(() => initialStatuses(detail), [detail]);
  const [statuses, setStatuses] = useState<Record<string, Status>>(initial);
  const [reason, setReason] = useState("");
  const [stale, setStale] = useState(false);
  const [saved, setSaved] = useState(false);
  // Rows never saved (default or leave) are sent on the first save, so every student gets a status.
  const unsaved = useMemo(
    () =>
      new Set(detail.roster.filter((r) => r.status_source !== "saved").map((r) => r.student_id)),
    [detail],
  );
  const locked = detail.register.state === "locked";
  const counts = countByStatus(Object.values(statuses));
  const entries = changedEntries(initial, statuses, unsaved);

  const reload = async () => {
    setStale(false);
    await refetch();
  };
  const save = (submit: boolean) =>
    run(async () => {
      let current: Detail = detail;
      try {
        if (entries.length) {
          current = await unwrap(
            api().POST("/api/v1/attendance/registers/{register_id}/save/", {
              params: { path: { register_id: registerId } },
              body: { version: current.register.version, entries, reason },
            }),
          );
        }
        if (submit && current.register.state === "open") {
          current = await unwrap(
            api().POST("/api/v1/attendance/registers/{register_id}/submit/", {
              params: { path: { register_id: registerId } },
              body: { version: current.register.version },
            }),
          );
        }
      } catch (error) {
        if (isApiError(error, "stale_register")) {
          setStale(true);
          return;
        }
        throw error;
      }
      queryClient.setQueryData([...ATTENDANCE_KEY, "register", registerId], current);
      await queryClient.invalidateQueries({ queryKey: ATTENDANCE_KEY });
      setSaved(true);
    });

  const title = detail.register.subject_name
    ? `${detail.register.unit_name} · ${detail.register.subject_name}`
    : detail.register.unit_name;
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>
          {title} · {detail.register.date}
        </CardTitle>
        <div className="flex items-center gap-2 text-sm">
          <span data-testid="register-state">{t(`states.${detail.register.state}`)}</span>
          <Button variant="outline" size="sm" onClick={onClose}>
            {t("back")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 pb-24">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {stale ? (
          <Alert variant="destructive">
            <div className="flex flex-wrap items-center gap-3">
              <span>{t("stale")}</span>
              <Button size="sm" variant="outline" onClick={() => void reload()}>
                {t("reload")}
              </Button>
            </div>
          </Alert>
        ) : null}
        {saved && !entries.length ? <p className="text-sm text-emerald-700">{t("saved")}</p> : null}
        {locked ? (
          <Alert>
            <div className="flex flex-wrap items-center gap-3">
              <span>{t("locked")}</span>
              {detail.can_manage ? <UnlockDialog registerId={registerId} /> : null}
            </div>
          </Alert>
        ) : null}
        {detail.outside_window && !locked ? (
          <Field id="register-reason" label={t("reason")} hint={t("reasonHint")}>
            {(aria) => (
              <Input value={reason} onChange={(e) => setReason(e.target.value)} {...aria} />
            )}
          </Field>
        ) : null}
        <p className="text-muted-foreground text-sm" data-testid="register-counts">
          {STATUSES.map((s) => `${t(`status.${s}`)} ${counts[s]}`).join(" · ")}
        </p>
        <ul className="grid gap-2" aria-label={t("roster")}>
          {detail.roster.map((row) => {
            const value = statuses[row.student_id] ?? (row.status as Status);
            return (
              <li key={row.student_id} className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={locked || !detail.can_mark}
                  aria-label={`${row.name}: ${t(`status.${value}`)}`}
                  onClick={() => setStatuses({ ...statuses, [row.student_id]: nextStatus(value) })}
                  className={cn(
                    "flex min-h-12 flex-1 items-center justify-between rounded-md border-2 px-3 text-left",
                    TONE[value],
                  )}
                >
                  <span>
                    <span className="text-muted-foreground mr-2 tabular-nums">
                      {row.roll_number || "·"}
                    </span>
                    {row.name}
                    {row.on_leave ? <span className="ml-2 text-xs">({t("onLeave")})</span> : null}
                  </span>
                  <span className="font-medium">{t(`status.${value}`)}</span>
                </button>
                <select
                  className={cn(SELECT_CLASS, "w-28")}
                  aria-label={t("choose", { name: row.name })}
                  value={value}
                  disabled={locked || !detail.can_mark}
                  onChange={(e) =>
                    setStatuses({ ...statuses, [row.student_id]: e.target.value as Status })
                  }
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {t(`status.${s}`)}
                    </option>
                  ))}
                </select>
              </li>
            );
          })}
        </ul>
        {!detail.roster.length ? <p className="text-sm">{t("emptyRoster")}</p> : null}
        {detail.can_mark && !locked ? (
          <div className="bg-background fixed inset-x-0 bottom-0 z-10 flex justify-end gap-2 border-t p-3 sm:static sm:border-0 sm:p-0">
            <Button
              variant="outline"
              disabled={!entries.length || (detail.outside_window && !reason.trim())}
              onClick={() => void save(false)}
            >
              {t("save")}
            </Button>
            {detail.register.state === "open" ? (
              <Button
                disabled={detail.outside_window && !reason.trim()}
                onClick={() => void save(true)}
              >
                {t("submit")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function UnlockDialog({ registerId }: { registerId: string }) {
  const t = useTranslations("attendance");
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  return (
    <ActionDialog
      trigger={<Button size="sm">{t("unlock")}</Button>}
      title={t("unlockTitle")}
      submit={t("unlock")}
      disabled={!reason.trim()}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/attendance/registers/{register_id}/unlock/", {
            params: { path: { register_id: registerId } },
            body: { reason },
          }),
        );
        await queryClient.invalidateQueries({ queryKey: ATTENDANCE_KEY });
      }}
    >
      <Field id="unlock-reason" label={t("reason")}>
        {(aria) => <Input value={reason} onChange={(e) => setReason(e.target.value)} {...aria} />}
      </Field>
    </ActionDialog>
  );
}
