"""Audit log (plan §6.8/§6.9): allow-listed metadata, DB-enforced immutability for every role,
encrypted/deletable IP side table, retention anonymisation, erasure, dual-scope RLS prototype."""

import uuid
from datetime import timedelta

import psycopg
import pytest
from django.conf import settings
from django.db import connection, transaction
from django.db.utils import ProgrammingError
from django.test import RequestFactory
from django.utils import timezone
from freezegun import freeze_time

from apps.audit.models import AuditEvent, AuditEventIP
from apps.audit.services import (
    anonymize_expired_ips,
    erase_ips_for_actor,
    events_from_ip,
    record,
    reveal_ip,
)
from apps.core.ip_privacy import open_ip

pytestmark = pytest.mark.django_db


def _request(ip: str = "203.0.113.9"):
    return RequestFactory().get("/", REMOTE_ADDR=ip, HTTP_USER_AGENT="Firefox/140.0 (X11; Linux)")


def test_record_writes_event_and_encrypted_ip():
    event = record("identity.logout", request=_request(), actor_user_id=uuid.uuid4())
    assert event.actor_type == "user"
    side = AuditEventIP.objects.get(event=event)
    assert side.ip_prefix == "203.0.113.0/24"
    assert b"203.0.113.9" not in bytes(side.ip_encrypted or b"")
    assert open_ip(side.ip_encrypted) == "203.0.113.9"
    assert event.user_agent_summary == "Firefox on Linux"
    assert events_from_ip("203.0.113.9") == [event.pk]


@pytest.mark.parametrize(
    "metadata",
    [{"password": "x"}, {"unexpected": "x"}, {"reason": {"nested": 1}}, {"reason": object()}],
)
def test_metadata_must_be_allow_listed_scalars(metadata):
    with pytest.raises(ValueError, match="Metadata"):
        record("identity.login.failed", metadata=metadata)


def test_unknown_actions_are_rejected():
    with pytest.raises(ValueError, match="Unknown audit action"):
        record("identity.made_up")


def test_runtime_role_cannot_update_or_delete_events():
    event = record("identity.logout")
    for sql in (
        "UPDATE audit_auditevent SET action = 'x' WHERE id = %s",
        "DELETE FROM audit_auditevent WHERE id = %s",
    ):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql, [event.pk])


def test_trigger_blocks_mutation_even_for_the_owner(owner_dsn):
    with psycopg.connect(**owner_dsn) as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO audit_auditevent (id, occurred_at, actor_type, action, outcome, "
            "target_type, target_id, metadata, user_agent_summary, request_id) "
            "VALUES (%s, now(), 'system', 'identity.logout', 'success', '', '', '{}', '', '')",
            [uuid.uuid4()],
        )
        for sql in (
            "UPDATE audit_auditevent SET action = 'x'",
            "DELETE FROM audit_auditevent",
            "TRUNCATE audit_auditevent CASCADE",
        ):
            cursor.execute("SAVEPOINT s")
            with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
                cursor.execute(sql)
            cursor.execute("ROLLBACK TO SAVEPOINT s")
        conn.rollback()


def test_ip_side_table_is_anonymised_after_retention_and_erasable():
    actor = uuid.uuid4()
    old = record("identity.logout", request=_request(), actor_user_id=actor)
    # Rows can't be back-dated (L4 trigger), so the job runs "in the future" instead.
    later = timezone.now() + timedelta(days=settings.SECURITY_IP_RETENTION_DAYS, hours=1)
    with freeze_time(later - timedelta(hours=2)):
        new = record("identity.logout", request=_request("198.51.100.4"), actor_user_id=actor)
    assert anonymize_expired_ips(now=later) == 1
    side = AuditEventIP.objects.get(event=old)
    assert side.ip_encrypted is None and side.ip_index is None
    assert side.ip_prefix == "203.0.113.0/24" and side.anonymized_at is not None
    assert AuditEventIP.objects.get(event=new).ip_encrypted is not None
    assert erase_ips_for_actor(actor) == 2
    assert not AuditEventIP.objects.filter(event__in=[old, new]).exists()
    assert AuditEvent.objects.filter(pk__in=[old.pk, new.pk]).count() == 2  # log intact


