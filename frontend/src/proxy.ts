import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

/**
 * Next.js 16 proxy (formerly middleware): locale negotiation and redirects only.
 * It makes NO security decisions — authentication and authorization are enforced by the API.
 */
export default createMiddleware(routing);

export const config = {
  // Skip API routes, probes, Next internals and files with an extension.
  matcher: ["/((?!api|healthz|readyz|_next|_vercel|.*\\..*).*)"],
};
