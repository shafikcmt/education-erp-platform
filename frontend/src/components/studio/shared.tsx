"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Field } from "@/components/ui/field";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

export const STUDIO_KEY = ["studio"] as const;

/** What the Studio can configure (declared keys, entities, namespaces, kinds, quotas). */
export function useCatalog() {
  return useQuery({
    queryKey: [...STUDIO_KEY, "catalog"],
    queryFn: () => unwrap(api().GET("/api/v1/customization/catalog/")),
  });
}

export function useStudioRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: STUDIO_KEY });
}

/** A JSON text area: keeps the text, reports parse errors, hands the parsed value back. */
export function JsonEditor({
  id,
  label,
  hint,
  value,
  onChange,
  rows = 8,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (text: string) => void;
  rows?: number;
}) {
  const t = useTranslations("studio");
  let error: string | undefined;
  try {
    if (value.trim()) JSON.parse(value);
  } catch {
    error = t("invalidJson");
  }
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      {(aria) => (
        <textarea
          className="bg-background min-h-24 w-full rounded-md border p-2 font-mono text-xs"
          rows={rows}
          spellCheck={false}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          {...aria}
        />
      )}
    </Field>
  );
}

export function parseJson(text: string): unknown {
  return text.trim() ? JSON.parse(text) : {};
}

export function useJson(initial: unknown) {
  return useState(() => JSON.stringify(initial, null, 2));
}

/** "used of limit" from a quota object. */
export function QuotaBadge({ quota }: { quota?: { used: number; limit: number } }) {
  const t = useTranslations("studio");
  if (!quota || !quota.limit) return null;
  const near = quota.used >= quota.limit * 0.8;
  return (
    <span
      className={
        near
          ? "text-xs font-medium text-amber-700 dark:text-amber-400"
          : "text-muted-foreground text-xs"
      }
      data-testid="quota"
    >
      {t("quota", { used: quota.used, limit: quota.limit })}
    </span>
  );
}

export type Artefact = {
  id: string;
  key: string;
  name: string;
  number: number;
  status: string;
  published_at: string | null;
  body: Record<string, unknown>;
};

/** The latest version per key, with the published number when there is one. */
export function latestByKey(items: Artefact[]): (Artefact & { publishedNumber?: number })[] {
  const out = new Map<string, Artefact & { publishedNumber?: number }>();
  for (const item of items) {
    const current = out.get(item.key);
    if (!current) out.set(item.key, { ...item });
    if (item.status === "published") out.get(item.key)!.publishedNumber = item.number;
  }
  return [...out.values()];
}
