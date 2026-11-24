"use client";

import { useQuery } from "@tanstack/react-query";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";

import {
  DynamicForm,
  type FormSource,
  type RenderedSection,
} from "@/components/studio/dynamic-form";
import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Field } from "@/components/ui/field";
import { api, ensureCsrf } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { localName } from "@/lib/tenancy/context";

/**
 * Open admissions and the application form. The answer after sending is always the same
 * ("check your email"), whatever the address; the application stays a draft until the email
 * link is confirmed. A hidden field catches bots (honeypot).
 */
export function ApplyPage() {
  const t = useTranslations("apply");
  const locale = useLocale();
  const format = useFormatter();
  const cycles = useQuery({
    queryKey: ["public", "admissions", "cycles"],
    queryFn: () => unwrap(api().GET("/api/v1/public/admissions/cycles/")),
    retry: false,
  });
  const [cycleId, setCycleId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [sent, setSent] = useState(false);
  const [limited, setLimited] = useState(false);
  const honeypot = useRef<HTMLInputElement>(null);
  const cycle = cycles.data?.find((c) => c.id === cycleId) ?? cycles.data?.[0];
  const target = targetId || cycle?.targets[0]?.id || "";

  if (cycles.isError) return <Alert>{t("closed")}</Alert>;
  if (!cycles.data) return <p className="text-muted-foreground text-sm">{t("loading")}</p>;
  if (!cycle) return <Alert>{t("noneOpen")}</Alert>;
  if (sent) return <Alert variant="success">{t("sent")}</Alert>;

  const source: FormSource = {
    cacheKey: ["public", "admissions", "form", cycle.id],
    render: () =>
      unwrap(
        api().GET("/api/v1/public/admissions/cycles/{cycle_id}/form/", {
          params: { path: { cycle_id: cycle.id } },
        }),
      ) as Promise<{ sections: RenderedSection[] }>,
    visibility: async (values) => {
      await ensureCsrf();
      const result = (await unwrap(
        api().POST("/api/v1/public/admissions/cycles/{cycle_id}/visibility/", {
          params: { path: { cycle_id: cycle.id } },
          body: { target, values, website: "" },
        }),
      )) as { sections?: string[] };
      return result.sections ?? [];
    },
    submit: async (values) => {
      setLimited(false);
      await ensureCsrf();
      try {
        await unwrap(
          api().POST("/api/v1/public/admissions/cycles/{cycle_id}/apply/", {
            params: { path: { cycle_id: cycle.id } },
            body: { target, values, website: honeypot.current?.value ?? "" },
          }),
        );
      } catch (error) {
        if (isApiError(error) && error.status === 429) setLimited(true);
        throw error;
      }
      setSent(true);
    },
    submitLabel: t("send"),
    extra: (
      // Hidden from people (and assistive technology); bots fill it.
      <div aria-hidden="true" className="absolute -left-[10000px] h-px w-px overflow-hidden">
        <label htmlFor="website">Website</label>
        <input id="website" name="website" ref={honeypot} tabIndex={-1} autoComplete="off" />
      </div>
    ),
  };

  return (
    <div className="grid gap-4">
      {cycles.data.length > 1 ? (
        <Field id="apply-cycle" label={t("cycle")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={cycle.id}
              onChange={(e) => {
                setCycleId(e.target.value);
                setTargetId("");
              }}
              {...aria}
            >
              {cycles.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {localName(c, locale)}
                </option>
              ))}
            </select>
          )}
        </Field>
      ) : null}
      <p className="text-muted-foreground text-sm">
        {localName(cycle, locale)} ·{" "}
        {t("closes", { date: format.dateTime(new Date(cycle.closes_on), { dateStyle: "long" }) })}
        {cycle.fee_amount
          ? ` · ${t("fee", { amount: cycle.fee_amount, currency: cycle.fee_currency })}`
          : ""}
      </p>
      <Field id="apply-target" label={t("target")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={target}
            onChange={(e) => setTargetId(e.target.value)}
            {...aria}
          >
            {cycle.targets.map((g) => (
              <option key={g.id} value={g.id}>
                {g.unit_name}
              </option>
            ))}
          </select>
        )}
      </Field>
      {limited ? <Alert variant="destructive">{t("limited")}</Alert> : null}
      <DynamicForm key={cycle.id} formKey={cycle.id} source={source} />
      <p className="text-muted-foreground text-xs">{t("privacy")}</p>
    </div>
  );
}
