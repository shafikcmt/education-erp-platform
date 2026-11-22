import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";

import { SignupForm } from "./signup-form";

export default async function SignupPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("signup");
  return (
    <AuthCard title={t("title")} description={t("intro")}>
      <SignupForm />
    </AuthCard>
  );
}
