"""``TenantScopedModel`` / ``TenantManager`` (Phase 3 M1): fail closed, no create or move into
another tenant, enforced again by RLS."""

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.core.ids import new_id
from apps.core.tenancy import (
    TenantContext,
    TenantContextMissing,
    TenantMismatch,
    tenant_atomic,
)
from apps.core.tenancy.models import TenantManager
from tests.isolation_app.models import ProbeRecord

pytestmark = pytest.mark.django_db


@pytest.fixture
def a() -> TenantContext:
    return TenantContext(new_id())


@pytest.fixture
def b() -> TenantContext:
    return TenantContext(new_id())


def test_queries_without_context_raise_instead_of_returning_everything():
    for action in (
        lambda: ProbeRecord.objects.count(),
        lambda: list(ProbeRecord.objects.all()),
        lambda: ProbeRecord.objects.filter(name="x").exists(),
        lambda: ProbeRecord.objects.create(name="x"),
        lambda: ProbeRecord(name="x").save(),
    ):
        with pytest.raises(TenantContextMissing):
            action()


def test_base_manager_is_fail_closed_too():
    assert isinstance(ProbeRecord._base_manager, TenantManager)
    assert isinstance(ProbeRecord._default_manager, TenantManager)


def test_rows_are_stamped_and_scoped(a, b):
    with tenant_atomic(a):
        row = ProbeRecord.objects.create(name="a1")
        assert row.tenant_id == a.id
    with tenant_atomic(b):
        ProbeRecord.objects.create(name="b1")
        assert list(ProbeRecord.objects.values_list("name", flat=True)) == ["b1"]
        assert not ProbeRecord.objects.filter(pk=row.pk).exists()
    with tenant_atomic(a):
        assert list(ProbeRecord.objects.values_list("name", flat=True)) == ["a1"]


def test_cannot_create_into_another_tenant(a, b):
    with tenant_atomic(a):
        with pytest.raises(TenantMismatch):
            ProbeRecord(name="x", tenant_id=b.id).save()
        with pytest.raises(TenantMismatch):
            ProbeRecord.objects.create(name="x", tenant_id=b.id)
        with pytest.raises(TenantMismatch):
            ProbeRecord.objects.bulk_create(
                [ProbeRecord(name="ok"), ProbeRecord(name="x", tenant_id=b.id)]
            )
        assert ProbeRecord.objects.count() == 0
        created = ProbeRecord.objects.bulk_create([ProbeRecord(name="ok")])
        assert created[0].tenant_id == a.id


def test_cannot_move_a_row_to_another_tenant(a, b):
    with tenant_atomic(a):
        row = ProbeRecord.objects.create(name="mine")
        row.tenant_id = b.id
        with pytest.raises(TenantMismatch):
            row.save()
        with pytest.raises(TenantMismatch):
            ProbeRecord.objects.filter(pk=row.pk).update(tenant_id=b.id)
        with pytest.raises(TenantMismatch):
            ProbeRecord.objects.bulk_update([row], ["tenant_id"])
        with pytest.raises(TenantMismatch):
            ProbeRecord(pk=row.pk, name="mine", tenant_id=a.id).save(update_fields=["tenant_id"])
    with tenant_atomic(b):
        # In B's context the "moved" object is just an insert attempt with A's primary key.
        with pytest.raises(IntegrityError), transaction.atomic():
            row.save()
    with tenant_atomic(a):
        assert ProbeRecord.objects.get(pk=row.pk).tenant_id == a.id


def test_rls_blocks_cross_tenant_writes_even_with_raw_sql(a, b):
    with tenant_atomic(a):
        row = ProbeRecord.objects.create(name="mine")
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE isolation_probe_record SET tenant_id = %s WHERE id = %s", [b.id, row.pk]
                )
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO isolation_probe_record "
                    "(id, created_at, updated_at, tenant_id, name)"
                    " VALUES (%s, now(), now(), %s, 'x')",
                    [new_id(), b.id],
                )
    with tenant_atomic(b), connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM isolation_probe_record")
        assert cursor.fetchone()[0] == 0
        cursor.execute("DELETE FROM isolation_probe_record WHERE id = %s", [row.pk])
        assert cursor.rowcount == 0  # invisible, so not deletable
        cursor.execute("UPDATE isolation_probe_record SET name = 'stolen' WHERE id = %s", [row.pk])
        assert cursor.rowcount == 0


def test_delete_and_refresh_stay_in_their_tenant(a, b):
    with tenant_atomic(a):
        row = ProbeRecord.objects.create(name="mine")
    with tenant_atomic(b):
        with pytest.raises(TenantMismatch):
            row.refresh_from_db()
        ProbeRecord.objects.filter(pk=row.pk).delete()
    with tenant_atomic(a):
        row.refresh_from_db()
        assert row.name == "mine"


def test_bulk_update_of_ordinary_fields_works_within_the_tenant(a):
    with tenant_atomic(a):
        rows = ProbeRecord.objects.bulk_create([ProbeRecord(name="x"), ProbeRecord(name="y")])
        for row in rows:
            row.name = row.name.upper()
        assert ProbeRecord.objects.bulk_update(rows, ["name"]) == 2
        assert set(ProbeRecord.objects.values_list("name", flat=True)) == {"X", "Y"}
        assert ProbeRecord.objects.filter(name="X").update(name="Z") == 1
