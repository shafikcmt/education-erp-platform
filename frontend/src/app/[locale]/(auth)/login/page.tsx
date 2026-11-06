import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";

import { LoginForm } from "./login-form";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string; expired?: string }>;
};

export default async function LoginPage({ params, searchParams }: Props) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const t = await getTranslations("auth.login");
  return (
    <AuthCard title={t("title")} description={t("subtitle")}>
      <LoginForm next={query.next} expired={query.expired === "1"} />
    </AuthCard>
  );
}
