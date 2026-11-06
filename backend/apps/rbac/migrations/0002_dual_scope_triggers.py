"""Dual-scope consistency for Phase 3 RLS (Phase 2 plan §4.6).

* ``rbac_rolepermission.tenant_id`` always equals its role's ``tenant_id`` (set by trigger), so
  the Phase 3 dual-scope RLS policy needs no backfill.
* A role's ``tenant_id`` can never change after creation (a role can't move between tenants
  or between platform and tenant scope).
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION rbac_rolepermission_tenant_sync() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  SELECT r.tenant_id INTO NEW.tenant_id FROM rbac_role r WHERE r.id = NEW.role_id;
  RETURN NEW;
END $$;
CREATE TRIGGER rbac_rolepermission_tenant_sync BEFORE INSERT OR UPDATE ON rbac_rolepermission
  FOR EACH ROW EXECUTE FUNCTION rbac_rolepermission_tenant_sync();

CREATE FUNCTION rbac_role_tenant_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'rbac_role.tenant_id is immutable' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER rbac_role_tenant_immutable BEFORE UPDATE ON rbac_role
  FOR EACH ROW EXECUTE FUNCTION rbac_role_tenant_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS rbac_role_tenant_immutable ON rbac_role;
DROP FUNCTION IF EXISTS rbac_role_tenant_immutable();
DROP TRIGGER IF EXISTS rbac_rolepermission_tenant_sync ON rbac_rolepermission;
DROP FUNCTION IF EXISTS rbac_rolepermission_tenant_sync();
"""


class Migration(migrations.Migration):
    dependencies = [("rbac", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
