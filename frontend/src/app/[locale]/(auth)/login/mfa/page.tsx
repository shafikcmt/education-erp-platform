import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";

import { MfaForm } from "./mfa-form";

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<{ next?: string }> };

export default async function MfaPage({ params, searchParams }: Props) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const t = await getTranslations("auth.mfa");
  return (
    <AuthCard title={t("title")} description={t("subtitle")}>
      <MfaForm next={query.next} />
    </AuthCard>
  );
}
