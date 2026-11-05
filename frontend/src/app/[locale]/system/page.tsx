import { CheckCircle2, CircleAlert, CircleX } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";
import { createServerApiClient } from "@/lib/api/server";

// Always render at request time: this page reports live API health.
export const dynamic = "force-dynamic";

type HealthState = "ok" | "degraded" | "unreachable";

async function loadHealth() {
  try {
    const { data, error } = await createServerApiClient().GET("/api/v1/system/health/", {
      signal: AbortSignal.timeout(5000),
    });
    if (error || !data) return { state: "unreachable" as HealthState };
    return { state: data.status as HealthState, version: data.version, env: data.environment };
  } catch {
    return { state: "unreachable" as HealthState };
  }
}

const ICONS = {
  ok: <CheckCircle2 aria-hidden="true" className="text-success size-5" />,
  degraded: <CircleAlert aria-hidden="true" className="text-warning size-5" />,
  unreachable: <CircleX aria-hidden="true" className="text-destructive size-5" />,
} as const;

export default async function SystemPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale });
  const health = await loadHealth();

  return (
    <div className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-8 px-4 py-6 sm:px-6">
      <header className="flex items-center justify-between gap-4">
        <Link
          href="/"
          className="text-primary text-sm font-medium underline-offset-4 hover:underline"
        >
          {t("system.back")}
        </Link>
        <LocaleSwitcher pathname="/system" />
      </header>
      <main id="main" className="flex flex-col gap-6">
        <h1 className="text-3xl font-bold tracking-tight">{t("system.heading")}</h1>
        <Card>
          <CardHeader>
            <CardTitle>{t("system.api")}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
              <dt className="text-muted-foreground">{t("system.status")}</dt>
              <dd className="flex items-center gap-2 font-medium" data-testid="api-status">
                {ICONS[health.state]}
                <span data-state={health.state}>{t(`system.${health.state}`)}</span>
              </dd>
              {health.version ? (
                <>
                  <dt className="text-muted-foreground">{t("system.version")}</dt>
                  <dd className="font-mono">{health.version}</dd>
                  <dt className="text-muted-foreground">{t("system.environment")}</dt>
                  <dd className="font-mono">{health.env}</dd>
                </>
              ) : null}
            </dl>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
