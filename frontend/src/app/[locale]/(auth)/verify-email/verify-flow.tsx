"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { api, ensureCsrf } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useFragmentToken } from "@/lib/auth/fragment-token";
import { useErrorMessage } from "@/lib/auth/use-error-message";

export function VerifyFlow() {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const { token, ready } = useFragmentToken();
  const verify = useMutation({
    mutationFn: async (value: string) => {
      await ensureCsrf();
      return unwrap(api().POST("/api/v1/auth/email/verify/", { body: { token: value } }));
    },
  });
  const { mutate } = verify;
  useEffect(() => {
    if (token) mutate(token);
  }, [token, mutate]);
  if (!ready) return null;
  if (!token) return <Alert variant="destructive">{t("errors.invalid_token")}</Alert>;
  if (verify.isError) return <Alert variant="destructive">{errorMessage(verify.error)}</Alert>;
  if (verify.isSuccess) {
    return (
      <div className="grid gap-4">
        <Alert variant="success">{t("auth.verifyEmail.done")}</Alert>
        <Button asChild>
          <Link href="/account/security">{t("nav.security")}</Link>
        </Button>
      </div>
    );
  }
  return <p className="text-muted-foreground text-sm">{t("auth.verifyEmail.verifying")}</p>;
}
