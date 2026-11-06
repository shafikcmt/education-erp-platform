"use client";

import { useEffect } from "react";

import { MfaEnrollment } from "@/components/auth/mfa-enrollment";
import { StepUpProvider } from "@/components/auth/step-up";
import { useRouter } from "@/i18n/navigation";
import { isApiError } from "@/lib/api/errors";
import { useMe } from "@/lib/auth/me";

/** Forced enrollment for privileged accounts (plan §6.1 restricted session). */
export function SetupFlow() {
  const router = useRouter();
  const me = useMe();
  useEffect(() => {
    if (isApiError(me.error) && me.error.status === 401) router.replace("/login");
    if (me.data?.mfa_enabled) router.replace("/dashboard");
  }, [me.data, me.error, router]);
  if (!me.data || me.data.mfa_enabled) return null;
  return (
    <StepUpProvider mfaEnabled={false}>
      <MfaEnrollment onDone={() => router.replace("/dashboard")} />
    </StepUpProvider>
  );
}
