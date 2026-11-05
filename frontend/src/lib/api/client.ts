import type { paths } from "@erp/api-client";
import createClient, { type Client, type Middleware } from "openapi-fetch";

/** Django's CSRF cookie (ADR-011). It is an anti-forgery token, not a credential. */
export const CSRF_COOKIE_NAME = "csrftoken";
export const CSRF_HEADER_NAME = "X-CSRFToken";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

export function readCookie(cookieString: string, name: string): string | undefined {
  for (const part of cookieString.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (rawKey === name) return decodeURIComponent(rest.join("="));
  }
  return undefined;
}

/** Adds `X-CSRFToken` to unsafe requests when the CSRF cookie is available (browser only). */
export function csrfMiddleware(getCookies: () => string): Middleware {
  return {
    onRequest({ request }) {
      if (SAFE_METHODS.has(request.method.toUpperCase())) return request;
      const token = readCookie(getCookies(), CSRF_COOKIE_NAME);
      if (token) request.headers.set(CSRF_HEADER_NAME, token);
      return request;
    },
  };
}

export interface ApiClientOptions {
  /** Same-origin by default ("" → requests go to /api/... through Nginx). */
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  getCookies?: () => string;
}

/**
 * Typed API client generated from the OpenAPI contract (ADR-015).
 * Session cookies are HttpOnly and sent automatically (`credentials: "include"`);
 * this code never reads, stores or forwards auth tokens (ADR-011).
 */
export function createApiClient(options: ApiClientOptions = {}): Client<paths> {
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? "",
    credentials: "include",
    fetch: options.fetch,
  });
  const getCookies =
    options.getCookies ?? (() => (typeof document === "undefined" ? "" : document.cookie));
  client.use(csrfMiddleware(getCookies));
  return client;
}
