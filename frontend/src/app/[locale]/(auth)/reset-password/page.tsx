import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";
import { TokenPasswordFlow } from "@/components/auth/token-flow";

export default async function ResetPasswordPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth.reset");
  return (
    <AuthCard title={t("title")} description={t("intro")}>
      <TokenPasswordFlow kind="reset" />
    </AuthCard>
  );
}
