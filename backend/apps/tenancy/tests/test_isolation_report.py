"""Daily isolation denial report (Phase 3 M10; plan §14, P14)."""

from __future__ import annotations

import uuid

import pytest

from apps.audit.services import record
from apps.tenancy.tasks import report_isolation_denials

pytestmark = pytest.mark.django_db


def _blocked(tenant_id: uuid.UUID | None, reason: str) -> None:
    metadata = {"reason": reason, "host_kind": "tenant"}
    if tenant_id is not None:
        metadata["tenant_id"] = str(tenant_id)
    record("tenancy.isolation.blocked", outcome="denied", metadata=metadata)


def test_counts_blocked_events_per_tenant_and_reason(caplog):
    a, b = uuid.uuid4(), uuid.uuid4()
    _blocked(a, "TenantContextConflict")
    _blocked(a, "session_host_mismatch")
    _blocked(b, "session_host_mismatch")
    _blocked(None, "session_host_mismatch")
    record("authz.denied", outcome="denied", metadata={"permission": "x.y.z", "reason": "r"})
    report = report_isolation_denials.apply().get()

    assert report["total"] == 4
    assert report["by_tenant"] == {str(a): 2, str(b): 1, "platform": 1}
    assert report["by_reason"] == {"TenantContextConflict": 1, "session_host_mismatch": 3}
    assert "tenancy.isolation.daily_report" in caplog.text
    # Only the window counts (the audit log is append-only, so events can't be back-dated).
    assert report_isolation_denials.apply(kwargs={"hours": 0}).get()["total"] == 0


def test_quiet_day_reports_zero():
    assert report_isolation_denials.apply().get()["total"] == 0
