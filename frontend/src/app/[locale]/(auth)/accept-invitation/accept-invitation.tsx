"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api, ensureCsrf } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { useFragmentToken } from "@/lib/auth/fragment-token";
import { PASSWORD_MIN } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/**
 * Accept an invitation with the password of your account (plan §13.2, N80): a new account is
 * created for the invited address, or an existing account proves its password (a non-member
 * can't sign in on this host before joining). The token is read from the URL fragment only.
 */
export function AcceptInvitation() {
  const t = useTranslations();
  const locale = useLocale() === "bn" ? "bn" : "en";
  const errorMessage = useErrorMessage();
  const { token, ready } = useFragmentToken();
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [state, setState] = useState<"form" | "busy" | "done">("form");
  const [failure, setFailure] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  if (!ready) return null;
  if (!token) return <Alert variant="destructive">{t("errors.invitation_invalid")}</Alert>;
  if (state === "done") {
    return (
      <div className="grid gap-4">
        <Alert>{created ? t("tenancy.accept.createdDone") : t("tenancy.accept.joinedDone")}</Alert>
        <Button asChild>
          <Link href="/login">{t("tenancy.accept.goToSignIn")}</Link>
        </Button>
      </div>
    );
  }
  const submit = async () => {
    setFailure(null);
    setState("busy");
    try {
      await ensureCsrf();
      const result = await unwrap(
        api().POST("/api/v1/auth/invitations/accept/", {
          body: { token, password, display_name: displayName.trim(), locale },
        }),
      );
      setCreated(result.account_created);
      setState("done");
    } catch (error) {
      setFailure(
        isApiError(error, "validation_error")
          ? t("tenancy.accept.weakPassword")
          : errorMessage(error),
      );
      setState("form");
    }
  };
  return (
    <form
      className="grid gap-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (password.length >= 1) void submit();
      }}
    >
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <p className="text-muted-foreground text-sm">
        {t("tenancy.accept.passwordHint", { min: PASSWORD_MIN })}
      </p>
      <Field id="accept-name" label={t("account.displayName")}>
        {(aria) => (
          <Input
            autoComplete="name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            {...aria}
          />
        )}
      </Field>
      <Field id="accept-password" label={t("auth.password")}>
        {(aria) => (
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            {...aria}
          />
        )}
      </Field>
      <Button type="submit" disabled={!password || state === "busy"}>
        {t("tenancy.accept.submit")}
      </Button>
    </form>
  );
}
