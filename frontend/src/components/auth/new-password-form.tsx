"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { isApiError } from "@/lib/api/errors";
import { newPasswordSchema, PASSWORD_MIN } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/** New-password form shared by activation and password reset. */
export function NewPasswordForm({
  submitLabel,
  onSubmit,
}: {
  submitLabel: string;
  onSubmit: (password: string) => Promise<void>;
}) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const schema = newPasswordSchema(t);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });
  const [failure, setFailure] = useState<string | null>(null);

  const submit = form.handleSubmit(async ({ password }) => {
    setFailure(null);
    try {
      await onSubmit(password);
    } catch (error) {
      form.reset({ password: "", confirm: "" });
      const server = isApiError(error) ? error.fieldErrors.password?.[0] : undefined;
      setFailure(server ?? errorMessage(error));
    }
  });

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field
        id="new-password"
        label={t("auth.newPassword")}
        hint={t("validation.passwordMin", { min: PASSWORD_MIN })}
        error={form.formState.errors.password?.message}
      >
        {(aria) => (
          <Input
            type="password"
            autoComplete="new-password"
            autoFocus
            {...aria}
            {...form.register("password")}
          />
        )}
      </Field>
      <Field
        id="confirm-password"
        label={t("auth.confirmPassword")}
        error={form.formState.errors.confirm?.message}
      >
        {(aria) => (
          <Input
            type="password"
            autoComplete="new-password"
            {...aria}
            {...form.register("confirm")}
          />
        )}
      </Field>
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {submitLabel}
      </Button>
    </form>
  );
}
