"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { createContext, type ReactNode, useCallback, useContext, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { isApiError, unwrap } from "@/lib/api/errors";
import { ME_KEY } from "@/lib/auth/me";
import { useErrorMessage } from "@/lib/auth/use-error-message";

type Run = <R>(action: () => Promise<R>) => Promise<R>;

const StepUpContext = createContext<{ withStepUp: Run; requestStepUp: () => Promise<boolean> }>({
  withStepUp: (action) => action(),
  requestStepUp: () => Promise.resolve(false),
});

/** `withStepUp(action)`: runs the action; on `403 step_up_required` asks for the password
 * (and MFA code) once, then retries (ADR-035). `requestStepUp()` asks up front (ADR-038). */
export function useStepUp() {
  return useContext(StepUpContext);
}

export function StepUpProvider({
  children,
  mfaEnabled,
}: {
  children: ReactNode;
  mfaEnabled: boolean;
}) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const resolver = useRef<((ok: boolean) => void) | null>(null);
  const schema = z.object({
    password: z.string().min(1, { error: t("validation.required") }),
    code: mfaEnabled
      ? z
          .string()
          .trim()
          .regex(/^\d{6}$/, { error: t("validation.codeFormat") })
      : z.string().optional(),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", code: "" },
  });
  const [failure, setFailure] = useState<string | null>(null);

  const requestStepUp = useCallback(() => {
    form.reset({ password: "", code: "" });
    setFailure(null);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, [form]);

  const withStepUp: Run = useCallback(
    async (action) => {
      try {
        return await action();
      } catch (error) {
        if (!isApiError(error, "step_up_required")) throw error;
        if (!(await requestStepUp())) throw error;
        return action();
      }
    },
    [requestStepUp],
  );

  const finish = (ok: boolean) => {
    setOpen(false);
    form.reset({ password: "", code: "" });
    resolver.current?.(ok);
    resolver.current = null;
  };

  const submitValues = async (values: z.infer<typeof schema>) => {
    setFailure(null);
    try {
      await unwrap(
        api().POST("/api/v1/auth/step-up/", {
          body: { password: values.password, ...(mfaEnabled ? { code: values.code } : {}) },
        }),
      );
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
      finish(true);
    } catch (error) {
      setFailure(errorMessage(error));
    }
  };

  return (
    <StepUpContext.Provider value={{ withStepUp, requestStepUp }}>
      {children}
      <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : finish(false))}>
        <DialogContent closeLabel={t("common.close")}>
          <DialogTitle>{t("stepUp.title")}</DialogTitle>
          <DialogDescription>{t("stepUp.description")}</DialogDescription>
          <form
            onSubmit={(event) => void form.handleSubmit(submitValues)(event)}
            className="grid gap-4"
            noValidate
          >
            {failure ? <Alert variant="destructive">{failure}</Alert> : null}
            <Field
              id="step-up-password"
              label={t("auth.password")}
              error={form.formState.errors.password?.message}
            >
              {(aria) => (
                <Input
                  type="password"
                  autoComplete="current-password"
                  autoFocus
                  {...aria}
                  {...form.register("password")}
                />
              )}
            </Field>
            {mfaEnabled ? (
              <Field
                id="step-up-code"
                label={t("auth.mfa.code")}
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
            ) : null}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => finish(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {t("stepUp.submit")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </StepUpContext.Provider>
  );
}
