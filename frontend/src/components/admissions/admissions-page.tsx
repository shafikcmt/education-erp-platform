"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { useInstitutionChoice } from "@/components/academics/institution-picker";
import { PageHeader } from "@/components/app/page-header";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { CyclesSection } from "./cycles-section";
import { InquiriesSection } from "./inquiries-section";
import { Tabs } from "./shared";
import { TestsSection } from "./tests-section";

const TABS = [
  { key: "cycles", permission: "admissions.cycle.view" },
  { key: "tests", permission: "admissions.test.manage" },
  { key: "inquiries", permission: "admissions.inquiry.view" },
] as const;
type Tab = (typeof TABS)[number]["key"];

/** Admissions back office (Phase 6 M7). Tabs follow the member's permissions; the API decides
 * everything (institution scope, step-up for publishing the merit list). */
export function AdmissionsPage() {
  const t = useTranslations("admissions");
  const { data: context } = useTenantContext();
  const { institution, picker } = useInstitutionChoice();
  const tabs = TABS.filter((tab) => canAnywhere(context, tab.permission)).map((tab) => tab.key);
  const [active, setActive] = useState<Tab | null>(null);
  const current = active ?? tabs[0] ?? null;
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 max-w-sm">{picker}</div>
      {current ? (
        <Tabs
          label={t("title")}
          tabs={tabs}
          current={current}
          onChange={setActive}
          name={(key) => t(`tabs.${key}`)}
        />
      ) : null}
      {institution && current === "cycles" ? (
        <CyclesSection key={institution} institution={institution} />
      ) : null}
      {institution && current === "tests" ? (
        <TestsSection key={`t-${institution}`} institution={institution} />
      ) : null}
      {institution && current === "inquiries" ? (
        <InquiriesSection key={institution} institution={institution} />
      ) : null}
    </>
  );
}
