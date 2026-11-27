"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import type { Schemas } from "@erp/api-client";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import {
  PrintPreview,
  STUDENTS_KEY,
  useEnrollmentChoices,
  useStudentStatus,
  useStudentsRefresh,
} from "./shared";

const RELATIONS = ["mother", "father", "guardian", "grandparent", "sibling", "relative", "other"];

/** One student (Phase 7 M9): profile, enrollments, guardians, portal invitations, leaving and
 * printable documents. Each action shows only with its permission; the API re-checks it in the
 * student's institution, and a hidden student is a 404. */
export function StudentDetail({ id }: { id?: string }) {
  const t = useTranslations("students");
  const status = useStudentStatus();
  const { data: context } = useTenantContext();
  const can = (code: string) => canAnywhere(context, code);
  const detail = useQuery({
    queryKey: [...STUDENTS_KEY, "detail", id],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/students/{student_id}/", { params: { path: { student_id: id! } } }),
      ),
  });
  if (detail.isError) return <Alert variant="destructive">{t("notFound")}</Alert>;
  const student = detail.data;
  if (!student || !id) return null;
  const staff = student.relation === "staff";
  return (
    <>
      <PageHeader
        title={student.name}
        description={`${student.number} · ${status(student.status)} · ${t(`relations.${student.relation as "staff"}`)}`}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("profile")}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              {(["date_of_birth", "gender", "phone", "email"] as const).map((key) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground">{t(`fields.${key}`)}</dt>
                  <dd>{student[key] || "—"}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
        <EnrollmentsCard
          id={id}
          institution={student.institution}
          enrollments={student.enrollments}
          manage={staff && can("students.student.manage")}
        />
        <GuardiansCard
          id={id}
          guardians={student.guardians}
          manage={staff && can("students.guardian.manage")}
          invite={can("tenancy.member.invite")}
        />
        {staff ? (
          <ActionsCard
            id={id}
            active={student.status === "active"}
            hasEmail={Boolean(student.email)}
            can={can}
          />
        ) : null}
      </div>
    </>
  );
}

type Detail = Schemas["StudentDetail"];

