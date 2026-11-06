import type { paths } from "@erp/api-client";
import createClient, { type Client, type Middleware } from "openapi-fetch";

/**
 * Django's CSRF cookie (ADR-011). It is an anti-forgery token, not a credential.
 * Production uses the `__Host-` prefix (Secure, Path=/, no Domain; review L6); local HTTP
 * development uses the plain name because browsers reject `__Host-` cookies without HTTPS.
 */
export const CSRF_COOKIE_NAMES = ["__Host-csrftoken", "csrftoken"] as const;
export const CSRF_HEADER_NAME = "X-CSRFToken";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

export function readCsrfToken(cookieString: string): string | undefined {
  for (const name of CSRF_COOKIE_NAMES) {
    const value = readCookie(cookieString, name);
    if (value) return value;
  }
  return undefined;
}

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
      const token = readCsrfToken(getCookies());
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
