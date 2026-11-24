"use client";

import { useQuery } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { ADMISSIONS_KEY, useAdmissionsRefresh } from "./shared";

const STATUSES = ["new", "contacted", "converted", "closed"] as const;

export function InquiriesSection({ institution }: { institution: string }) {
  const t = useTranslations("admissions");
  const format = useFormatter();
  const { data: context } = useTenantContext();
  const manage = canAnywhere(context, "admissions.inquiry.manage");
  const refresh = useAdmissionsRefresh();
  const { run, failure } = useAction();
  const inquiries = useQuery({
    queryKey: [...ADMISSIONS_KEY, "inquiries", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/admissions/inquiries/", { params: { query: { institution } } })),
  });
  const empty = { name: "", phone: "", email: "", interest: "", source: "walk_in" };
  const [form, setForm] = useState(empty);
  const setStatus = (id: string, status: (typeof STATUSES)[number]) =>
    run(async () => {
      await unwrap(
        api().PATCH("/api/v1/admissions/inquiries/{inquiry_id}/", {
          params: { path: { inquiry_id: id } },
          body: { status },
        }),
      );
      await refresh();
    });
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("tabs.inquiries")}</CardTitle>
        {manage ? (
          <ActionDialog
            trigger={<Button size="sm">{t("inquiries.add")}</Button>}
            title={t("inquiries.add")}
            description={t("inquiries.contactHint")}
            submit={t("save")}
            disabled={!form.name.trim() || !(form.phone.trim() || form.email.trim())}
            onSubmit={async () => {
              await unwrap(
                api().POST("/api/v1/admissions/inquiries/", { body: { institution, ...form } }),
              );
              setForm(empty);
              await refresh();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {(["name", "phone", "email", "interest"] as const).map((key) => (
                <Field key={key} id={`inquiry-${key}`} label={t(`inquiries.${key}`)}>
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
              <Field id="inquiry-source" label={t("inquiries.source")}>
                {(aria) => (
                  <select
                    className={SELECT_CLASS}
                    value={form.source}
                    onChange={(e) => setForm({ ...form, source: e.target.value })}
                    {...aria}
                  >
                    {(["walk_in", "phone", "web", "referral", "other"] as const).map((k) => (
                      <option key={k} value={k}>
                        {t(`inquiries.sources.${k}`)}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </div>
          </ActionDialog>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-2">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {inquiries.data?.length ? (
          <ul className="grid gap-2 text-sm" data-testid="inquiries">
            {inquiries.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {row.name}{" "}
                  <span className="text-muted-foreground text-xs">
                    {[row.phone, row.email, row.interest].filter(Boolean).join(" · ")} ·{" "}
                    {format.dateTime(new Date(row.created_at), { dateStyle: "medium" })}
                  </span>
                </span>
                {manage ? (
                  <select
                    className={SELECT_CLASS}
                    aria-label={t("inquiries.status")}
                    value={row.status}
                    onChange={(e) =>
                      void setStatus(row.id, e.target.value as (typeof STATUSES)[number])
                    }
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {t(`inquiries.statuses.${s}`)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="text-xs">{t(`inquiries.statuses.${row.status}`)}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
