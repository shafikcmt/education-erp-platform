"""Usage metering (Phase 4 M7; plan §2): daily rows per tenant, idempotent, isolated."""

from __future__ import annotations

import pytest
from django.db import connection

from apps.billing.models import UsageRecord
from apps.billing.tasks import record_tenant_usage, record_usage
from apps.core.tenancy import tenant_atomic
from apps.tenancy.models import Campus, Institution

pytestmark = pytest.mark.django_db


def _rows(tenant) -> dict[str, int]:
    with tenant_atomic(tenant):
        return dict(UsageRecord.objects.values_list("metric", "value"))


def test_usage_is_metered_per_tenant_and_idempotent_per_day(tenant_factory):
    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    with tenant_atomic(a):
        school = Institution.objects.create(code="main", name="Main", institution_type="school")
        Campus.objects.create(institution=school, code="c1", name="One", is_main=True)
        Campus.objects.create(institution=school, code="c2", name="Two")
    assert record_usage.delay().get() >= 2
    assert _rows(a) == {"institutions": 1, "campuses": 2}
    assert _rows(b) == {"institutions": 0, "campuses": 0}
    with tenant_atomic(a):
        Campus.objects.filter(code="c2").update(archived_at=school.created_at)
    record_tenant_usage.apply(kwargs={"tenant_id": str(a.id)}).get()
    assert _rows(a) == {"institutions": 1, "campuses": 1}  # same day: updated, not added
    with tenant_atomic(a):
        assert UsageRecord.objects.count() == 2


def test_usage_rows_are_tenant_isolated(tenant_factory):
    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    record_tenant_usage.apply(kwargs={"tenant_id": str(a.id)}).get()
    with tenant_atomic(b):
        assert UsageRecord.objects.count() == 0
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            cursor.execute("SELECT count(*) FROM billing_usagerecord WHERE tenant_id = %s", [a.id])
            assert cursor.fetchone() == (0,)
