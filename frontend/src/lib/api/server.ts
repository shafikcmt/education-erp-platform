import type { paths, Schemas } from "@erp/api-client";
import { cookies, headers } from "next/headers";
import { cache } from "react";
import type { Client } from "openapi-fetch";

import { createApiClient } from "./client";

const baseUrl = () => process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Server-side API client (React Server Components) on the internal network, unauthenticated. */
export function createServerApiClient(): Client<paths> {
  return createApiClient({ baseUrl: baseUrl(), getCookies: () => "" });
}

export type ServerMe =
  { state: "authenticated"; me: Schemas["Me"] } | { state: "anonymous" } | { state: "unavailable" };

/**
 * Who is signed in, for server-side redirects (plan §9 "App shell").
 * Forwards only the incoming Cookie and the proxy's host/proto headers; Next.js never reads,
 * stores or mints credentials itself. The API stays the authority on every request.
 */
async function forwardedHeaders(): Promise<Record<string, string>> {
  const [jar, incoming] = await Promise.all([cookies(), headers()]);
  const forwarded: Record<string, string> = { cookie: jar.toString(), accept: "application/json" };
  for (const name of ["host", "x-forwarded-host", "x-forwarded-proto", "accept-language"]) {
    const value = incoming.get(name);
    if (value) forwarded[name] = value;
  }
  return forwarded;
}

export async function getServerMe(): Promise<ServerMe> {
  const forwarded = await forwardedHeaders();
  try {
    const response = await fetch(`${baseUrl()}/api/v1/me/`, {
      headers: forwarded,
      cache: "no-store",
      redirect: "manual",
    });
    if (response.status === 401) return { state: "anonymous" };
    if (!response.ok) return { state: "unavailable" };
    return { state: "authenticated", me: (await response.json()) as Schemas["Me"] };
  } catch {
    return { state: "unavailable" };
  }
}

export type ServerHost =
  | { kind: "platform" }
  | { kind: "tenant"; tenant: Schemas["PublicTenant"] }
  | { kind: "unknown" }
  | { kind: "unavailable" };

/**
 * Which kind of host serves this request (Phase 3 plan §13): a tenant host answers
 * `/public/tenant/`; the platform host answers `/system/health/` (platform-only); any other
 * host gets the API's uniform 404 for both and is "unknown" (no screen at all). Only used to
 * choose screens; the API decides every request on its own (host policy, ADR-041).
 * Memoised per request (React `cache`), so layouts can all ask.
 */
export const getServerHost = cache(async (): Promise<ServerHost> => {
  const forwarded = await forwardedHeaders();
  delete forwarded.cookie; // anonymous endpoints: no credentials needed
  const get = (path: string) =>
    fetch(`${baseUrl()}${path}`, { headers: forwarded, cache: "no-store", redirect: "manual" });
  try {
    const tenant = await get("/api/v1/public/tenant/");
    if (tenant.ok) {
      return { kind: "tenant", tenant: (await tenant.json()) as Schemas["PublicTenant"] };
    }
    if (tenant.status !== 404) return { kind: "unavailable" };
    const platform = await get("/api/v1/system/health/");
    if (platform.status === 404) return { kind: "unknown" };
    return platform.ok ? { kind: "platform" } : { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
});
