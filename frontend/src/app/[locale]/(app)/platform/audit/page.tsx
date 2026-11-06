import { setRequestLocale } from "next-intl/server";

import { AuditPage } from "./audit-page";

export default async function PlatformAuditPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  setRequestLocale((await params).locale);
  return <AuditPage />;
}