function EnrollmentsCard({
  id,
  institution,
  enrollments,
  manage,
}: {
  id: string;
  institution: string;
  enrollments: Detail["enrollments"];
  manage: boolean;
}) {
  const t = useTranslations("students");
  const status = useStudentStatus();
  const refresh = useStudentsRefresh();
  const { years, leafUnits } = useEnrollmentChoices(manage ? institution : undefined);
  const [form, setForm] = useState({ year: "", unit: "", roll_number: "" });
  const active = enrollments.find((e) => e.status === "active");
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("enrollments")}</CardTitle>
        {manage ? (
          <div className="flex gap-2">
            <ActionDialog
              trigger={<Button size="sm">{active ? t("move") : t("enroll")}</Button>}
              title={active ? t("move") : t("enroll")}
              submit={t("save")}
              disabled={!form.unit || (!active && !form.year)}
              onSubmit={async () => {
                if (active) {
                  await unwrap(
                    api().POST("/api/v1/students/{student_id}/move/", {
                      params: { path: { student_id: id } },
                      body: { unit: form.unit, roll_number: form.roll_number },
                    }),
                  );
                } else {
                  await unwrap(
                    api().POST("/api/v1/students/{student_id}/enrollments/", {
                      params: { path: { student_id: id } },
                      body: { year: form.year, unit: form.unit, roll_number: form.roll_number },
                    }),
                  );
                }
                await refresh();
              }}
            >
              {active ? null : (
                <Field id="enroll-year" label={t("year")}>
                  {(aria) => (
                    <select
                      className={SELECT_CLASS}
                      value={form.year}
                      onChange={(e) => setForm({ ...form, year: e.target.value })}
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
              )}
              <Field id="enroll-unit" label={t("unit")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={form.unit}
                    onChange={(e) => setForm({ ...form, unit: e.target.value })}
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
              <Field id="enroll-roll" label={t("rollNumber")}>
                {(aria) => (
                  <Input
                    value={form.roll_number}
                    onChange={(e) => setForm({ ...form, roll_number: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            </ActionDialog>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {enrollments.length ? (
          <ul className="grid gap-1 text-sm" data-testid="enrollments">
            {enrollments.map((e) => (
              <li key={e.id} className="flex flex-wrap justify-between gap-2">
                <span>
                  {e.year_name} · {e.unit_name}
                  {e.roll_number ? ` · ${t("rollNumber")} ${e.roll_number}` : ""}
                </span>
                <span className="text-muted-foreground text-xs">{status(e.status)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("notEnrolled")}</p>
        )}
      </CardContent>
    </Card>
  );
}

function GuardiansCard({
  id,
  guardians,
  manage,
  invite,
}: {
  id: string;
  guardians: Detail["guardians"];
  manage: boolean;
  invite: boolean;
}) {
  const t = useTranslations("students");
  const refresh = useStudentsRefresh();
  const { run, failure } = useAction();
  const empty = { name: "", phone: "", email: "", relation: "mother", is_primary: false };
  const [form, setForm] = useState(empty);
  const [invited, setInvited] = useState<string[]>([]);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("guardians.title")}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t("guardians.add")}</Button>}
            title={t("guardians.add")}
            description={t("guardians.matchHint")}
            submit={t("save")}
            disabled={!(form.phone.trim() || form.email.trim())}
            onSubmit={async () => {
              const values = Object.fromEntries(
                (["name", "phone", "email"] as const)
                  .filter((k) => form[k].trim())
                  .map((k) => [k, form[k].trim()]),
              );
              await unwrap(
                api().POST("/api/v1/students/{student_id}/guardians/", {
                  params: { path: { student_id: id } },
                  body: {
                    values,
                    relation: form.relation,
                    is_primary: form.is_primary,
                    can_pickup: true,
                    receives_notices: true,
                  },
                }),
              );
              setForm(empty);
              await refresh();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {(["name", "phone", "email"] as const).map((key) => (
                <Field key={key} id={`guardian-${key}`} label={t(`fields.${key}`)}>
                  {(aria) => (
                    <Input
                      type={key === "email" ? "email" : key === "phone" ? "tel" : "text"}
                      value={form[key]}
                      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                      {...aria}
                    />
                  )}
                </Field>
              ))}
              <Field id="guardian-relation" label={t("guardians.relation")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={form.relation}
                    onChange={(e) => setForm({ ...form, relation: e.target.value })}
                    {...aria}
                  >
                    {RELATIONS.map((r) => (
                      <option key={r} value={r}>
                        {t(`guardians.relations.${r as "mother"}`)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_primary}
                onChange={(e) => setForm({ ...form, is_primary: e.target.checked })}
              />
              {t("guardians.primary")}
            </label>
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-2">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {guardians.length ? (
          <ul className="grid gap-2 text-sm" data-testid="guardians">
            {guardians.map((link) => (
              <li key={link.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {link.guardian.name}{" "}
                  <span className="text-muted-foreground text-xs">
                    {t(`guardians.relations.${link.relation as "mother"}`)}
                    {link.is_primary ? ` · ${t("guardians.primary")}` : ""} ·{" "}
                    {[link.guardian.phone, link.guardian.email].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <span className="flex gap-2">
                  {manage && invite && link.guardian.email && !link.guardian.has_login ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={invited.includes(link.guardian.id)}
                      onClick={() =>
                        void run(async () => {
                          await unwrap(
                            api().POST("/api/v1/guardians/{guardian_id}/invite/", {
                              params: { path: { guardian_id: link.guardian.id } },
                            }),
                          );
                          setInvited([...invited, link.guardian.id]);
                        })
                      }
                    >
                      {invited.includes(link.guardian.id) ? t("invited") : t("invite")}
                    </Button>
                  ) : null}
                  {manage ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        void run(async () => {
                          await unwrap(
                            api().DELETE("/api/v1/students/{student_id}/guardians/{link_id}/", {
                              params: { path: { student_id: id, link_id: link.id } },
                            }),
                          );
                          await refresh();
                        })
                      }
                    >
                      {t("guardians.unlink")}
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("guardians.none")}</p>
        )}
      </CardContent>
    </Card>
  );
}

function ActionsCard({
  id,
  active,
  hasEmail,
  can,
}: {
  id: string;
  active: boolean;
  hasEmail: boolean;
  can: (code: string) => boolean;
}) {
  const t = useTranslations("students");
  const refresh = useStudentsRefresh();
  const { run, failure } = useAction();
  const [leave, setLeave] = useState({ reason: "", destination: "", number: "" });
  const [template, setTemplate] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [invited, setInvited] = useState(false);
  const certificates = useQuery({
    queryKey: [...STUDENTS_KEY, "tcs", id],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/students/{student_id}/transfer-certificates/", {
          params: { path: { student_id: id } },
        }),
      ),
  });
  const transfer = can("students.student.transfer");
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("actions.title")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        <div className="flex flex-wrap gap-2">
          {transfer && active ? (
            <>
              <ActionDialog
                trigger={<Button variant="outline">{t("actions.withdraw")}</Button>}
                title={t("actions.withdraw")}
                submit={t("actions.confirm")}
                disabled={!leave.reason.trim()}
                onSubmit={async () => {
                  await unwrap(
                    api().POST("/api/v1/students/{student_id}/withdraw/", {
                      params: { path: { student_id: id } },
                      body: { reason: leave.reason },
                    }),
                  );
                  await refresh();
                }}
              >
                <ReasonField
                  value={leave.reason}
                  onChange={(reason) => setLeave({ ...leave, reason })}
                />
              </ActionDialog>
              <ActionDialog
                trigger={<Button variant="outline">{t("actions.transferCertificate")}</Button>}
                title={t("actions.transferCertificate")}
                description={t("actions.tcHint")}
                submit={t("actions.confirm")}
                disabled={!leave.reason.trim()}
                onSubmit={async () => {
                  await unwrap(
                    api().POST("/api/v1/students/{student_id}/transfer-certificates/", {
                      params: { path: { student_id: id } },
                      body: leave,
                    }),
                  );
                  await refresh();
                }}
              >
                <ReasonField
                  value={leave.reason}
                  onChange={(reason) => setLeave({ ...leave, reason })}
                />
                {(["destination", "number"] as const).map((key) => (
                  <Field key={key} id={`tc-${key}`} label={t(`actions.${key}`)}>
                    {(aria) => (
                      <Input
                        value={leave[key]}
                        onChange={(e) => setLeave({ ...leave, [key]: e.target.value })}
                        {...aria}
                      />
                    )}
                  </Field>
                ))}
              </ActionDialog>
            </>
          ) : null}
          {can("students.student.manage") && can("tenancy.member.invite") && hasEmail && active ? (
            <Button
              variant="outline"
              disabled={invited}
              onClick={() =>
                void run(async () => {
                  await unwrap(
                    api().POST("/api/v1/students/{student_id}/invite/", {
                      params: { path: { student_id: id } },
                    }),
                  );
                  setInvited(true);
                })
              }
            >
              {invited ? t("invited") : t("actions.invitePortal")}
            </Button>
          ) : null}
        </div>
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
          <Field id="doc-template" label={t("actions.template")}>
            {(aria) => (
              <Input value={template} onChange={(e) => setTemplate(e.target.value)} {...aria} />
            )}
          </Field>
          <Button
            variant="outline"
            disabled={!template.trim()}
            onClick={() =>
              void run(async () => {
                const doc = await unwrap(
                  api().GET("/api/v1/students/{student_id}/id-card/", {
                    params: { path: { student_id: id }, query: { template: template.trim() } },
                  }),
                );
                setPreview(doc.html);
              })
            }
          >
            {t("actions.idCard")}
          </Button>
          {certificates.data?.[0] ? (
            <Button
              variant="outline"
              disabled={!template.trim()}
              onClick={() =>
                void run(async () => {
                  const doc = await unwrap(
                    api().GET(
                      "/api/v1/students/{student_id}/transfer-certificates/{certificate_id}/document/",
                      {
                        params: {
                          path: { student_id: id, certificate_id: certificates.data[0]!.id },
                          query: { template: template.trim() },
                        },
                      },
                    ),
                  );
                  setPreview(doc.html);
                })
              }
            >
              {t("actions.printTc")}
            </Button>
          ) : null}
        </div>
        {certificates.data?.length ? (
          <ul className="text-muted-foreground text-xs" data-testid="certificates">
            {certificates.data.map((c) => (
              <li key={c.id}>
                {c.number} · {c.issued_on} · {c.destination || "—"}
              </li>
            ))}
          </ul>
        ) : null}
        {preview !== null ? <PrintPreview html={preview} title={t("actions.preview")} /> : null}
      </CardContent>
    </Card>
  );
}

function ReasonField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const t = useTranslations("students");
  return (
    <Field id="leave-reason" label={t("actions.reason")}>
      {(aria) => <Input value={value} onChange={(e) => onChange(e.target.value)} {...aria} />}
    </Field>
  );
}
