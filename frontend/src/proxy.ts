import { NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";
import { buildCsp, createNonce, uploadOriginOf } from "./lib/security/csp";

const handleI18nRouting = createMiddleware(routing);

/**
 * Next.js 16 proxy (formerly middleware): locale negotiation plus a per-request CSP nonce
 * (security review M3). It makes NO authorization decisions — the API enforces those.
 *
 * The nonce and CSP are added to the forwarded REQUEST headers (next-intl copies the incoming
 * headers into the request it forwards), so Next.js can stamp the nonce on its scripts, and to
 * the response, so the browser enforces the policy.
 */
export default function proxy(request: NextRequest) {
  const nonce = createNonce();
  const csp = buildCsp(nonce, {
    dev: process.env.NODE_ENV === "development",
    uploadOrigin: uploadOriginOf(process.env.FILES_UPLOAD_ORIGIN),
  });
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("content-security-policy", csp);
  const response = handleI18nRouting(new NextRequest(request, { headers }));
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  // Skip API routes, probes, Next internals and files with an extension.
  matcher: ["/((?!api|healthz|readyz|_next|_vercel|.*\\..*).*)"],
};
