import type { paths } from "@erp/api-client";
import type { Client } from "openapi-fetch";

import { createApiClient } from "./client";

/**
 * Server-side API client (React Server Components). Talks to Django on the internal network.
 * Phase 2 adds forwarding of the incoming Cookie/Host headers for authenticated calls.
 */
export function createServerApiClient(): Client<paths> {
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  return createApiClient({ baseUrl, getCookies: () => "" });
}
