#!/bin/sh
# Build-time helper: if the optional `build_ca` BuildKit secret is mounted, trust it for this
# command only (pip/uv/requests). Used for TLS-intercepting proxies; no-op otherwise.
set -eu
if [ -s /run/secrets/build_ca ]; then
  export SSL_CERT_FILE=/run/secrets/build_ca PIP_CERT=/run/secrets/build_ca \
         REQUESTS_CA_BUNDLE=/run/secrets/build_ca UV_SYSTEM_CERTS=0
fi
exec "$@"
