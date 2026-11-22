"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { Alert } from "@/components/ui/alert";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";
import { cn } from "@/lib/utils";

import { ArtefactSection } from "./artefact-section";
import { FieldsSection } from "./fields-section";
import { NumberingSection } from "./numbering-section";
import { SettingsSection } from "./settings-section";

const TABS = [
  { key: "settings", permission: "customization.config.view" },
  { key: "fields", permission: "customization.field.view" },
  { key: "forms", permission: "customization.form.view" },
  { key: "rules", permission: "customization.rule.view" },
  { key: "workflows", permission: "customization.workflow.view" },
  { key: "templates", permission: "customization.template.view" },
  { key: "numbering", permission: "customization.numbering.view" },
] as const;
type Tab = (typeof TABS)[number]["key"];

/** Customization Studio (Phase 5 M7). Tabs follow the member's permissions; the API decides. */
export function StudioPage() {
  const t = useTranslations("studio");
  const { data: context } = useTenantContext();
  const tabs = TABS.filter((tab) => canAnywhere(context, tab.permission));
  const [active, setActive] = useState<Tab | null>(null);
  const current = active ?? tabs[0]?.key ?? null;
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      {context && !tabs.length ? <Alert>{t("noAccess")}</Alert> : null}
      <div role="tablist" aria-label={t("title")} className="-mx-1 mb-4 flex gap-1 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            type="button"
            id={`studio-tab-${tab.key}`}
            aria-selected={current === tab.key}
            aria-controls="studio-panel"
            onClick={() => setActive(tab.key)}
            className={cn(
              "shrink-0 rounded-md px-3 py-2 text-sm font-medium",
              current === tab.key
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            {t(`sections.${tab.key}`)}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="studio-panel"
        aria-labelledby={current ? `studio-tab-${current}` : undefined}
      >
        {current === "settings" ? <SettingsSection /> : null}
        {current === "fields" ? <FieldsSection /> : null}
        {current === "numbering" ? <NumberingSection /> : null}
        {current === "rules" ||
        current === "forms" ||
        current === "workflows" ||
        current === "templates" ? (
          <ArtefactSection key={current} kind={current} />
        ) : null}
      </div>
    </>
  );
}
