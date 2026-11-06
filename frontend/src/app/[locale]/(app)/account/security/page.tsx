import { setRequestLocale } from "next-intl/server";

import { SecurityPage } from "./security-page";

export default async function AccountSecurityPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  setRequestLocale((await params).locale);
  return <SecurityPage />;
}
