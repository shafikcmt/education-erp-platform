"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api, ensureCsrf } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { useFragmentToken } from "@/lib/auth/fragment-token";

/** Confirms an application with the emailed token. A button, not an automatic call: mail
 * scanners that open links must not submit applications on someone's behalf. */
export function ApplyVerify() {
  const t = useTranslations();
  const { token, ready } = useFragmentToken();
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  if (!ready) return null;
  if (!token || state === "failed") {
    return <Alert variant="destructive">{t("errors.invalid_token")}</Alert>;
  }
  if (state === "done") return <Alert variant="success">{t("apply.verified")}</Alert>;
  const confirm = async () => {
    try {
      await ensureCsrf();
      await unwrap(api().POST("/api/v1/public/admissions/verify/", { body: { token } }));
      setState("done");
    } catch {
      setState("failed");
    }
  };
  return (
    <div className="grid gap-4">
      <p className="text-sm">{t("apply.verifyIntro")}</p>
      <Button size="lg" onClick={() => void confirm()}>
        {t("apply.confirm")}
      </Button>
    </div>
  );
}
