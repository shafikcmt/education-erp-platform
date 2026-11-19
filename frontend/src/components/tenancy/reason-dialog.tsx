"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useStepUp } from "@/components/auth/step-up";
import { useErrorMessage } from "@/lib/auth/use-error-message";

/** A confirmation dialog that asks for a reason (10-200 characters) and runs a privileged
 * action with step-up recovery (suspensions, limit overrides, the approval setting). */
export function ReasonDialog({
  trigger,
  title,
  description,
  confirm,
  extra,
  onConfirm,
  variant = "default",
}: {
  trigger: string;
  title: string;
  description: string;
  confirm: string;
  extra?: ReactNode;
  onConfirm: (reason: string) => Promise<unknown>;
  variant?: "default" | "destructive";
}) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const { withStepUp } = useStepUp();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = reason.trim().length >= 10 && reason.trim().length <= 200;
  const submit = async () => {
    setFailure(null);
    setBusy(true);
    try {
      await withStepUp(() => onConfirm(reason.trim()));
      setReason("");
      setOpen(false);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant === "destructive" ? "destructive" : "outline"}>{trigger}</Button>
      </DialogTrigger>
      <DialogContent closeLabel={t("common.close")}>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) void submit();
          }}
        >
          {failure ? <Alert variant="destructive">{failure}</Alert> : null}
          {extra}
          <Field
            id="reason"
            label={t("tenancy.reason")}
            hint={t("tenancy.reasonHint")}
            error={reason && !valid ? t("tenancy.reasonHint") : undefined}
          >
            {(aria) => (
              <Input value={reason} onChange={(e) => setReason(e.target.value)} {...aria} />
            )}
          </Field>
          <Button
            type="submit"
            variant={variant === "destructive" ? "destructive" : "default"}
            disabled={!valid || busy}
          >
            {confirm}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
