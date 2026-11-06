import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";

import { VerifyFlow } from "./verify-flow";

export default async function VerifyEmailPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth.verifyEmail");
  return (
    <AuthCard title={t("title")}>
      <VerifyFlow />
    </AuthCard>
  );
}
