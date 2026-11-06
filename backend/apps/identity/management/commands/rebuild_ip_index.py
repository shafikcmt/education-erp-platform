"""Recompute IP blind indexes after rotating ``IP_INDEX_KEY`` (ADR-036).

Decrypts each stored IP (never printed) and writes ``HMAC(new key, ip)``. Rows already
anonymised (no ciphertext) are skipped.
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.audit.models import AuditEventIP
from apps.core.ip_privacy import ip_search_index, open_ip
from apps.identity.models import SessionRecord


class Command(BaseCommand):
    help = "Rebuild IP blind indexes with the current IP_INDEX_KEY."

    def handle(self, *args: Any, **options: Any) -> None:
        updated = 0
        with transaction.atomic():
            for model in (AuditEventIP, SessionRecord):
                rows = model.objects.select_for_update().filter(ip_encrypted__isnull=False)
                for row in rows:
                    index = ip_search_index(open_ip(row.ip_encrypted))
                    model.objects.filter(pk=row.pk).update(ip_index=index)
                    updated += 1
        self.stdout.write(f"rebuilt {updated} IP indexes")
