# syntax=docker/dockerfile:1.7
# Education ERP frontend image (Next.js standalone). Build context: repository root
# (pnpm workspace). Optional BuildKit secret `build_ca` = extra CA for TLS-intercepting proxies.
ARG NODE_IMAGE=node:24.22.2-alpine

# ---------------------------------------------------------------- base
FROM ${NODE_IMAGE} AS base
ENV NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    PNPM_HOME=/pnpm \
    PATH="/pnpm:${PATH}"
WORKDIR /repo

# ---------------------------------------------------------------- deps
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json frontend/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    corepack enable && corepack install \
 && pnpm install --frozen-lockfile --filter "@erp/frontend..."

# ---------------------------------------------------------------- build
FROM deps AS builder
COPY packages packages
COPY frontend frontend
RUN pnpm --filter @erp/frontend build

# ---------------------------------------------------------------- runtime (production)
FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
# The standalone server needs only `node`; drop bundled npm/corepack (unused, carry CVEs).
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
      /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /opt/yarn* /usr/local/bin/yarn*
COPY --from=builder --chown=node:node /repo/frontend/.next/standalone ./
COPY --from=builder --chown=node:node /repo/frontend/.next/static ./frontend/.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/en').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "frontend/server.js"]
