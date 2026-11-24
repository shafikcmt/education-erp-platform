"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const ADMISSIONS_KEY = ["admissions"] as const;

export function useAdmissionsRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ADMISSIONS_KEY });
}

/** A row of tabs (keyboard focusable buttons with ARIA tab roles). */
export function Tabs<K extends string>({
  label,
  tabs,
  current,
  onChange,
  name,
}: {
  label: string;
  tabs: readonly K[];
  current: K;
  onChange: (key: K) => void;
  name: (key: K) => ReactNode;
}) {
  return (
    <div role="tablist" aria-label={label} className="-mx-1 mb-4 flex gap-1 overflow-x-auto">
      {tabs.map((key) => (
        <button
          key={key}
          role="tab"
          type="button"
          aria-selected={current === key}
          onClick={() => onChange(key)}
          className={cn(
            "shrink-0 rounded-md px-3 py-2 text-sm font-medium",
            current === key
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-accent",
          )}
        >
          {name(key)}
        </button>
      ))}
    </div>
  );
}

/** The localised name of an application status. */
export function useStatusName() {
  const t = useTranslations("admissions.statuses");
  // Statuses are server values; an unknown one is shown as it is.
  return (status: string) => {
    const key = status as "submitted";
    return t.has(key) ? t(key) : status;
  };
}
