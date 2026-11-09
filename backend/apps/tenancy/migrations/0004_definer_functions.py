"""SECURITY DEFINER read functions F1-F3 and their owner-only policies (plan §7; ADR-043).

Threat model: plan §7. Common controls:
* owned by the migrating owner role (``erp_owner``, NOBYPASSRLS; FORCE RLS applies to it);
* rows are reachable only through the owner-only, SELECT-only policies below (they never apply
  to ``erp_app``) plus each function's own predicates;
* ``SET search_path = pg_catalog, public, pg_temp`` with schema-qualified references;
* ``LANGUAGE sql STABLE``, no dynamic SQL, no writes, no ``set_config``;
* ``EXECUTE`` revoked from PUBLIC and granted only to the runtime role;
* minimal columns; provisioning/deleted tenants are indistinguishable from unknown ones.
"""

from django.db import migrations

from apps.core.db_operations import app_role, refuse_isolation_rollback

_PATH = "SET search_path = pg_catalog, public, pg_temp"
_RESOLVABLE = "('active', 'suspended', 'offboarding')"

POLICIES = [
    ("tenancy_tenantdomain", "definer_resolve_host", "verified_at IS NOT NULL"),
    ("tenancy_membership", "definer_memberships_of", "status IN ('invited', 'active', 'suspended')"),
    ("tenancy_supportsession", "definer_support_sessions_of", "true"),
]

FUNCTIONS = {
    "tenancy_resolve_host(text)": f"""
CREATE FUNCTION public.tenancy_resolve_host(p_host text)
RETURNS TABLE (tenant_id uuid, status text)
LANGUAGE sql STABLE SECURITY DEFINER {_PATH} AS $$
  SELECT t.id, t.status::text
  FROM public.tenancy_tenantdomain AS d
  JOIN public.tenancy_tenant AS t ON t.id = d.tenant_id
  WHERE p_host IS NOT NULL
    AND pg_catalog.length(p_host) <= 253
    AND p_host OPERATOR(pg_catalog.~)
        '^[a-z0-9]([a-z0-9-]{{0,61}}[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]{{0,61}}[a-z0-9])?)+$'
    AND p_host OPERATOR(pg_catalog.!~) '^[0-9.]+$'
    AND d.domain = p_host
    AND d.verified_at IS NOT NULL
    AND t.status IN {_RESOLVABLE}
  LIMIT 1
$$;
""",
    "tenancy_memberships_of(uuid)": f"""
CREATE FUNCTION public.tenancy_memberships_of(p_user uuid)
RETURNS TABLE (tenant_id uuid, slug text, name text, tenant_status text, membership_status text)
LANGUAGE sql STABLE SECURITY DEFINER {_PATH} AS $$
  SELECT t.id, t.slug::text, t.name::text, t.status::text, m.status::text
  FROM public.tenancy_membership AS m
  JOIN public.tenancy_tenant AS t ON t.id = m.tenant_id
  WHERE p_user IS NOT NULL
    AND m.user_id = p_user
    AND m.status IN ('invited', 'active', 'suspended')
    AND t.status IN {_RESOLVABLE}
  ORDER BY t.name, t.id
$$;
""",
    "tenancy_support_sessions_of(uuid)": f"""
CREATE FUNCTION public.tenancy_support_sessions_of(p_staff uuid)
RETURNS TABLE (session_id uuid, tenant_id uuid, tenant_slug text, status text,
               starts_at timestamptz, ends_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER {_PATH} AS $$
  SELECT s.id, s.tenant_id, t.slug::text, s.status::text, s.starts_at, s.ends_at
  FROM public.tenancy_supportsession AS s
  JOIN public.tenancy_tenant AS t ON t.id = s.tenant_id
  WHERE p_staff IS NOT NULL AND s.staff_user_id = p_staff
  ORDER BY s.requested_at DESC, s.id
$$;
""",
}


def _forward(apps, schema_editor):  # type: ignore[no-untyped-def]
    role = schema_editor.quote_name(app_role())
    for table, name, using in POLICIES:
        schema_editor.execute(
            f"CREATE POLICY {name} ON {table} FOR SELECT TO CURRENT_USER USING ({using})"
        )
    for signature, sql in FUNCTIONS.items():
        schema_editor.execute(sql)
        schema_editor.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        schema_editor.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO {role}")


def _backward(apps, schema_editor):  # type: ignore[no-untyped-def]
    # Refused like the other tenancy migrations, so that a refused rollback changes nothing
    # (Django reverses newest first; without this the functions would already be gone).
    refuse_isolation_rollback("tenancy definer functions")
    for signature in FUNCTIONS:
        schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{signature}")
    for table, name, _ in POLICIES:
        schema_editor.execute(f"DROP POLICY IF EXISTS {name} ON {table}")


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0003_rls")]

    operations = [migrations.RunPython(_forward, _backward)]
