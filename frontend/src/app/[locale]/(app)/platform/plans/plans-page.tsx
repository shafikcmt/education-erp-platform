"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ActionDialog, SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { useErrorMessage } from "@/lib/auth/use-error-message";

const KEY = ["platform", "billing"] as const;

/** Plans, add-ons and prices (plan §7; ADR-054 Q4). Prices are owner data: this screen only
 * records what the owner enters, and a new price replaces the active one (never edited). */
export function PlansPage() {
  const t = useTranslations("billing");
  const { data: me } = useMe();
  const errorMessage = useErrorMessage();
  const plans = useQuery({
    queryKey: [...KEY, "plans"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/plans/")),
  });
  const addons = useQuery({
    queryKey: [...KEY, "addons"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/addons/")),
  });
  const prices = useQuery({
    queryKey: [...KEY, "prices"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/prices/", { params: { query: {} } })),
  });
  const modules = useQuery({
    queryKey: [...KEY, "modules"],
    queryFn: () => unwrap(api().GET("/api/v1/platform/modules/")),
    enabled: can(me, "module_registry.module.view"),
  });
  const failed = plans.error ?? addons.error ?? prices.error;
  if (failed) return <Alert variant="destructive">{errorMessage(failed)}</Alert>;
  const manage = can(me, "billing.plan.manage");
  const sellable = (modules.data ?? []).filter((m) => m.sellable).map((m) => m.code);
  return (
    <>
      <PageHeader
        title={t("platform.title")}
        description={t("platform.subtitle")}
        actions={manage ? <CreatePlan sellable={sellable} /> : null}
      />
      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>{t("plans")}</CardTitle>
          </CardHeader>
          <CardContent>
            {plans.data?.length ? (
              <ul className="divide-y" data-testid="plans">
                {plans.data.map((plan) => (
                  <li key={plan.code} className="grid gap-1 py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{plan.name}</span>
                      <code className="text-muted-foreground text-xs">{plan.code}</code>
                      {plan.archived ? (
                        <span className="text-muted-foreground text-xs">{t("archived")}</span>
                      ) : null}
                    </div>
                    <p className="text-muted-foreground text-xs">
                      {plan.modules.length ? plan.modules.join(", ") : t("noModules")}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {t("planLimits", {
                        institutions: plan.limits.max_institutions ?? "-",
                        campuses: plan.limits.max_campuses ?? "-",
                      })}
                      {plan.trial_days ? ` · ${t("trialDays", { days: plan.trial_days })}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">{t("platform.noPlans")}</p>
            )}
          </CardContent>
        </Card>
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2">
              <div>
                <CardTitle>{t("addons")}</CardTitle>
              </div>
              {manage ? <CreateAddOn sellable={sellable} /> : null}
            </CardHeader>
            <CardContent>
              {addons.data?.length ? (
                <ul className="grid gap-1 text-sm">
                  {addons.data.map((a) => (
                    <li key={a.code}>
                      {a.name} <code className="text-muted-foreground text-xs">{a.code}</code>
                      {a.module ? ` · ${a.module}` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">{t("platform.noAddons")}</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2">
              <div>
                <CardTitle>{t("prices")}</CardTitle>
                <CardDescription>{t("platform.pricesHint")}</CardDescription>
              </div>
              {can(me, "billing.price.manage") ? (
                <AddPrice
                  plans={(plans.data ?? []).map((p) => p.code)}
                  addons={(addons.data ?? []).map((a) => a.code)}
                />
              ) : null}
            </CardHeader>
            <CardContent>
              {prices.data?.length ? (
                <ul className="grid gap-2 text-sm" data-testid="prices">
                  {prices.data.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center justify-between gap-2">
                      <span>
                        <code className="text-xs">{p.plan ?? p.addon}</code>{" "}
                        <span className="tabular-nums">
                          {p.amount} {p.currency}
                        </span>{" "}
                        · {t(`intervals.${p.interval}` as "intervals.month")}
                        {p.active ? "" : ` · ${t("inactive")}`}
                      </span>
                      {p.active && can(me, "billing.price.manage") ? (
                        <DeactivatePrice id={p.id} />
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">{t("platform.noPrices")}</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

function useRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

function ModulePicker({
  sellable,
  value,
  onChange,
}: {
  sellable: string[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const t = useTranslations("billing");
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-sm font-medium">{t("modules")}</legend>
      <div className="grid max-h-48 grid-cols-2 gap-1 overflow-y-auto text-sm">
        {sellable.map((code) => (
          <label key={code} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={value.includes(code)}
              onChange={(e) =>
                onChange(e.target.checked ? [...value, code] : value.filter((c) => c !== code))
              }
            />
            <code className="text-xs">{code}</code>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function CreatePlan({ sellable }: { sellable: string[] }) {
  const t = useTranslations("billing");
  const refresh = useRefresh();
  const empty = { code: "", name: "", institutions: "", campuses: "", trialDays: "" };
  const [form, setForm] = useState(empty);
  const [chosen, setChosen] = useState<string[]>([]);
  const limits: Record<string, number> = {};
  if (Number(form.institutions) > 0) limits.max_institutions = Number(form.institutions);
  if (Number(form.campuses) > 0) limits.max_campuses = Number(form.campuses);
  return (
    <ActionDialog
      trigger={<Button>{t("platform.createPlan")}</Button>}
      title={t("platform.createPlan")}
      description={t("platform.createPlanHint")}
      submit={t("platform.createPlan")}
      disabled={!/^[a-z][a-z0-9_]{1,39}$/.test(form.code) || !form.name.trim()}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/platform/plans/", {
            body: {
              code: form.code,
              name: form.name.trim(),
              limits,
              modules: chosen,
              is_public: false,
              trial_days: Number(form.trialDays) > 0 ? Number(form.trialDays) : null,
            },
          }),
        );
        setForm(empty);
        setChosen([]);
        await refresh();
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field id="plan-code" label={t("code")} hint={t("codeHint")}>
          {(aria) => (
            <Input
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value.trim() })}
              {...aria}
            />
          )}
        </Field>
        <Field id="plan-name" label={t("name")}>
          {(aria) => (
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              {...aria}
            />
          )}
        </Field>
        <Field id="plan-institutions" label={t("limitNames.max_institutions")}>
          {(aria) => (
            <Input
              type="number"
              min={1}
              inputMode="numeric"
              value={form.institutions}
              onChange={(e) => setForm({ ...form, institutions: e.target.value })}
              {...aria}
            />
          )}
        </Field>
        <Field id="plan-campuses" label={t("limitNames.max_campuses")}>
          {(aria) => (
            <Input
              type="number"
              min={1}
              inputMode="numeric"
              value={form.campuses}
              onChange={(e) => setForm({ ...form, campuses: e.target.value })}
              {...aria}
            />
          )}
        </Field>
        <Field id="plan-trial" label={t("trialLength")} hint={t("trialLengthHint")}>
          {(aria) => (
            <Input
              type="number"
              min={1}
              max={365}
              inputMode="numeric"
              value={form.trialDays}
              onChange={(e) => setForm({ ...form, trialDays: e.target.value })}
              {...aria}
            />
          )}
        </Field>
      </div>
      <ModulePicker sellable={sellable} value={chosen} onChange={setChosen} />
    </ActionDialog>
  );
}

function CreateAddOn({ sellable }: { sellable: string[] }) {
  const t = useTranslations("billing");
  const refresh = useRefresh();
  const [form, setForm] = useState({ code: "", name: "", module: "" });
  return (
    <ActionDialog
      trigger={
        <Button variant="outline" size="sm">
          {t("platform.createAddon")}
        </Button>
      }
      title={t("platform.createAddon")}
      submit={t("platform.createAddon")}
      disabled={!/^[a-z][a-z0-9_]{1,39}$/.test(form.code) || !form.name.trim() || !form.module}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/platform/addons/", {
            body: { code: form.code, name: form.name.trim(), module: form.module },
          }),
        );
        setForm({ code: "", name: "", module: "" });
        await refresh();
      }}
    >
      <Field id="addon-code" label={t("code")} hint={t("codeHint")}>
        {(aria) => (
          <Input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value.trim() })}
            {...aria}
          />
        )}
      </Field>
      <Field id="addon-name" label={t("name")}>
        {(aria) => (
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            {...aria}
          />
        )}
      </Field>
      <Field id="addon-module" label={t("module")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={form.module}
            onChange={(e) => setForm({ ...form, module: e.target.value })}
            {...aria}
          >
            <option value="">{t("choose")}</option>
            {sellable.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        )}
      </Field>
    </ActionDialog>
  );
}

function AddPrice({ plans, addons }: { plans: string[]; addons: string[] }) {
  const t = useTranslations("billing");
  const refresh = useRefresh();
  const empty = { target: "", currency: "", interval: "month", amount: "" };
  const [form, setForm] = useState(empty);
  const [kind, code] = form.target.split(":");
  const valid =
    Boolean(code) && /^[A-Z]{3}$/.test(form.currency) && /^\d{1,16}(\.\d{1,2})?$/.test(form.amount);
  return (
    <ActionDialog
      trigger={
        <Button variant="outline" size="sm">
          {t("platform.addPrice")}
        </Button>
      }
      title={t("platform.addPrice")}
      description={t("platform.addPriceHint")}
      submit={t("platform.addPrice")}
      disabled={!valid}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/platform/prices/", {
            body: {
              plan: kind === "plan" ? code : null,
              addon: kind === "addon" ? code : null,
              currency: form.currency,
              interval: form.interval as "month",
              amount: form.amount,
            },
          }),
        );
        setForm(empty);
        await refresh();
      }}
    >
      <Field id="price-target" label={t("priceFor")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={form.target}
            onChange={(e) => setForm({ ...form, target: e.target.value })}
            {...aria}
          >
            <option value="">{t("choose")}</option>
            {plans.map((c) => (
              <option key={`plan:${c}`} value={`plan:${c}`}>
                {t("plan")}: {c}
              </option>
            ))}
            {addons.map((c) => (
              <option key={`addon:${c}`} value={`addon:${c}`}>
                {t("addon")}: {c}
              </option>
            ))}
          </select>
        )}
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field id="price-currency" label={t("currency")}>
          {(aria) => (
            <Input
              value={form.currency}
              maxLength={3}
              onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
              {...aria}
            />
          )}
        </Field>
        <Field id="price-amount" label={t("amount")}>
          {(aria) => (
            <Input
              inputMode="decimal"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value.trim() })}
              {...aria}
            />
          )}
        </Field>
        <Field id="price-interval" label={t("interval")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={form.interval}
              onChange={(e) => setForm({ ...form, interval: e.target.value })}
              {...aria}
            >
              {(["month", "year", "one_time"] as const).map((i) => (
                <option key={i} value={i}>
                  {t(`intervals.${i}`)}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>
    </ActionDialog>
  );
}

function DeactivatePrice({ id }: { id: string }) {
  const t = useTranslations("billing");
  const refresh = useRefresh();
  return (
    <ActionDialog
      trigger={
        <Button variant="ghost" size="sm">
          {t("platform.deactivate")}
        </Button>
      }
      title={t("platform.deactivate")}
      description={t("platform.deactivateHint")}
      submit={t("platform.deactivate")}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/platform/prices/{price_id}/deactivate/", {
            params: { path: { price_id: id } },
          }),
        );
        await refresh();
      }}
    >
      <span />
    </ActionDialog>
  );
}
