import { setRequestLocale } from "next-intl/server";

import { UserDetail } from "./user-detail";

type Props = { params: Promise<{ locale: string; id: string }> };

export default async function PlatformUserPage({ params }: Props) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <UserDetail id={id} />;
}
