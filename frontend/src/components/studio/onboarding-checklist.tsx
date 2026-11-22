"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canTenantWide, type TenantContext } from "@/lib/tenancy/context";
import { isEntitled } from "@/lib/tenancy/entitlements";

import { onboardingSteps } from "./onboarding";

/** Shown to whoever can configure the whole organisation, until every step is done. */
export function OnboardingChecklist({ context }: { context: TenantContext }) {
  const t = useTranslations("onboarding");
  const enabled =
    canTenantWide(context, "customization.config.edit") &&
    canTenantWide(context, "tenancy.member.view") &&
    isEntitled(context, "customization");
  const state = useQuery({
    queryKey: ["onboarding"],
    enabled,
    queryFn: async () => {
      const [institutions, members, config, fields] = await Promise.all([
        unwrap(api().GET("/api/v1/institutions/")),
        unwrap(api().GET("/api/v1/members/")),
        unwrap(api().GET("/api/v1/customization/config/")),
        unwrap(
          api().GET("/api/v1/customization/fields/", {
            params: { query: { entity: "tenancy.institution" } },
          }),
        ),
      ]);
      return onboardingSteps({
        institutions: institutions.length,
        members: members.length,
        settingsPublished: Boolean(config.published),
        customFields: fields.length,
      });
    },
  });
  if (!enabled || !state.data || state.data.every((s) => s.done)) return null;
  const done = state.data.filter((s) => s.done).length;
  return (
    <Card className="mb-4" data-testid="onboarding">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("progress", { done, total: state.data.length })}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2 text-sm">
          {state.data.map((step) => (
            <li key={step.key} className="flex items-center gap-2">
              {step.done ? (
                <CheckCircle2 aria-hidden="true" className="size-4 text-emerald-600" />
              ) : (
                <Circle aria-hidden="true" className="text-muted-foreground size-4" />
              )}
              <span className="sr-only">{step.done ? t("done") : t("todo")}</span>
              <Link href={step.href} className="underline-offset-2 hover:underline">
                {t(`steps.${step.key}` as "steps.institution")}
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
