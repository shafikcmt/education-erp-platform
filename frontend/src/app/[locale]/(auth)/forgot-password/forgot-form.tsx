"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api, ensureCsrf } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { emailSchema } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/** Same confirmation for every input: never reveals whether an account exists (plan §6.1). */
export function ForgotForm() {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({ email: emailSchema(t) });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });
  const onSubmit = form.handleSubmit(async ({ email }) => {
    setFailure(null);
    try {
      await ensureCsrf();
      await unwrap(api().POST("/api/v1/auth/password/reset/", { body: { email } }));
      setSent(true);
    } catch (error) {
      setFailure(errorMessage(error));
    }
  });
  if (sent) {
    return (
      <div className="grid gap-4">
        <Alert variant="success">{t("auth.forgot.sent")}</Alert>
        <Link href="/login" className="text-primary text-sm underline-offset-4 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </div>
    );
  }
  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field id="email" label={t("auth.email")} error={form.formState.errors.email?.message}>
        {(aria) => (
          <Input
            type="email"
            autoComplete="email"
            inputMode="email"
            autoFocus
            {...aria}
            {...form.register("email")}
          />
        )}
      </Field>
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {t("auth.forgot.submit")}
      </Button>
      <Link href="/login" className="text-primary text-sm underline-offset-4 hover:underline">
        {t("auth.backToLogin")}
      </Link>
    </form>
  );
}
