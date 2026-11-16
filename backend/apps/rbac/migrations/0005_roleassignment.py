"""Role assignments and tenant system-role copies (Phase 3 M4; plan §4.1, §4.4, §9; ADR-044).

* ``rbac_roleassignment``: tenant-owned, standard RLS. Its references are composite
  ``(tenant_id, ...)`` keys (``MATCH SIMPLE``, ``ON DELETE RESTRICT``, not deferrable), the only
  database constraints between tenant tables: a membership, role, institution or campus of
  another tenant, a template role (``tenant_id`` NULL) and a campus of another institution
  can never be referenced, and a foreign id fails exactly like a random one.
* ``rbac_role.template_id``: a tenant's read-only system copy points at its template. A trigger
  guarantees the target is a ``template`` row (templates have no tenant, so a composite key
  can't express it).
"""

import apps.core.ids
import django.db.models.deletion
from django.db import migrations, models

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback


COMPOSITE_FKS = [
    ("rbac_assignment_membership_fk", "tenant_id, membership_id",
     "tenancy_membership (tenant_id, id)"),
    ("rbac_assignment_role_fk", "tenant_id, role_id", "rbac_role (tenant_id, id)"),
    ("rbac_assignment_institution_fk", "tenant_id, institution_id",
     "tenancy_institution (tenant_id, id)"),
    ("rbac_assignment_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
]  # fmt: skip
FK_FORWARD = [
    f"ALTER TABLE rbac_roleassignment ADD CONSTRAINT {name} FOREIGN KEY ({cols}) "
    f"REFERENCES {ref} MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE"
    for name, cols, ref in COMPOSITE_FKS
]
FK_REVERSE = [
    f"ALTER TABLE rbac_roleassignment DROP CONSTRAINT IF EXISTS {name}"
    for name, _, _ in COMPOSITE_FKS
]

TEMPLATE_GUARD_FORWARD = """
CREATE FUNCTION public.rbac_role_template_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.template_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM public.rbac_role AS t
    WHERE t.id = NEW.template_id AND t.kind = 'template' AND t.tenant_id IS NULL
  ) THEN
    RAISE EXCEPTION 'rbac_role.template_id must reference a template role'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER rbac_role_template_guard BEFORE INSERT OR UPDATE OF template_id ON rbac_role
  FOR EACH ROW EXECUTE FUNCTION public.rbac_role_template_guard();
"""
TEMPLATE_GUARD_REVERSE = """
DROP TRIGGER IF EXISTS rbac_role_template_guard ON rbac_role;
DROP FUNCTION IF EXISTS public.rbac_role_template_guard();
"""


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("role assignment keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0004_role_tenant_key"),
        ("tenancy", "0004_definer_functions"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleAssignment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.ids.new_id,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("updated_by", models.UUIDField(blank=True, editable=False, null=True)),
                (
                    "scope_type",
                    models.CharField(
                        choices=[
                            ("tenant", "Tenant"),
                            ("institution", "Institution"),
                            ("campus", "Campus"),
                        ],
                        max_length=16,
                    ),
                ),
                ("valid_from", models.DateTimeField()),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("granted_by", models.UUIDField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, default="", max_length=255)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_by", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "db_table": "rbac_roleassignment",
                "ordering": ("-created_at",),
                "abstract": False,
                "base_manager_name": "objects",
            },
        ),
        migrations.AddField(
            model_name="role",
            name="template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="copies",
                to="rbac.role",
            ),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("template__isnull", True),
                    models.Q(("is_system", True), ("kind", "tenant")),
                    _connector="OR",
                ),
                name="rbac_role_template_only_on_system_copy",
            ),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(
                condition=models.Q(("template__isnull", False)),
                fields=("tenant_id", "template"),
                name="rbac_role_one_copy_per_template",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="campus",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenancy.campus",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="institution",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenancy.institution",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="membership",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="role_assignments",
                to="tenancy.membership",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="role",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="assignments",
                to="rbac.role",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="tenant",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="tenancy.tenant",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("campus__isnull", True),
                        ("institution__isnull", True),
                        ("scope_type", "tenant"),
                    ),
                    models.Q(
                        ("campus__isnull", True),
                        ("institution__isnull", False),
                        ("scope_type", "institution"),
                    ),
                    models.Q(
                        ("campus__isnull", False),
                        ("institution__isnull", False),
                        ("scope_type", "campus"),
                    ),
                    _connector="OR",
                ),
                name="rbac_assignment_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("valid_until__isnull", True),
                    ("valid_until__gt", models.F("valid_from")),
                    _connector="OR",
                ),
                name="rbac_assignment_validity",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True)),
                fields=(
                    "tenant",
                    "membership",
                    "role",
                    "scope_type",
                    "institution",
                    "campus",
                ),
                name="rbac_assignment_one_live",
                nulls_distinct=False,
            ),
        ),
        migrations.RunSQL(FK_FORWARD, FK_REVERSE),
        migrations.RunSQL(TEMPLATE_GUARD_FORWARD, TEMPLATE_GUARD_REVERSE),
        EnableTenantRLS("rbac_roleassignment"),
        # Last, so that reversing starts here and is refused (plan §19.2).
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
