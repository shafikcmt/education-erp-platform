"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api, ensureCsrf } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { useErrorMessage } from "@/lib/auth/use-error-message";
import { INSTITUTION_TYPES } from "@/lib/tenancy/constants";
import { suggestSlug } from "@/lib/tenancy/slug";

/** Self-service sign-up (Phase 5 M8). The same confirmation for every valid input; a platform
 * administrator approves each request before the organisation exists. */
export function SignupForm() {
  const t = useTranslations();
  const locale = useLocale();
  const errorMessage = useErrorMessage();
  const availability = useQuery({
    queryKey: ["signup", "availability"],
    queryFn: () => unwrap(api().GET("/api/v1/signup/")),
    retry: false,
  });
  const [form, setForm] = useState({
    email: "",
    organisation_name: "",
    slug: "",
    institution_type: "school" as (typeof INSTITUTION_TYPES)[number],
    institution_name: "",
    currency: "USD",
    website: "",
  });
  const [slugTouched, setSlugTouched] = useState(false);
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string[]>>({});

  if (availability.isPending) return null;
  if (!availability.data?.enabled) {
    return (
      <div className="grid gap-4">
        <Alert>{t("signup.closed")}</Alert>
        <Link href="/login" className="text-primary text-sm underline-offset-4 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </div>
    );
  }
  if (sent) return <Alert variant="success">{t("signup.sent")}</Alert>;

  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setFailure(null);
    setErrors({});
    try {
      await ensureCsrf();
      await unwrap(
        api().POST("/api/v1/signup/", {
          body: {
            ...form,
            default_locale: locale as "en" | "bn",
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          },
        }),
      );
      setSent(true);
    } catch (error) {
      if (isApiError(error) && Object.keys(error.fieldErrors).length) setErrors(error.fieldErrors);
      else setFailure(errorMessage(error));
    }
  };
  const error = (name: string) => errors[name]?.[0];
  return (
    <form onSubmit={(e) => void submit(e)} className="grid gap-4" noValidate>
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field id="signup-org" label={t("signup.organisation")} error={error("organisation_name")}>
        {(aria) => (
          <Input
            value={form.organisation_name}
            onChange={(e) =>
              set({
                organisation_name: e.target.value,
                ...(slugTouched ? {} : { slug: suggestSlug(e.target.value) }),
              })
            }
            autoFocus
            {...aria}
          />
        )}
      </Field>
      <Field
        id="signup-slug"
        label={t("signup.slug")}
        hint={t("signup.slugHint")}
        error={error("slug")}
      >
        {(aria) => (
          <Input
            value={form.slug}
            onChange={(e) => {
              setSlugTouched(true);
              set({ slug: e.target.value.trim().toLowerCase() });
            }}
            autoCapitalize="none"
            {...aria}
          />
        )}
      </Field>
      <Field id="signup-type" label={t("signup.institutionType")} error={error("institution_type")}>
        {(aria) => (
          <select
            className={SELECT_CLASS}
            value={form.institution_type}
            onChange={(e) =>
              set({ institution_type: e.target.value as (typeof INSTITUTION_TYPES)[number] })
            }
            {...aria}
          >
            {INSTITUTION_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`tenancy.types.${type}`)}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field id="signup-inst" label={t("signup.institutionName")} error={error("institution_name")}>
        {(aria) => (
          <Input
            value={form.institution_name}
            onChange={(e) => set({ institution_name: e.target.value })}
            {...aria}
          />
        )}
      </Field>
      <Field
        id="signup-currency"
        label={t("signup.currency")}
        hint={t("signup.currencyHint")}
        error={error("currency")}
      >
        {(aria) => (
          <Input
            value={form.currency}
            maxLength={3}
            onChange={(e) => set({ currency: e.target.value.toUpperCase() })}
            {...aria}
          />
        )}
      </Field>
      <Field
        id="signup-email"
        label={t("auth.email")}
        hint={t("signup.emailHint")}
        error={error("email")}
      >
        {(aria) => (
          <Input
            type="email"
            autoComplete="email"
            inputMode="email"
            value={form.email}
            onChange={(e) => set({ email: e.target.value })}
            {...aria}
          />
        )}
      </Field>
      {/* Honeypot: hidden from people and assistive technology; bots fill it. */}
      <div aria-hidden="true" className="absolute -left-[10000px] h-px w-px overflow-hidden">
        <label>
          Website
          <input
            tabIndex={-1}
            autoComplete="off"
            value={form.website}
            onChange={(e) => set({ website: e.target.value })}
          />
        </label>
      </div>
      <Button type="submit" size="lg">
        {t("signup.submit")}
      </Button>
      <p className="text-muted-foreground text-xs">{t("signup.approvalNote")}</p>
      <Link href="/login" className="text-primary text-sm underline-offset-4 hover:underline">
        {t("auth.backToLogin")}
      </Link>
    </form>
  );
}
