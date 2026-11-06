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
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { safeNextPath } from "@/lib/auth/next-path";
import { otpSchema } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

export function MfaForm({ next }: { next?: string }) {
  const t = useTranslations();
  const router = useRouter();
  const errorMessage = useErrorMessage();
  const [recovery, setRecovery] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    value: recovery
      ? z
          .string()
          .trim()
          .regex(/^[A-Za-z2-7-\s]{16,24}$/, { error: t("validation.recoveryFormat") })
      : otpSchema(t),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { value: "" },
  });

  const onSubmit = form.handleSubmit(async ({ value }) => {
    setFailure(null);
    try {
      await unwrap(
        api().POST("/api/v1/auth/mfa/verify/", {
          body: recovery ? { recovery_code: value } : { code: value },
        }),
      );
      router.replace(safeNextPath(next));
    } catch (error) {
      if (isApiError(error, "mfa_challenge_expired")) {
        router.replace("/login?expired=1");
        return;
      }
      form.reset({ value: "" });
      setFailure(errorMessage(error));
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field
        id="mfa-value"
        label={recovery ? t("auth.mfa.recoveryCode") : t("auth.mfa.code")}
        error={form.formState.errors.value?.message}
      >
        {(aria) => (
          <Input
            key={recovery ? "recovery" : "code"}
            autoFocus
            autoComplete={recovery ? "off" : "one-time-code"}
            inputMode={recovery ? "text" : "numeric"}
            maxLength={recovery ? 24 : 6}
            {...aria}
            {...form.register("value")}
          />
        )}
      </Field>
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {t("auth.mfa.submit")}
      </Button>
      <Button
        type="button"
        variant="link"
        className="justify-self-start px-0"
        onClick={() => {
          setRecovery((r) => !r);
          form.reset({ value: "" });
          setFailure(null);
        }}
      >
        {recovery ? t("auth.mfa.useCode") : t("auth.mfa.useRecovery")}
      </Button>
    </form>
  );
}
