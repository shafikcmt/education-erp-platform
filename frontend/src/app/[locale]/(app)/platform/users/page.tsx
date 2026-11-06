import { setRequestLocale } from "next-intl/server";

import { UsersPage } from "./users-page";

export default async function PlatformUsersPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  setRequestLocale((await params).locale);
  return <UsersPage />;
}
