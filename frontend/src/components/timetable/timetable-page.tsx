"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { Tabs } from "@/components/admissions/shared";
import { PageHeader } from "@/components/app/page-header";
import { useEnrollmentChoices } from "@/components/students/shared";
import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

const KEY = ["timetable"] as const;
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
/** What the grid shows of a lesson (slots and the portal's lessons both fit). */
type Lesson = {
  id?: string;
  weekday: number;
  start_time: string;
  end_time: string;
  period_name: string;
  subject_name: string;
  room_code: string;
  unit_name?: string;
};
type Tab = "units" | "mine";

function useRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

/** Timetables (Phase 7 M9): a unit's week for staff, my lessons for teachers, and the bell
 * schedules, rooms and lessons for managers. The server refuses clashes and hides what the
 * member may not see. */
export function TimetablePage() {
  const t = useTranslations("timetable");
  const { data: context } = useTenantContext();
  const staff = canAnywhere(context, "academics.structure.view");
  const manage = canAnywhere(context, "timetable.timetable.manage");
  const tabs: Tab[] = staff ? ["units", "mine"] : ["mine"];
  const [active, setActive] = useState<Tab | null>(null);
  const current: Tab = active ?? tabs[0] ?? "mine";
  const { institution, picker } = useInstitutionChoice();
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <Tabs
        label={t("title")}
        tabs={tabs}
        current={current}
        onChange={setActive}
        name={(key) => t(`tabs.${key}`)}
      />
      {current === "mine" ? <MyLessons /> : null}
      {current === "units" ? (
        <>
          <div className="mb-4 max-w-sm">{picker}</div>
          {institution ? (
            <div className="grid gap-4">
              <UnitTimetable institution={institution} manage={manage} />
              {manage ? <Setup institution={institution} /> : null}
            </div>
          ) : null}
        </>
      ) : null}
    </>
  );
}

/** The days that have lessons (Monday first) and the distinct start times, in order. */
export function weekLayout(lessons: { weekday: number; start_time: string }[]) {
  return {
    days: WEEKDAYS.filter((d) => lessons.some((l) => l.weekday === d)),
    times: [...new Set(lessons.map((l) => l.start_time))].sort(),
  };
}

