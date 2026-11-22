import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";

import { SignupVerify } from "./signup-verify";

export default async function SignupVerifyPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("signup");
  return (
    <AuthCard title={t("verifyTitle")}>
      <SignupVerify />
    </AuthCard>
  );
}
