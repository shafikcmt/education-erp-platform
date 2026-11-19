import { setRequestLocale } from "next-intl/server";

import { MyInstitutions } from "./my-institutions";

export default async function MyInstitutionsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  setRequestLocale((await params).locale);
  return <MyInstitutions />;
}
