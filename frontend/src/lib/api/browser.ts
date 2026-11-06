"use client";

import type { paths } from "@erp/api-client";
import type { Client } from "openapi-fetch";

import { createApiClient, readCsrfToken } from "./client";

let client: Client<paths> | undefined;

/** Same-origin browser client (session cookie + CSRF header; ADR-011). */
export function api(): Client<paths> {
  client ??= createApiClient();
  return client;
}

/** Make sure the CSRF cookie exists before the first unsafe request of an anonymous visitor. */
export async function ensureCsrf(): Promise<void> {
  if (typeof document !== "undefined" && readCsrfToken(document.cookie)) return;
  await api().GET("/api/v1/auth/csrf/");
}
