import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";

import { SetupFlow } from "./setup-flow";

export default async function MfaSetupPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("mfaSetup");
  return (
    <AuthCard title={t("title")} description={t("intro")}>
      <SetupFlow />
    </AuthCard>
  );
}
