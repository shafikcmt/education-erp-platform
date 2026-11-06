import { setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app/app-shell";
import { redirect } from "@/i18n/navigation";
import { getServerMe } from "@/lib/api/server";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

/**
 * Authenticated area. The server checks `/me/` first (plan §9 "App shell") so signed-out
 * visitors and privileged accounts that still must enroll MFA never see app chrome. This is a
 * UX gate only: every API call is authorized server-side.
 */
export default async function AppLayout({ children, params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const result = await getServerMe();
  if (result.state !== "authenticated") {
    return redirect({ href: "/login", locale });
  }
  if (result.me.mfa_enrollment_required) {
    return redirect({ href: "/login/mfa-setup", locale });
  }
  return <AppShell me={result.me}>{children}</AppShell>;
}
