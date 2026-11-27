"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { PageHeader } from "@/components/app/page-header";
import { ActionDialog } from "@/components/tenancy/simple-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link, useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { STUDENTS_KEY, useStudentStatus, useStudentsRefresh } from "./shared";

const EMPTY = { name: "", number: "", date_of_birth: "", gender: "", phone: "", email: "" };

/** Students I may see (Phase 7 M9). The server decides who is listed: my scope, the students
 * I teach or advise, my children, myself. */
export function StudentsPage() {
  const t = useTranslations("students");
  const { data: context } = useTenantContext();
  const { institution, picker } = useInstitutionChoice();
  const status = useStudentStatus();
  const refresh = useStudentsRefresh();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [form, setForm] = useState(EMPTY);
  const manage = canAnywhere(context, "students.student.manage");
  const list = useQuery({
    queryKey: [...STUDENTS_KEY, "list", institution, query],
    enabled: Boolean(institution),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/students/", {
          params: { query: { institution, ...(query.trim() ? { q: query.trim() } : {}) } },
        }),
      ),
  });
  const actions = (
    <div className="flex flex-wrap gap-2">
      {canAnywhere(context, "students.student.import") ||
      canAnywhere(context, "staff.profile.manage") ? (
        <Button variant="outline" asChild>
          <Link href="/students/import">{t("import.title")}</Link>
        </Button>
      ) : null}
      {canAnywhere(context, "students.student.promote") ? (
        <Button variant="outline" asChild>
          <Link href="/students/promotion">{t("promotion.title")}</Link>
        </Button>
      ) : null}
      {manage && institution ? (
        <ActionDialog
          trigger={<Button>{t("add")}</Button>}
          title={t("add")}
          description={t("numberHint")}
          submit={t("save")}
          disabled={!form.name.trim()}
          onSubmit={async () => {
            const values = Object.fromEntries(
              Object.entries(form).filter(([k, v]) => k !== "number" && v.trim()),
            );
            const created = await unwrap(
              api().POST("/api/v1/students/", {
                body: { institution, values, number: form.number.trim() },
              }),
            );
            setForm(EMPTY);
            await refresh();
            router.push(`/students/${created.id}`);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {(Object.keys(EMPTY) as (keyof typeof EMPTY)[]).map((key) => (
              <Field key={key} id={`student-${key}`} label={t(`fields.${key}`)}>
                {(aria) => (
                  <Input
                    type={
                      key === "date_of_birth"
                        ? "date"
                        : key === "email"
                          ? "email"
                          : key === "phone"
                            ? "tel"
                            : "text"
                    }
                    value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            ))}
          </div>
        </ActionDialog>
      ) : null}
    </div>
  );
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} actions={actions} />
      <div className="mb-4 grid max-w-2xl gap-3 sm:grid-cols-2">
        {picker}
        <Field id="student-search" label={t("search")}>
          {(aria) => (
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              {...aria}
            />
          )}
        </Field>
      </div>
      <Card>
        <CardContent className="pt-6">
          {list.data?.length ? (
            <ul className="divide-y text-sm" data-testid="students">
              {list.data.map((row) => (
                <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <Link href={`/students/${row.id}`} className="font-medium hover:underline">
                    {row.name}
                  </Link>
                  <span className="text-muted-foreground text-xs">
                    {row.number} · {status(row.status)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
