"""Tenant cache and storage keys, and the external-I/O guard (Phase 3 M7; plan §8.4.3, §8.7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.core import mail

from apps.core.ids import new_id
from apps.core.tenancy import TenantContextMissing, tenant_atomic
from apps.core.tenancy.keys import (
    ExternalIOInTenantTransaction,
    tenant_cache_key,
    tenant_storage,
    tenant_storage_key,
)

pytestmark = pytest.mark.django_db
BACKEND = Path(__file__).resolve().parents[1]


def test_cache_keys_are_tenant_prefixed(tenant_factory):
    a = tenant_factory()
    with tenant_atomic(a):
        assert tenant_cache_key("perm", "u1") == f"t:{a.id}:perm:u1"
    assert tenant_cache_key("x", tenant=a.id) == f"t:{a.id}:x"
    with pytest.raises(TenantContextMissing):
        tenant_cache_key("x")
    for bad in ((), ("",), ("a b",), ("a:b",), ("x\n",)):
        with pytest.raises(ValueError, match="Cache key parts"):
            tenant_cache_key(*bad, tenant=a.id)


def test_storage_keys_are_tenant_prefixed_and_safe(tenant_factory):
    a = tenant_factory()
    with tenant_atomic(a):
        assert tenant_storage_key("logos", "main.png") == f"tenants/{a.id}/logos/main.png"
    for bad in ((), ("..",), (".",), ("a/../b",), ("/etc",), ("a\\b",), ("",), ("x\x00",)):
        with pytest.raises(ValueError, match="storage key"):
            tenant_storage_key(*bad, tenant=a.id)
    with pytest.raises(TenantContextMissing):
        tenant_storage_key("x")
    assert tenant_storage_key("x", tenant=str(a.id)).startswith(f"tenants/{a.id}/")
    assert new_id()  # keys never include anything but the tenant id and the parts


def test_no_email_or_storage_io_inside_an_open_tenant_transaction(tenant_factory):
    a = tenant_factory()
    with tenant_atomic(a):
        with pytest.raises(ExternalIOInTenantTransaction):
            mail.send_mail("s", "b", "from@example.test", ["to@example.test"])
        with pytest.raises(ExternalIOInTenantTransaction):
            tenant_storage()
    mail.send_mail("s", "b", "from@example.test", ["to@example.test"])  # outside: fine
    assert len(mail.outbox) == 1
    assert tenant_storage() is not None


def test_tenant_modules_never_build_cache_keys_by_hand():
    """CLAUDE.md §10.7: cache calls in tenant modules go through tenant_cache_key."""
    call = re.compile(r"cache\.(get|set|add|delete|incr|get_many|set_many)\(\s*([^\n]*)")
    offenders = []
    for path in (BACKEND / "apps" / "tenancy").rglob("*.py"):
        if "/tests/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        for match in call.finditer(text):
            following = text[match.end(2) - len(match.group(2)) : match.end(2) + 200]
            if "tenant_cache_key(" not in following.split(")", 1)[0] + following[:120]:
                offenders.append(f"{path.relative_to(BACKEND)}: {match.group(0)[:60]}")
    assert offenders == []
