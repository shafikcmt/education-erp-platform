"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import { useStepUp } from "@/components/auth/step-up";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/** A dialog with a small form whose submit runs an API call with step-up recovery and shows
 * the localised error. Field state lives in the caller. */
export function ActionDialog({
  trigger,
  title,
  description,
  submit,
  disabled,
  onSubmit,
  children,
}: {
  trigger: ReactNode;
  title: string;
  description?: string;
  submit: string;
  disabled?: boolean;
  onSubmit: () => Promise<unknown>;
  children: ReactNode;
}) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const { withStepUp } = useStepUp();
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setFailure(null);
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent closeLabel={t("common.close")}>
        <DialogTitle>{title}</DialogTitle>
        {description ? <DialogDescription>{description}</DialogDescription> : null}
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            setFailure(null);
            setBusy(true);
            withStepUp(onSubmit)
              .then(() => setOpen(false))
              .catch((error: unknown) => setFailure(errorMessage(error)))
              .finally(() => setBusy(false));
          }}
        >
          {failure ? <Alert variant="destructive">{failure}</Alert> : null}
          {children}
          <Button type="submit" disabled={disabled || busy}>
            {submit}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Runs one API action with step-up recovery and reports a localised failure. */
export function useAction(): {
  run: (action: () => Promise<unknown>) => Promise<boolean>;
  failure: string | null;
} {
  const errorMessage = useErrorMessage();
  const { withStepUp } = useStepUp();
  const [failure, setFailure] = useState<string | null>(null);
  const run = async (action: () => Promise<unknown>) => {
    setFailure(null);
    try {
      await withStepUp(action);
      return true;
    } catch (error) {
      setFailure(errorMessage(error));
      return false;
    }
  };
  return { run, failure };
}

export const SELECT_CLASS = "bg-background h-10 rounded-md border px-3 text-sm";
