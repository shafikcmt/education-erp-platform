#!/usr/bin/env bash
# PostgreSQL bootstrap: database roles and extensions (ADR-009).
#
# Runs automatically on first start of the docker postgres container
# (/docker-entrypoint-initdb.d), and is reused by CI against a service container
# (set PGHOST/PGPORT/PGPASSWORD for a remote server).
#
# Roles:
#   erp_owner    — owns the application database/schema; runs migrations only.
#   erp_app      — runtime role: NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS,
#                  DML only (no DDL). Row-Level Security applies to it (Phase 3).
#   erp_platform — BYPASSRLS but NOLOGIN, with no members: reserved, and used by NO runtime or
#                  maintenance code path (ADR-043, amending ADR-009 §5). platform_scope() works
#                  through the platform operation catalogue instead. Enabling login or any
#                  break-glass use requires a new ADR and explicit owner approval (D6).
#
# Extensions are installed as superuser in the app database AND template1, so databases
# created later (e.g. the pytest test database) inherit them without superuser rights.
set -euo pipefail

: "${ERP_DB_NAME:?ERP_DB_NAME is required}"
: "${ERP_OWNER_PASSWORD:?ERP_OWNER_PASSWORD is required}"
: "${ERP_APP_PASSWORD:?ERP_APP_PASSWORD is required}"
SUPERUSER="${POSTGRES_USER:-postgres}"

psql_super() {
  psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$SUPERUSER" "$@"
}

echo "[bootstrap] creating roles"
psql_super --dbname postgres \
  -v owner_pw="$ERP_OWNER_PASSWORD" -v app_pw="$ERP_APP_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE erp_owner' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp_owner')\gexec
SELECT 'CREATE ROLE erp_app' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp_app')\gexec
SELECT 'CREATE ROLE erp_platform' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp_platform')\gexec

-- erp_owner may create databases so pytest can build its own test database.
ALTER ROLE erp_owner WITH LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION
  PASSWORD :'owner_pw';
ALTER ROLE erp_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION
  NOINHERIT PASSWORD :'app_pw';
ALTER ROLE erp_platform WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS NOREPLICATION;
-- Bound runaway queries from the runtime role.
ALTER ROLE erp_app SET statement_timeout = '30s';
ALTER ROLE erp_app SET idle_in_transaction_session_timeout = '60s';
SQL

echo "[bootstrap] creating database ${ERP_DB_NAME}"
psql_super --dbname postgres -v db="$ERP_DB_NAME" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER erp_owner', :'db')
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db')\gexec
SQL

configure_db() {
  local db="$1"
  echo "[bootstrap] configuring database ${db}"
  psql_super --dbname "$db" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS citext;

-- Schema: owned by erp_owner; nobody else may create objects in it.
ALTER SCHEMA public OWNER TO erp_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO erp_app;

-- erp_app gets DML (never DDL) on everything erp_owner creates.
ALTER DEFAULT PRIVILEGES FOR ROLE erp_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO erp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE erp_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO erp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO erp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO erp_app;
SQL
}

# template1 first, so test databases inherit extensions, schema ownership and grants.
configure_db template1
configure_db "$ERP_DB_NAME"

# Database-level least privilege (not inherited from templates, so applied to the app DB):
# only our roles may connect, and nobody may create TEMP tables by default.
echo "[bootstrap] restricting database-level privileges on ${ERP_DB_NAME}"
psql_super --dbname postgres -v db="$ERP_DB_NAME" <<'SQL'
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', :'db')\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO erp_owner, erp_app', :'db')\gexec
SQL
echo "[bootstrap] done"
