import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const here = path.dirname(fileURLToPath(import.meta.url));
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  // Monorepo: trace workspace packages (packages/api-client) from the repository root.
  outputFileTracingRoot: path.join(here, ".."),
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@erp/api-client"],
  async rewrites() {
    // Browsers request /favicon.ico opportunistically; serve the generated app icon.
    return [{ source: "/favicon.ico", destination: "/icon.svg" }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default withNextIntl(nextConfig);
