"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ReasonDialog } from "@/components/tenancy/reason-dialog";
import { SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { CONTEXT_KEY, canTenantWide, useTenantContext } from "@/lib/tenancy/context";

const PROFILE_KEY = ["tenant", "profile"];

type Draft = { name: string; default_locale: string; timezone: string; currency: string };

/** Organisation profile and the support-access approval setting (plan §13.1, D5: owners only,
 * with a reason and step-up; the API enforces both). */
export function SettingsPage() {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const { data: context } = useTenantContext();
  const { run, failure } = useAction();
  const profile = useQuery({
    queryKey: PROFILE_KEY,
    queryFn: () => unwrap(api().GET("/api/v1/tenant/")),
  });
  // Edits start from the stored profile; nothing is copied into state until the user types.
  const [edits, setEdits] = useState<Partial<Record<keyof Draft, string>>>({});
  const [saved, setSaved] = useState(false);
  const canEdit = canTenantWide(context, "tenancy.tenant.update");
  const row = profile.data;
  if (!row) return null;
  const draft: Draft = {
    name: edits.name ?? row.name,
    default_locale: edits.default_locale ?? row.default_locale,
    timezone: edits.timezone ?? row.timezone,
    currency: edits.currency ?? row.currency,
  };
  const setDraft = (next: Draft) => setEdits(next);
  const save = async () => {
    setSaved(false);
    const ok = await run(async () => {
      await unwrap(
        api().PATCH("/api/v1/tenant/", {
          body: {
            name: draft.name.trim(),
            default_locale: draft.default_locale,
            locales: draft.default_locale === "en" ? ["en", "bn"] : ["bn", "en"],
            timezone: draft.timezone.trim(),
            currency: draft.currency.trim().toUpperCase(),
          },
        }),
      );
      await queryClient.invalidateQueries({ queryKey: PROFILE_KEY });
    });
    if (ok) setEdits({});
    setSaved(ok);
  };
  return (
    <>
      <PageHeader
        title={t("tenancy.settings.title")}
        description={t("tenancy.settings.subtitle")}
      />
      {failure ? (
        <Alert variant="destructive" className="mb-4">
          {failure}
        </Alert>
      ) : null}
      {saved ? <Alert className="mb-4">{t("tenancy.settings.saved")}</Alert> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("tenancy.settings.profile")}</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3"
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void save();
              }}
            >
              <fieldset disabled={!canEdit} className="grid gap-3">
                <Field id="set-name" label={t("tenancy.orgName")}>
                  {(aria) => (
                    <Input
                      value={draft.name}
                      onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                      {...aria}
                    />
                  )}
                </Field>
                <Field id="set-locale" label={t("tenancy.defaultLanguage")}>
                  {(aria) => (
                    <select
                      className={SELECT_CLASS}
                      value={draft.default_locale}
                      onChange={(e) => setDraft({ ...draft, default_locale: e.target.value })}
                      {...aria}
                    >
                      <option value="en">English</option>
                      <option value="bn">বাংলা</option>
                    </select>
                  )}
                </Field>
                <Field id="set-tz" label={t("tenancy.timezone")}>
                  {(aria) => (
                    <Input
                      value={draft.timezone}
                      onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
                      {...aria}
                    />
                  )}
                </Field>
                <Field
                  id="set-currency"
                  label={t("tenancy.currency")}
                  hint={t("tenancy.currencyHint")}
                >
                  {(aria) => (
                    <Input
                      value={draft.currency}
                      maxLength={3}
                      onChange={(e) => setDraft({ ...draft, currency: e.target.value })}
                      {...aria}
                    />
                  )}
                </Field>
                {canEdit ? <Button type="submit">{t("common.save")}</Button> : null}
              </fieldset>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("tenancy.settings.supportApproval")}</CardTitle>
            <CardDescription>
              {row.support_access_requires_approval
                ? t("tenancy.settings.approvalOn")
                : t("tenancy.settings.approvalOff")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {canEdit ? (
              <ReasonDialog
                trigger={
                  row.support_access_requires_approval
                    ? t("tenancy.settings.turnOff")
                    : t("tenancy.settings.turnOn")
                }
                title={t("tenancy.settings.supportApproval")}
                description={t("tenancy.settings.ownerOnly")}
                confirm={t("common.save")}
                onConfirm={async (reason) => {
                  await unwrap(
                    api().POST("/api/v1/tenant/support-approval/", {
                      body: { requires_approval: !row.support_access_requires_approval, reason },
                    }),
                  );
                  await queryClient.invalidateQueries({ queryKey: PROFILE_KEY });
                  await queryClient.invalidateQueries({ queryKey: CONTEXT_KEY });
                }}
              />
            ) : null}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
