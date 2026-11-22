"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ensureCsrf } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { safeNextPath } from "@/lib/auth/next-path";
import { useErrorMessage } from "@/lib/auth/use-error-message";

import { SignupLink } from "./signup-link";

export function LoginForm({ next, expired }: { next?: string; expired: boolean }) {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const errorMessage = useErrorMessage();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    email: z
      .string()
      .trim()
      .min(1, { error: t("validation.required") }),
    password: z.string().min(1, { error: t("validation.required") }),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });
  const destination = safeNextPath(next);

  const onSubmit = form.handleSubmit(async (values) => {
    setFailure(null);
    try {
      await ensureCsrf();
      const result = await unwrap(api().POST("/api/v1/auth/login/", { body: values }));
      queryClient.clear();
      if (result.status === "mfa_required") {
        router.push({ pathname: "/login/mfa", query: { next: destination } });
      } else if (result.status === "mfa_enrollment_required") {
        router.replace("/login/mfa-setup");
      } else {
        router.replace(destination);
      }
    } catch (error) {
      form.resetField("password");
      setFailure(errorMessage(error));
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {expired ? <Alert variant="warning">{t("auth.login.expired")}</Alert> : null}
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <Field id="email" label={t("auth.email")} error={form.formState.errors.email?.message}>
        {(aria) => (
          <Input
            type="email"
            autoComplete="username"
            inputMode="email"
            autoFocus
            {...aria}
            {...form.register("email")}
          />
        )}
      </Field>
      <Field
        id="password"
        label={t("auth.password")}
        error={form.formState.errors.password?.message}
      >
        {(aria) => (
          <Input
            type="password"
            autoComplete="current-password"
            {...aria}
            {...form.register("password")}
          />
        )}
      </Field>
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {t("auth.login.submit")}
      </Button>
      <Link
        href="/forgot-password"
        className="text-primary text-sm underline-offset-4 hover:underline"
      >
        {t("auth.login.forgot")}
      </Link>
      <SignupLink />
    </form>
  );
}
