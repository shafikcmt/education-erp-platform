"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Copy, Download, KeyRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useStepUp } from "@/components/auth/step-up";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { otpSchema } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

type Setup = { device_id: string; qr_svg: string; expires_at: string };

/**
 * TOTP enrollment (plan §6.6, ADR-038):
 * 1. server-rendered QR (no otpauth URI, no secret in the response);
 * 2. optional manual key: fresh step-up, shown ONCE, kept only in component state
 *    (not in the query cache, storage or URL), cleared on unmount; lost key → restart setup;
 * 3. confirmation code → 10 recovery codes shown once, with copy/download + acknowledgement.
 */
export function MfaEnrollment({ onDone }: { onDone: () => void }) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const { requestStepUp } = useStepUp();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [manualKey, setManualKey] = useState<string | null>(null);
  const [keyShown, setKeyShown] = useState(false);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: () => unwrap(api().POST("/api/v1/me/mfa/totp/setup/")),
    onSuccess: (data) => {
      setSetup(data);
      setManualKey(null);
      setKeyShown(false);
      setFailure(null);
    },
    onError: (error) => setFailure(errorMessage(error)),
  });
  const { mutate: startSetup } = start;

  useEffect(() => {
    startSetup();
    // The key must never outlive this component.
    return () => setManualKey(null);
  }, [startSetup]);

  const revealKey = async () => {
    if (!setup) return;
    setFailure(null);
    const call = () =>
      unwrap(
        api().POST("/api/v1/me/mfa/totp/setup/{device_id}/manual-key/", {
          params: { path: { device_id: setup.device_id } },
        }),
      );
    try {
      let result;
      try {
        result = await call();
      } catch (error) {
        if (!isApiError(error, "step_up_required") || !(await requestStepUp())) throw error;
        result = await call();
      }
      setManualKey(result.manual_key);
      setKeyShown(true);
    } catch (error) {
      setKeyShown(isApiError(error, "manual_key_already_shown"));
      setFailure(errorMessage(error));
    }
  };

  const schema = z.object({ code: otpSchema(t) });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { code: "" },
  });
  const confirm = form.handleSubmit(async ({ code }) => {
    if (!setup) return;
    setFailure(null);
    try {
      const result = await unwrap(
        api().POST("/api/v1/me/mfa/totp/confirm/", { body: { device_id: setup.device_id, code } }),
      );
      setManualKey(null);
      setCodes(result.recovery_codes);
    } catch (error) {
      form.reset({ code: "" });
      setFailure(errorMessage(error));
    }
  });

  const copy = async (text: string, what: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(what);
  };

  if (codes) {
    const text = codes.join("\n");
    return (
      <div className="grid gap-4" data-testid="recovery-codes">
        <h2 className="text-lg font-semibold">{t("mfaSetup.recoveryTitle")}</h2>
        <Alert variant="warning">{t("mfaSetup.recoveryIntro")}</Alert>
        <ol className="bg-muted grid grid-cols-1 gap-1 rounded-md p-4 font-mono text-sm sm:grid-cols-2">
          {codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void copy(text, "codes")}>
            <Copy aria-hidden="true" /> {copied === "codes" ? t("common.copied") : t("common.copy")}
          </Button>
          <Button type="button" variant="outline" asChild>
            <a
              href={`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`}
              download="recovery-codes.txt"
            >
              <Download aria-hidden="true" /> {t("mfaSetup.download")}
            </a>
          </Button>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1 size-4"
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
          />
          {t("mfaSetup.ack")}
        </label>
        <Button type="button" size="lg" disabled={!acknowledged} onClick={onDone}>
          {t("mfaSetup.continue")}
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      {setup ? (
        <>
          <p className="text-sm">{t("mfaSetup.scan")}</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- server-rendered SVG data URI */}
          <img
            src={setup.qr_svg}
            alt={t("mfaSetup.qrAlt")}
            width={220}
            height={220}
            className="mx-auto rounded-md border bg-white p-2"
            data-testid="mfa-qr"
          />
          {manualKey ? (
            <div className="grid gap-2" data-testid="manual-key-panel">
              <Alert variant="warning">{t("mfaSetup.manualWarning")}</Alert>
              <code
                className="bg-muted rounded-md p-3 text-center font-mono text-base tracking-wider break-all"
                data-testid="manual-key"
              >
                {manualKey}
              </code>
              <Button
                type="button"
                variant="outline"
                onClick={() => void copy(manualKey.replaceAll(" ", ""), "key")}
              >
                <Copy aria-hidden="true" />{" "}
                {copied === "key" ? t("common.copied") : t("common.copy")}
              </Button>
              <p className="text-muted-foreground text-xs">{t("mfaSetup.clipboardWarning")}</p>
            </div>
          ) : keyShown ? (
            <div className="grid gap-2">
              <p className="text-muted-foreground text-sm">{t("mfaSetup.keyGone")}</p>
              <Button type="button" variant="outline" onClick={() => start.mutate()}>
                {t("mfaSetup.restart")}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="link"
              className="justify-self-start px-0"
              onClick={() => void revealKey()}
            >
              <KeyRound aria-hidden="true" /> {t("mfaSetup.cantScan")}
            </Button>
          )}
          <form onSubmit={confirm} className="grid gap-4" noValidate>
            <Field
              id="mfa-confirm-code"
              label={t("mfaSetup.codeLabel")}
              error={form.formState.errors.code?.message}
            >
              {(aria) => (
                <Input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  {...aria}
                  {...form.register("code")}
                />
              )}
            </Field>
            <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
              {t("mfaSetup.confirm")}
            </Button>
          </form>
          <p className="text-muted-foreground text-xs">{t("mfaSetup.expiresNote")}</p>
        </>
      ) : start.isPending ? (
        <p className="text-muted-foreground text-sm">{t("common.loading")}</p>
      ) : (
        <Button type="button" onClick={() => start.mutate()}>
          {t("mfaSetup.restart")}
        </Button>
      )}
    </div>
  );
}
