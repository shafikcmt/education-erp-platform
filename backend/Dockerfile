# syntax=docker/dockerfile:1.7
# Education ERP backend image (Django API, Celery worker/beat share this image).
# Targets:  dev  — dev dependencies, code bind-mounted by docker compose
#           runtime — production: no dev deps, code baked in, gunicorn + uvicorn workers
ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm

# ---------------------------------------------------------------- base
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:${PATH}"
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app

# ---------------------------------------------------------------- dependency builders
# Optional build secret `build_ca`: extra CA bundle for TLS-intercepting corporate proxies.
# Absent by default; never copied into an image layer.
FROM base AS builder
COPY infra-build-ca.sh /usr/local/bin/with-build-ca
RUN --mount=type=secret,id=build_ca,required=false \
    with-build-ca pip install "uv==0.11.32"
COPY pyproject.toml uv.lock .python-version ./

FROM builder AS deps-prod
RUN --mount=type=secret,id=build_ca,required=false \
    with-build-ca uv sync --frozen --no-dev --no-install-project

FROM builder AS deps-dev
RUN --mount=type=secret,id=build_ca,required=false \
    with-build-ca uv sync --frozen --no-install-project

# ---------------------------------------------------------------- dev
FROM base AS dev
COPY --from=deps-dev /opt/venv /opt/venv
COPY --chown=app:app . /app
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------------------------------------------------------------- runtime (production)
FROM base AS runtime
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
# The app runs from /opt/venv; the base image's system pip/setuptools are not needed at
# runtime and carry their own vendored CVEs — remove them to shrink the attack surface.
# Debian security fixes published after the pinned base image (CVE-2025-6020, linux-pam):
# upgrade only the affected packages, keeping the image otherwise reproducible (ADR-030).
# Fails closed: an unreachable mirror or a missing fix stops the build.
RUN python -m pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true \
 && rm -rf /usr/local/lib/python3.13/ensurepip \
 && apt-get update --error-on=any \
 && apt-get install -y --no-install-recommends --only-upgrade \
      libpam-modules libpam-modules-bin libpam-runtime libpam0g \
 && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libpam0g)" ge 1.5.2-6+deb12u3 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=deps-prod /opt/venv /opt/venv
COPY --chown=app:app . /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"]
CMD ["gunicorn", "config.asgi:application", "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "3", "--max-requests", "2000", \
     "--max-requests-jitter", "200", "--timeout", "60", "--access-logfile", "-"]
