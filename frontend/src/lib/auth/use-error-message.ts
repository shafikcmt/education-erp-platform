"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";

import { isApiError } from "@/lib/api/errors";
import type en from "@/messages/en.json";

type ErrorKey = keyof (typeof en)["errors"];

const KNOWN = new Set<string>([
  "already_activated",
  "cannot_act_on_self",
  "invitation_email_mismatch",
  "invitation_invalid",
  "last_tenant_owner",
  "limit_exceeded",
  "membership_inactive",
  "not_a_member",
  "support_access_read_only",
  "support_session_expired",
  "tenant_hosts_disabled",
  "tenant_suspended",
  "tenant_unavailable",
  "cannot_deactivate_self",
  "invalid_credentials",
  "invalid_mfa_code",
  "insufficient_privilege",
  "cannot_reset_own_mfa",
  "invalid_token",
  "last_super_admin",
  "manual_key_already_shown",
  "mfa_already_enrolled",
  "mfa_challenge_expired",
  "mfa_enrollment_required",
  "mfa_required",
  "mfa_required_for_account",
  "network_error",
  "not_found",
  "permission_denied",
  "privilege_escalation",
  "mfa_locked",
  "rate_limited",
  "role_in_use",
  "step_up_required",
  "system_role_read_only",
  "validation_error",
]);

/** Localised message for an API error code. Never echoes server detail text verbatim. */
export function useErrorMessage(): (error: unknown) => string {
  const t = useTranslations("errors");
  return useCallback(
    (error: unknown) => {
      if (!isApiError(error)) return t("generic");
      if (error.code === "rate_limited" || error.code === "mfa_locked") {
        return t(error.code, { seconds: error.retryAfter ?? 60 });
      }
      return KNOWN.has(error.code) ? t(error.code as ErrorKey) : t("generic");
    },
    [t],
  );
}
