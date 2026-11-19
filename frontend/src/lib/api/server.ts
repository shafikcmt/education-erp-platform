import type { paths, Schemas } from "@erp/api-client";
import { cookies, headers } from "next/headers";
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
  | { kind: "unavailable" };

/**
 * Which kind of host serves this request (Phase 3 plan §13): a tenant host answers
 * `/public/tenant/`, the platform host answers 404 there. Only used to choose screens and
 * navigation; the API decides every request on its own (host policy, ADR-041).
 */
export async function getServerHost(): Promise<ServerHost> {
  const forwarded = await forwardedHeaders();
  delete forwarded.cookie; // anonymous endpoint: no credentials needed
  try {
    const response = await fetch(`${baseUrl()}/api/v1/public/tenant/`, {
      headers: forwarded,
      cache: "no-store",
      redirect: "manual",
    });
    if (response.status === 404) return { kind: "platform" };
    if (!response.ok) return { kind: "unavailable" };
    return { kind: "tenant", tenant: (await response.json()) as Schemas["PublicTenant"] };
  } catch {
    return { kind: "unavailable" };
  }
}