/** A week as a grid: one row per start time, one column per day with lessons. */
export function WeekGrid({
  lessons,
  onRemove,
}: {
  lessons: Lesson[];
  onRemove?: (id: string) => void;
}) {
  const t = useTranslations("timetable");
  if (!lessons.length) return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  const { days, times } = weekLayout(lessons);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] border-collapse text-sm" data-testid="week-grid">
        <thead>
          <tr>
            <th className="border p-2 text-left font-medium">{t("time")}</th>
            {days.map((d) => (
              <th key={d} className="border p-2 text-left font-medium">
                {t(`days.${d}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {times.map((time) => (
            <tr key={time}>
              <th className="text-muted-foreground border p-2 text-left text-xs font-normal">
                {time.slice(0, 5)}
              </th>
              {days.map((d) => {
                const here = lessons.filter((l) => l.weekday === d && l.start_time === time);
                return (
                  <td key={d} className="border p-2 align-top">
                    {here.map((l, i) => (
                      <div key={l.id ?? i} className="grid">
                        <span className="font-medium">{l.subject_name}</span>
                        <span className="text-muted-foreground text-xs">
                          {[l.period_name, l.unit_name, l.room_code].filter(Boolean).join(" · ")}
                        </span>
                        {onRemove && l.id ? (
                          <button
                            type="button"
                            className="text-destructive justify-self-start text-xs underline"
                            onClick={() => onRemove(l.id!)}
                          >
                            {t("remove")}
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MyLessons() {
  const t = useTranslations("timetable");
  const mine = useQuery({
    queryKey: [...KEY, "mine"],
    queryFn: () => unwrap(api().GET("/api/v1/timetable/my/")),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("tabs.mine")}</CardTitle>
      </CardHeader>
      <CardContent>
        <WeekGrid lessons={mine.data ?? []} />
      </CardContent>
    </Card>
  );
}

function UnitTimetable({ institution, manage }: { institution: string; manage: boolean }) {
  const t = useTranslations("timetable");
  const refresh = useRefresh();
  const { run, failure } = useAction();
  const { years, leafUnits } = useEnrollmentChoices(institution);
  const [unit, setUnit] = useState("");
  const slots = useQuery({
    queryKey: [...KEY, "unit", unit],
    enabled: Boolean(unit),
    queryFn: () => unwrap(api().GET("/api/v1/timetable/slots/", { params: { query: { unit } } })),
  });
  const remove = (id: string) =>
    void run(async () => {
      await unwrap(
        api().DELETE("/api/v1/timetable/slots/{slot_id}/", { params: { path: { slot_id: id } } }),
      );
      await refresh();
    });
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-2">
        <Field id="timetable-unit" label={t("unit")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              {...aria}
            >
              <option value="">—</option>
              {leafUnits.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name} ({u.code})
                </option>
              ))}
            </select>
          )}
        </Field>
        {manage && unit ? <AddLesson institution={institution} unit={unit} years={years} /> : null}
      </CardHeader>
      <CardContent className="grid gap-2">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {unit ? (
          <WeekGrid lessons={slots.data ?? []} onRemove={manage ? remove : undefined} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function AddLesson({
  institution,
  unit,
  years,
}: {
  institution: string;
  unit: string;
  years: { id: string; name: string }[];
}) {
  const t = useTranslations("timetable");
  const refresh = useRefresh();
  const [form, setForm] = useState({ year: "", offering: "", weekday: "1", period: "", room: "" });
  const offerings = useQuery({
    queryKey: [...KEY, "offerings", form.year],
    enabled: Boolean(form.year),
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/offerings/", { params: { query: { year: form.year } } })),
  });
  const subjects = useQuery({
    queryKey: ["academics", "subjects", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/academics/subjects/", { params: { query: { institution } } })),
  });
  const schedules = useSchedules(institution);
  const rooms = useRooms(institution);
  const subjectName = (id: string) => subjects.data?.find((s) => s.id === id)?.name ?? id;
  const periods = (schedules.data ?? []).flatMap((s) =>
    s.periods.filter((p) => !p.is_break).map((p) => ({ ...p, schedule: s.name })),
  );
  const select = (
    key: keyof typeof form,
    options: { id: string; label: string }[],
    blank = true,
  ) => (
    <Field id={`lesson-${key}`} label={t(`lesson.${key}`)}>
      {(aria) => (
        <select
          className={SELECT_CLASS}
          value={form[key]}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          {...aria}
        >
          {blank ? <option value="">—</option> : null}
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
  return (
    <ActionDialog
      trigger={<Button size="sm">{t("lesson.add")}</Button>}
      title={t("lesson.add")}
      description={t("lesson.hint")}
      submit={t("save")}
      disabled={!form.offering || !form.period}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/timetable/slots/", {
            body: {
              offering: form.offering,
              weekday: Number(form.weekday),
              period: form.period,
              room: form.room || null,
            },
          }),
        );
        setForm({ ...form, offering: "", period: "", room: "" });
        await refresh();
      }}
    >
      {select(
        "year",
        years.map((y) => ({ id: y.id, label: y.name })),
      )}
      {select(
        "offering",
        (offerings.data ?? [])
          .filter((o) => o.unit === unit)
          .map((o) => ({ id: o.id, label: subjectName(o.subject) })),
      )}
      {select(
        "weekday",
        WEEKDAYS.map((d) => ({ id: String(d), label: t(`days.${d}`) })),
        false,
      )}
      {select(
        "period",
        periods.map((p) => ({
          id: p.id,
          label: `${p.schedule} · ${p.name} (${p.start_time.slice(0, 5)}–${p.end_time.slice(0, 5)})`,
        })),
      )}
      {select(
        "room",
        (rooms.data ?? []).map((r) => ({ id: r.id, label: `${r.code} · ${r.name}` })),
      )}
    </ActionDialog>
  );
}

function useSchedules(institution: string) {
  return useQuery({
    queryKey: [...KEY, "schedules", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/timetable/schedules/", { params: { query: { institution } } })),
  });
}

function useRooms(institution: string) {
  return useQuery({
    queryKey: [...KEY, "rooms", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/timetable/rooms/", { params: { query: { institution } } })),
  });
}

function Setup({ institution }: { institution: string }) {
  const t = useTranslations("timetable");
  const refresh = useRefresh();
  const schedules = useSchedules(institution);
  const rooms = useRooms(institution);
  const [schedule, setSchedule] = useState({ code: "", name: "" });
  const [room, setRoom] = useState({ code: "", name: "", capacity: "" });
  const [period, setPeriod] = useState({
    schedule: "",
    order: "1",
    name: "",
    start_time: "",
    end_time: "",
    is_break: false,
  });
  const text = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    type = "text",
  ) => (
    <Field id={id} label={label}>
      {(aria) => (
        <Input type={type} value={value} onChange={(e) => onChange(e.target.value)} {...aria} />
      )}
    </Field>
  );
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("schedules")}</CardTitle>
          <div className="flex gap-2">
            <ActionDialog
              trigger={<Button size="sm">{t("addSchedule")}</Button>}
              title={t("addSchedule")}
              submit={t("save")}
              disabled={!schedule.code.trim() || !schedule.name.trim()}
              onSubmit={async () => {
                await unwrap(
                  api().POST("/api/v1/timetable/schedules/", {
                    body: { institution, ...schedule },
                  }),
                );
                setSchedule({ code: "", name: "" });
                await refresh();
              }}
            >
              {text("schedule-code", t("code"), schedule.code, (code) =>
                setSchedule({ ...schedule, code }),
              )}
              {text("schedule-name", t("name"), schedule.name, (name) =>
                setSchedule({ ...schedule, name }),
              )}
            </ActionDialog>
            {schedules.data?.length ? (
              <ActionDialog
                trigger={
                  <Button size="sm" variant="outline">
                    {t("addPeriod")}
                  </Button>
                }
                title={t("addPeriod")}
                submit={t("save")}
                disabled={
                  !period.schedule || !period.name.trim() || !period.start_time || !period.end_time
                }
                onSubmit={async () => {
                  await unwrap(
                    api().POST("/api/v1/timetable/schedules/{schedule_id}/periods/", {
                      params: { path: { schedule_id: period.schedule } },
                      body: {
                        order: Number(period.order),
                        name: period.name.trim(),
                        start_time: period.start_time,
                        end_time: period.end_time,
                        is_break: period.is_break,
                      },
                    }),
                  );
                  setPeriod({ ...period, order: String(Number(period.order) + 1), name: "" });
                  await refresh();
                }}
              >
                <Field id="period-schedule" label={t("schedule")}>
                  {(aria) => (
                    <select
                      className={SELECT_CLASS}
                      value={period.schedule}
                      onChange={(e) => setPeriod({ ...period, schedule: e.target.value })}
                      {...aria}
                    >
                      <option value="">—</option>
                      {schedules.data.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                {text(
                  "period-order",
                  t("order"),
                  period.order,
                  (order) => setPeriod({ ...period, order }),
                  "number",
                )}
                {text("period-name", t("name"), period.name, (name) =>
                  setPeriod({ ...period, name }),
                )}
                {text(
                  "period-start",
                  t("start"),
                  period.start_time,
                  (start_time) => setPeriod({ ...period, start_time }),
                  "time",
                )}
                {text(
                  "period-end",
                  t("end"),
                  period.end_time,
                  (end_time) => setPeriod({ ...period, end_time }),
                  "time",
                )}
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={period.is_break}
                    onChange={(e) => setPeriod({ ...period, is_break: e.target.checked })}
                  />
                  {t("break")}
                </label>
              </ActionDialog>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          {schedules.data?.length ? (
            <ul className="grid gap-2 text-sm">
              {schedules.data.map((s) => (
                <li key={s.id}>
                  <span className="font-medium">{s.name}</span>{" "}
                  <span className="text-muted-foreground text-xs">
                    {s.periods
                      .map(
                        (p) =>
                          `${p.name} ${p.start_time.slice(0, 5)}${p.is_break ? ` (${t("break")})` : ""}`,
                      )
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("rooms")}</CardTitle>
          <ActionDialog
            trigger={<Button size="sm">{t("addRoom")}</Button>}
            title={t("addRoom")}
            submit={t("save")}
            disabled={!room.code.trim() || !room.name.trim()}
            onSubmit={async () => {
              await unwrap(
                api().POST("/api/v1/timetable/rooms/", {
                  body: {
                    institution,
                    code: room.code.trim(),
                    name: room.name.trim(),
                    capacity: room.capacity ? Number(room.capacity) : null,
                  },
                }),
              );
              setRoom({ code: "", name: "", capacity: "" });
              await refresh();
            }}
          >
            {text("room-code", t("code"), room.code, (code) => setRoom({ ...room, code }))}
            {text("room-name", t("name"), room.name, (name) => setRoom({ ...room, name }))}
            {text(
              "room-capacity",
              t("capacity"),
              room.capacity,
              (capacity) => setRoom({ ...room, capacity }),
              "number",
            )}
          </ActionDialog>
        </CardHeader>
        <CardContent>
          {rooms.data?.length ? (
            <ul className="grid gap-1 text-sm">
              {rooms.data.map((r) => (
                <li key={r.id}>
                  {r.code} · {r.name}
                  {r.capacity ? (
                    <span className="text-muted-foreground text-xs"> · {r.capacity}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
