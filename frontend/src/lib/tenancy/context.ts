"use client";

import type { Schemas } from "@erp/api-client";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

export type TenantContext = Schemas["Context"];
export const CONTEXT_KEY = ["tenant", "context"] as const;

/** My membership, scopes and permissions in this organisation (tenant host only). */
export function useTenantContext(enabled = true) {
  return useQuery({
    queryKey: CONTEXT_KEY,
    queryFn: () => unwrap(api().GET("/api/v1/me/context/")),
    enabled,
  });
}

/** Whether a permission is held in ANY scope of the tenant. Navigation only: the API decides
 * every request in the exact scope of its object. */
export function canAnywhere(context: TenantContext | undefined, permission: string): boolean {
  return Boolean(context?.scopes.some((scope) => scope.permissions.includes(permission)));
}

/** Whether a permission is held at tenant scope (whole organisation). */
export function canTenantWide(context: TenantContext | undefined, permission: string): boolean {
  return Boolean(
    context?.scopes.some(
      (scope) => scope.scope_type === "tenant" && scope.permissions.includes(permission),
    ),
  );
}

/** Localised name from a `name_i18n` map, falling back to the default name. */
export function localName(item: { name: string; name_i18n?: unknown }, locale: string): string {
  const map = item.name_i18n as Record<string, string> | null | undefined;
  return map?.[locale] || item.name;
}
