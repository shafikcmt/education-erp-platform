"""Recompute IP blind indexes after rotating ``IP_INDEX_KEY`` (ADR-036).

Decrypts each stored IP (never printed) and writes ``HMAC(new key, ip)``. Rows already
anonymised (no ciphertext) are skipped.
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.audit.models import AuditEventIP
from apps.core.db_operations import require_owner_role
from apps.core.ip_privacy import ip_search_index, open_ip
from apps.identity.models import SessionRecord


class Command(BaseCommand):
    help = "Rebuild IP blind indexes with the current IP_INDEX_KEY."

    def handle(self, *args: Any, **options: Any) -> None:
        require_owner_role("rebuild_ip_index")
        from apps.tenancy.iteration import in_every_scope

        def rebuild(model: Any) -> int:
            count = 0
            for row in model.objects.select_for_update().filter(ip_encrypted__isnull=False):
                index = ip_search_index(open_ip(row.ip_encrypted))
                model.objects.filter(pk=row.pk).update(ip_index=index)
                count += 1
            return count

        with transaction.atomic():
            updated = rebuild(SessionRecord)
        # Audit IP rows live in the platform scope and in every tenant's scope (M6).
        updated += in_every_scope(
            lambda: rebuild(AuditEventIP), operation="P13", reason="rebuild IP blind indexes"
        ).rows
        self.stdout.write(f"rebuilt {updated} IP indexes")
