import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";
import { getServerHost } from "@/lib/api/server";

import { ApplyPage } from "./apply-page";

/** Public admission form of an organisation (tenant hosts only; Phase 6 M7). */
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const host = await getServerHost();
  if (host.kind !== "tenant") notFound();
  const t = await getTranslations("apply");
  return (
    <AuthCard title={t("title")}>
      <ApplyPage />
    </AuthCard>
  );
}
