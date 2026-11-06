"use client";

import type { Schemas } from "@erp/api-client";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

export type Me = Schemas["Me"];
export const ME_KEY = ["me"] as const;

export function fetchMe(): Promise<Me> {
  return unwrap(api().GET("/api/v1/me/"));
}

export function useMe(initial?: Me) {
  return useQuery({ queryKey: ME_KEY, queryFn: fetchMe, initialData: initial });
}

export function can(me: Me | undefined, permission: string): boolean {
  return Boolean(me?.permissions.includes(permission));
}
