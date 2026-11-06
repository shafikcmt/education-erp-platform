import { setRequestLocale } from "next-intl/server";

import { Dashboard } from "./dashboard";

export default async function DashboardPage({ params }: { params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale);
  return <Dashboard />;
}