def test_reveal_returns_ip_and_is_itself_audited(admin):
    event = record("identity.logout", request=_request())
    assert reveal_ip(event, actor=admin.user, request=_request("192.0.2.1")) == "203.0.113.9"
    revealed = AuditEvent.objects.get(action="audit.ip.revealed")
    assert revealed.metadata == {"event_id": str(event.pk)}
    assert revealed.actor_user_id == admin.user.pk


def test_dual_scope_rls_policy_prototype(owner_dsn):
    """Plan §4.6: the Phase 3 dual-scope policies, on a throwaway table, as erp_app."""
    app_dsn = {
        **owner_dsn,
        "user": settings.TEST_APP_DB_USER,
        "password": settings.TEST_APP_DB_PASSWORD,
    }
    a, b = uuid.uuid4(), uuid.uuid4()
    ctx = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    with psycopg.connect(**owner_dsn, autocommit=True) as owner:
        owner.execute("DROP TABLE IF EXISTS rls_proto_role, rls_proto_audit")
        for table, read in (
            ("rls_proto_role", f"tenant_id IS NULL OR tenant_id = {ctx}"),
            ("rls_proto_audit", f"tenant_id IS NOT DISTINCT FROM {ctx}"),
        ):
            owner.execute(f"CREATE TABLE {table} (tenant_id uuid, v text)")
            owner.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            owner.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            owner.execute(f"CREATE POLICY r ON {table} FOR SELECT USING ({read})")
            owner.execute(
                f"CREATE POLICY w ON {table} FOR INSERT "
                f"WITH CHECK (tenant_id IS NOT DISTINCT FROM {ctx})"
            )
            owner.execute(f"GRANT SELECT, INSERT ON {table} TO {settings.TEST_APP_DB_USER}")
    try:
        with psycopg.connect(**app_dsn) as app, app.cursor() as cur:

            def as_tenant(tenant):
                cur.execute(
                    "SELECT set_config('app.tenant_id', %s, true)", [str(tenant) if tenant else ""]
                )

            for table in ("rls_proto_role", "rls_proto_audit"):
                as_tenant(None)
                cur.execute(f"INSERT INTO {table} VALUES (NULL, 'platform')")
                cur.execute("SAVEPOINT s")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(f"INSERT INTO {table} VALUES (%s, 'a-without-ctx')", [a])
                cur.execute("ROLLBACK TO SAVEPOINT s")
                as_tenant(a)
                cur.execute(f"INSERT INTO {table} VALUES (%s, 'a')", [a])
                cur.execute("SAVEPOINT s2")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(f"INSERT INTO {table} VALUES (%s, 'b-from-a')", [b])
                cur.execute("ROLLBACK TO SAVEPOINT s2")
                cur.execute("SAVEPOINT s3")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(f"INSERT INTO {table} VALUES (NULL, 'platform-from-a')")
                cur.execute("ROLLBACK TO SAVEPOINT s3")
                as_tenant(b)
                cur.execute(f"INSERT INTO {table} VALUES (%s, 'b')", [b])

            as_tenant(a)
            cur.execute("SELECT v FROM rls_proto_role ORDER BY v")
            assert [r[0] for r in cur.fetchall()] == ["a", "platform"]  # templates visible
            cur.execute("SELECT v FROM rls_proto_audit ORDER BY v")
            assert [r[0] for r in cur.fetchall()] == ["a"]  # never platform or tenant B
            as_tenant(None)
            cur.execute("SELECT v FROM rls_proto_role")
            assert [r[0] for r in cur.fetchall()] == ["platform"]
            cur.execute("SELECT v FROM rls_proto_audit")
            assert [r[0] for r in cur.fetchall()] == ["platform"]
            app.rollback()
    finally:
        with psycopg.connect(**owner_dsn, autocommit=True) as owner:
            owner.execute("DROP TABLE IF EXISTS rls_proto_role, rls_proto_audit")
