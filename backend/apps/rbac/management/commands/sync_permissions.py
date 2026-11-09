from typing import Any

from django.core.management.base import BaseCommand

from apps.rbac.seeding import sync_permissions


class Command(BaseCommand):
    help = "Write module manifest permissions into rbac_permission (idempotent; owner role only)."

    def handle(self, *args: Any, **options: Any) -> None:
        result = sync_permissions()
        self.stdout.write(
            f"permissions: {result.created} created, {result.updated} updated, "
            f"{result.deprecated} deprecated"
        )
