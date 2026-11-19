"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useStepUp } from "@/components/auth/step-up";
import { PageHeader } from "@/components/app/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { emailSchema } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";
import { INSTITUTION_TYPES } from "@/lib/tenancy/constants";

const SELECT = "bg-background h-10 rounded-md border px-3 text-sm";

/** Provisioning wizard (plan §13.1): organisation → first institution → main campus → owner.
 * The server refuses it while tenant hosts are disabled in production (409). */
function ProvisionDialog({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const { withStepUp } = useStepUp();
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    slug: z
      .string()
      .trim()
      .regex(/^[a-z](?!.*--)[a-z0-9-]{1,30}[a-z0-9]$/, { error: t("tenancy.slugHint") }),
    name: z
      .string()
      .trim()
      .min(2, { error: t("validation.required") })
      .max(200),
    owner_email: emailSchema(t),
    default_locale: z.enum(["en", "bn"]),
    timezone: z.string().trim().min(1).max(64),
    currency: z
      .string()
      .trim()
      .regex(/^[A-Z]{3}$/, { error: t("tenancy.currencyHint") }),
    institution_type: z.enum(INSTITUTION_TYPES),
    institution_code: z
      .string()
      .trim()
      .regex(/^[a-z0-9_-]{1,32}$/, { error: t("tenancy.codeHint") }),
    institution_name: z
      .string()
      .trim()
      .min(2, { error: t("validation.required") })
      .max(200),
    campus_name: z
      .string()
      .trim()
      .min(2, { error: t("validation.required") })
      .max(200),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      slug: "",
      name: "",
      owner_email: "",
      default_locale: "en",
      timezone: "UTC",
      currency: "USD",
      institution_type: "school",
      institution_code: "main",
      institution_name: "",
      campus_name: "",
    },
  });
  const submit = form.handleSubmit(async (v) => {
    setFailure(null);
    try {
      await withStepUp(() =>
        unwrap(
          api().POST("/api/v1/platform/tenants/", {
            body: {
              slug: v.slug,
              name: v.name,
              owner_email: v.owner_email,
              default_locale: v.default_locale,
              locales: v.default_locale === "en" ? ["en", "bn"] : ["bn", "en"],
              timezone: v.timezone,
              currency: v.currency,
              country: "",
              institution: {
                institution_type: v.institution_type,
                code: v.institution_code,
                name: v.institution_name,
                campus_code: "main",
                campus_name: v.campus_name,
              },
            },
          }),
        ),
      );
      form.reset();
      setOpen(false);
      onCreated();
    } catch (error) {
      setFailure(errorMessage(error));
    }
  });
  const err = form.formState.errors;
  const text = (name: keyof Values, label: string, hint?: string) => (
    <Field id={`p-${name}`} label={label} hint={hint} error={err[name]?.message}>
      {(aria) => <Input autoComplete="off" {...aria} {...form.register(name)} />}
    </Field>
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>{t("tenancy.tenants.provision")}</Button>
      </DialogTrigger>
      <DialogContent closeLabel={t("common.close")}>
        <DialogTitle>{t("tenancy.tenants.provision")}</DialogTitle>
        <DialogDescription>{t("tenancy.tenants.provisionHint")}</DialogDescription>
        <form onSubmit={submit} className="grid max-h-[70dvh] gap-4 overflow-y-auto" noValidate>
          {failure ? <Alert variant="destructive">{failure}</Alert> : null}
          <fieldset className="grid gap-3">
            <legend className="mb-1 text-sm font-semibold">{t("tenancy.tenants.stepOrg")}</legend>
            {text("name", t("tenancy.orgName"))}
            {text("slug", t("tenancy.slug"), t("tenancy.slugHint"))}
            <Field id="p-locale" label={t("tenancy.defaultLanguage")}>
              {(aria) => (
                <select className={SELECT} {...aria} {...form.register("default_locale")}>
                  <option value="en">English</option>
                  <option value="bn">বাংলা</option>
                </select>
              )}
            </Field>
            {text("timezone", t("tenancy.timezone"))}
            {text("currency", t("tenancy.currency"), t("tenancy.currencyHint"))}
          </fieldset>
          <fieldset className="grid gap-3">
            <legend className="mb-1 text-sm font-semibold">
              {t("tenancy.tenants.stepInstitution")}
            </legend>
            <Field id="p-type" label={t("tenancy.institutionType")}>
              {(aria) => (
                <select className={SELECT} {...aria} {...form.register("institution_type")}>
                  {INSTITUTION_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {t(`tenancy.types.${type}`)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            {text("institution_name", t("tenancy.institutionName"))}
            {text("institution_code", t("tenancy.code"), t("tenancy.codeHint"))}
            {text("campus_name", t("tenancy.mainCampusName"))}
          </fieldset>
          <fieldset className="grid gap-3">
            <legend className="mb-1 text-sm font-semibold">{t("tenancy.tenants.stepOwner")}</legend>
            {text("owner_email", t("tenancy.ownerEmail"), t("tenancy.ownerEmailHint"))}
          </fieldset>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {t("tenancy.tenants.create")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TenantsPage() {
  const t = useTranslations();
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const tenants = useQuery({
    queryKey: ["platform", "tenants", q],
    queryFn: () => unwrap(api().GET("/api/v1/platform/tenants/", { params: { query: { q } } })),
  });
  return (
    <>
      <PageHeader
        title={t("tenancy.tenants.title")}
        description={t("tenancy.tenants.subtitle")}
        actions={
          can(me, "tenancy.tenant.create") ? (
            <ProvisionDialog
              onCreated={() =>
                void queryClient.invalidateQueries({ queryKey: ["platform", "tenants"] })
              }
            />
          ) : null
        }
      />
      <div className="mb-4 max-w-sm">
        <Field id="tenant-search" label={t("tenancy.tenants.search")}>
          {(aria) => (
            <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} {...aria} />
          )}
        </Field>
      </div>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.orgName")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.slug")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.statusLabel")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("tenancy.limits")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(tenants.data?.results ?? []).map((row) => (
              <tr key={row.id} className="border-t">
                <td className="p-3">
                  <Link href={`/platform/tenants/${row.id}`} className="font-medium underline">
                    {row.name}
                  </Link>
                </td>
                <td className="p-3 font-mono text-xs">{row.slug}</td>
                <td className="p-3">
                  {t(`tenancy.tenantStatus.${row.status}` as "tenancy.tenantStatus.active")}
                </td>
                <td className="p-3 text-xs">
                  {t("tenancy.limitsValue", {
                    institutions: row.limits.max_institutions ?? 0,
                    campuses: row.limits.max_campuses ?? 0,
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
