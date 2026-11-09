"""Composite foreign keys, registry guard trigger and tombstone grant (Phase 3 M2; plan §4.4).

* Every reference between tenant tables is a ``(tenant_id, …)`` composite key (``MATCH
  SIMPLE``, ``ON DELETE RESTRICT``, not deferrable). PostgreSQL FK checks bypass RLS, so this is
  what makes a reference to another tenant's row impossible. The Django FKs between tenant
  tables carry no database constraint (``db_constraint=False``), so a foreign id fails the same
  way whether or not it exists elsewhere.
* ``tenancy_tenant`` (registry): a trigger keeps ``id`` and ``slug`` immutable and allows only
  the lifecycle transitions of plan §4.3 (``deleted`` is terminal). The runtime role loses
  DELETE, so a deleted tenant's slug stays tombstoned forever.
"""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants, refuse_isolation_rollback

COMPOSITE_FKS = [
    ("tenancy_campus", "tenancy_campus_institution_fk", "tenant_id, institution_id",
     "tenancy_institution (tenant_id, id)"),
    ("tenancy_invitation", "tenancy_invitation_role_fk", "tenant_id, role_id",
     "rbac_role (tenant_id, id)"),
    ("tenancy_invitation", "tenancy_invitation_institution_fk", "tenant_id, institution_id",
     "tenancy_institution (tenant_id, id)"),
    ("tenancy_invitation", "tenancy_invitation_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
]

FK_FORWARD = [
    f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({cols}) REFERENCES {ref} "
    "MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE"
    for table, name, cols, ref in COMPOSITE_FKS
]
FK_REVERSE = [f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {n}" for t, n, _, _ in COMPOSITE_FKS]

# Literal copy of apps.tenancy.rules.TRANSITIONS (a test asserts they agree).
GUARD_FORWARD = """
CREATE FUNCTION public.tenancy_tenant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id <> OLD.id THEN
    RAISE EXCEPTION 'tenant id is immutable' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.slug <> OLD.slug THEN
    RAISE EXCEPTION 'tenant slug is immutable' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status <> OLD.status AND NOT (
       (OLD.status = 'provisioning' AND NEW.status IN ('active', 'deleted'))
    OR (OLD.status = 'active' AND NEW.status IN ('suspended', 'offboarding'))
    OR (OLD.status = 'suspended' AND NEW.status IN ('active', 'offboarding'))
    OR (OLD.status = 'offboarding' AND NEW.status IN ('active', 'deleted'))
  ) THEN
    RAISE EXCEPTION 'invalid tenant status transition % -> %', OLD.status, NEW.status
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tenancy_tenant_guard BEFORE UPDATE ON tenancy_tenant
  FOR EACH ROW EXECUTE FUNCTION public.tenancy_tenant_guard();
"""
GUARD_REVERSE = """
DROP TRIGGER IF EXISTS tenancy_tenant_guard ON tenancy_tenant;
DROP FUNCTION IF EXISTS public.tenancy_tenant_guard();
"""


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("tenancy composite keys and registry guard")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_initial"),
        ("rbac", "0004_role_tenant_key"),
    ]

    operations = [
        migrations.RunSQL(FK_FORWARD, FK_REVERSE),
        migrations.RunSQL(GUARD_FORWARD, GUARD_REVERSE),
        RestrictTableGrants("tenancy_tenant", ("SELECT", "INSERT", "UPDATE")),
        # Last, so that reversing starts here and is refused (plan §19.2).
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
