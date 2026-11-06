import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";
import { TokenPasswordFlow } from "@/components/auth/token-flow";

export default async function ActivatePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth.activate");
  return (
    <AuthCard title={t("title")} description={t("intro")}>
      <TokenPasswordFlow kind="activate" />
    </AuthCard>
  );
}
