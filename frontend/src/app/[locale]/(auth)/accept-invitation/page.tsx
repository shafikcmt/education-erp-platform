import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AuthCard } from "@/components/auth/auth-card";
import { getServerHost } from "@/lib/api/server";

import { AcceptInvitation } from "./accept-invitation";

/** Invitation links point to the tenant's own host (plan §13.2); elsewhere there is nothing
 * to accept. */
export default async function AcceptInvitationPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const host = await getServerHost();
  if (host.kind !== "tenant") notFound();
  const t = await getTranslations("tenancy.accept");
  return (
    <AuthCard title={t("title", { name: host.tenant.name })} description={t("intro")}>
      <AcceptInvitation />
    </AuthCard>
  );
}
