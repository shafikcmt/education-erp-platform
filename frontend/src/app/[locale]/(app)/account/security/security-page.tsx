"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PageHeader } from "@/components/app/page-header";
import { MfaEnrollment } from "@/components/auth/mfa-enrollment";
import { useStepUp } from "@/components/auth/step-up";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { ME_KEY, useMe } from "@/lib/auth/me";
import { emailSchema, newPasswordSchema } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

function useFeedback() {
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const view = message ? (
    <Alert variant={message.ok ? "success" : "destructive"}>{message.text}</Alert>
  ) : null;
  return { view, set: setMessage };
}

function ProfileCard() {
  const t = useTranslations();
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const errorMessage = useErrorMessage();
  const feedback = useFeedback();
  const schema = z.object({ display_name: z.string().max(150), locale: z.enum(["en", "bn"]) });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    values: { display_name: me?.display_name ?? "", locale: (me?.locale as "en" | "bn") ?? "en" },
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      const updated = await unwrap(api().PATCH("/api/v1/me/", { body: values }));
      queryClient.setQueryData(ME_KEY, updated);
      feedback.set({ ok: true, text: t("account.saved") });
    } catch (error) {
      feedback.set({ ok: false, text: errorMessage(error) });
    }
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("account.profile")}</CardTitle>
        <CardDescription>{me?.email}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          {feedback.view}
          <Field id="display-name" label={t("account.displayName")}>
            {(aria) => <Input autoComplete="name" {...aria} {...form.register("display_name")} />}
          </Field>
          <Field id="email-language" label={t("account.emailLanguage")}>
            {(aria) => (
              <select
                className="bg-background h-10 rounded-md border px-3 text-sm"
                {...aria}
                {...form.register("locale")}
              >
                <option value="en">English</option>
                <option value="bn">বাংলা</option>
              </select>
            )}
          </Field>
          <Button
            type="submit"
            className="justify-self-start"
            disabled={form.formState.isSubmitting}
          >
            {t("common.save")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const t = useTranslations();
  const { withStepUp } = useStepUp();
  const errorMessage = useErrorMessage();
  const feedback = useFeedback();
  const schema = z
    .object({ current: z.string().min(1, { error: t("validation.required") }) })
    .and(newPasswordSchema(t));
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { current: "", password: "", confirm: "" },
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      await withStepUp(() =>
        unwrap(
          api().POST("/api/v1/me/password/", {
            body: { current_password: values.current, new_password: values.password },
          }),
        ),
      );
      form.reset();
      feedback.set({ ok: true, text: t("account.passwordChanged") });
    } catch (error) {
      const field = isApiError(error)
        ? (error.fieldErrors.current_password?.[0] ?? error.fieldErrors.new_password?.[0])
        : undefined;
      feedback.set({ ok: false, text: field ?? errorMessage(error) });
    }
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("account.password")}</CardTitle>
        <CardDescription>{t("account.passwordHint")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          {feedback.view}
          <Field
            id="current-password"
            label={t("account.currentPassword")}
            error={form.formState.errors.current?.message}
          >
            {(aria) => (
              <Input
                type="password"
                autoComplete="current-password"
                {...aria}
                {...form.register("current")}
              />
            )}
          </Field>
          <Field
            id="password-new"
            label={t("auth.newPassword")}
            error={form.formState.errors.password?.message}
          >
            {(aria) => (
              <Input
                type="password"
                autoComplete="new-password"
                {...aria}
                {...form.register("password")}
              />
            )}
          </Field>
          <Field
            id="password-confirm"
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
          <Button
            type="submit"
            className="justify-self-start"
            disabled={form.formState.isSubmitting}
          >
            {t("account.changePassword")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function EmailCard() {
  const t = useTranslations();
  const { withStepUp } = useStepUp();
  const errorMessage = useErrorMessage();
  const feedback = useFeedback();
  const schema = z.object({ email: emailSchema(t) });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });
  const submit = form.handleSubmit(async ({ email }) => {
    try {
      await withStepUp(() =>
        unwrap(api().POST("/api/v1/me/email/", { body: { new_email: email } })),
      );
      form.reset();
      feedback.set({ ok: true, text: t("account.emailSent") });
    } catch (error) {
      feedback.set({ ok: false, text: errorMessage(error) });
    }
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("account.email")}</CardTitle>
        <CardDescription>{t("account.emailHint")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          {feedback.view}
          <Field
            id="new-email"
            label={t("account.newEmail")}
            error={form.formState.errors.email?.message}
          >
            {(aria) => (
              <Input type="email" autoComplete="email" {...aria} {...form.register("email")} />
            )}
          </Field>
          <Button
            type="submit"
            className="justify-self-start"
            disabled={form.formState.isSubmitting}
          >
            {t("account.changeEmail")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function MfaCard() {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const { withStepUp } = useStepUp();
  const errorMessage = useErrorMessage();
  const feedback = useFeedback();
  const [enrolling, setEnrolling] = useState(false);
  const [codes, setCodes] = useState<string[] | null>(null);
  const status = useQuery({
    queryKey: ["me", "mfa"],
    queryFn: () => unwrap(api().GET("/api/v1/me/mfa/")),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ME_KEY });
  const disable = useMutation({
    mutationFn: () => withStepUp(() => unwrap(api().DELETE("/api/v1/me/mfa/totp/"))),
    onSuccess: () => {
      feedback.set({ ok: true, text: t("account.mfaDisabled") });
      void refresh();
    },
    onError: (error) => feedback.set({ ok: false, text: errorMessage(error) }),
  });
  const regenerate = useMutation({
    mutationFn: () => withStepUp(() => unwrap(api().POST("/api/v1/me/mfa/recovery-codes/"))),
    onSuccess: (data) => setCodes(data.recovery_codes),
    onError: (error) => feedback.set({ ok: false, text: errorMessage(error) }),
  });
  const data = status.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("account.mfa")}</CardTitle>
        <CardDescription>
          {data?.enabled
            ? t("account.mfaOn", { remaining: data.recovery_codes_remaining })
            : t("account.mfaOff")}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {feedback.view}
        {codes ? (
          <div className="grid gap-2" data-testid="regenerated-codes">
            <Alert variant="warning">{t("mfaSetup.recoveryIntro")}</Alert>
            <ol className="bg-muted grid gap-1 rounded-md p-4 font-mono text-sm sm:grid-cols-2">
              {codes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ol>
            <Button variant="outline" className="justify-self-start" onClick={() => setCodes(null)}>
              {t("common.done")}
            </Button>
          </div>
        ) : null}
        {enrolling ? (
          <MfaEnrollment
            onDone={() => {
              setEnrolling(false);
              void status.refetch();
              void refresh();
            }}
          />
        ) : data?.enabled ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => regenerate.mutate()}>
              {t("account.regenerate")}
            </Button>
            {data.is_required ? (
              <p className="text-muted-foreground text-sm">{t("account.mfaMandatory")}</p>
            ) : (
              <Button variant="destructive" onClick={() => disable.mutate()}>
                {t("account.disableMfa")}
              </Button>
            )}
          </div>
        ) : (
          <Button className="justify-self-start" onClick={() => setEnrolling(true)}>
            {t("account.enableMfa")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function SessionsCard() {
  const t = useTranslations();
  const router = useRouter();
  const errorMessage = useErrorMessage();
  const feedback = useFeedback();
  const sessions = useQuery({
    queryKey: ["me", "sessions"],
    queryFn: () => unwrap(api().GET("/api/v1/me/sessions/")),
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api().DELETE("/api/v1/me/sessions/{session_id}/", { params: { path: { session_id: id } } }),
      ),
    onSuccess: (_data, id) => {
      if (sessions.data?.find((s) => s.id === id)?.current) router.replace("/login");
      else void sessions.refetch();
    },
    onError: (error) => feedback.set({ ok: false, text: errorMessage(error) }),
  });
  const revokeOthers = useMutation({
    mutationFn: () => unwrap(api().POST("/api/v1/me/sessions/revoke-others/")),
    onSuccess: (data) => {
      feedback.set({ ok: true, text: t("account.revokedOthers", { count: data.revoked }) });
      void sessions.refetch();
    },
    onError: (error) => feedback.set({ ok: false, text: errorMessage(error) }),
  });
  const formatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("account.sessions")}</CardTitle>
        <CardDescription>{t("account.sessionsHint")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {feedback.view}
        <ul className="divide-y rounded-md border" data-testid="sessions">
          {(sessions.data ?? []).map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <div className="grid gap-0.5 text-sm">
                <span className="font-medium">
                  {s.user_agent_summary || t("account.unknownDevice")}
                  {s.current ? (
                    <span className="text-success ms-2 text-xs">({t("account.thisDevice")})</span>
                  ) : null}
                </span>
                <span className="text-muted-foreground text-xs">
                  {s.ip_masked} ·{" "}
                  {t("account.lastSeen", { time: formatter.format(new Date(s.last_seen_at)) })}
                </span>
              </div>
              <Button size="sm" variant="outline" onClick={() => revoke.mutate(s.id)}>
                {s.current ? t("nav.signOut") : t("account.revoke")}
              </Button>
            </li>
          ))}
        </ul>
        <Button
          variant="outline"
          className="justify-self-start"
          onClick={() => revokeOthers.mutate()}
        >
          {t("account.revokeOthers")}
        </Button>
      </CardContent>
    </Card>
  );
}

export function SecurityPage() {
  const t = useTranslations("account");
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="grid gap-6 lg:grid-cols-2">
        <ProfileCard />
        <MfaCard />
        <PasswordCard />
        <EmailCard />
        <div className="lg:col-span-2">
          <SessionsCard />
        </div>
      </div>
    </>
  );
}
