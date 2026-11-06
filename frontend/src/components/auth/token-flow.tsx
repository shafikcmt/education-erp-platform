"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { NewPasswordForm } from "@/components/auth/new-password-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { api, ensureCsrf } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useFragmentToken } from "@/lib/auth/fragment-token";

/** Activation and password reset: token from the URL fragment + a new password. */
export function TokenPasswordFlow({ kind }: { kind: "activate" | "reset" }) {
  const t = useTranslations();
  const { token, ready } = useFragmentToken();
  const [done, setDone] = useState(false);
  if (!ready) return null;
  if (!token) return <Alert variant="destructive">{t("errors.invalid_token")}</Alert>;
  if (done) {
    return (
      <div className="grid gap-4">
        <Alert variant="success">
          {t(kind === "activate" ? "auth.activate.done" : "auth.reset.done")}
        </Alert>
        <Button asChild size="lg">
          <Link href="/login">{t("auth.login.submit")}</Link>
        </Button>
      </div>
    );
  }
  const path =
    kind === "activate" ? "/api/v1/auth/activate/" : "/api/v1/auth/password/reset/confirm/";
  return (
    <NewPasswordForm
      submitLabel={t(kind === "activate" ? "auth.activate.submit" : "auth.reset.submit")}
      onSubmit={async (password) => {
        await ensureCsrf();
        await unwrap(api().POST(path, { body: { token, password } }));
        setDone(true);
      }}
    />
  );
}
