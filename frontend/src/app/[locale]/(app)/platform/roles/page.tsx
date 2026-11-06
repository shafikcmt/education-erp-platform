import { setRequestLocale } from "next-intl/server";

import { RolesPage } from "./roles-page";

export default async function PlatformRolesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  setRequestLocale((await params).locale);
  return <RolesPage />;
}
