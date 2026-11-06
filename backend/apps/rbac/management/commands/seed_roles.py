from typing import Any

from django.core.management.base import BaseCommand

from apps.rbac.seeding import seed_roles, sync_permissions


class Command(BaseCommand):
    help = "Create/refresh system platform roles and tenant role templates (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:
        sync_permissions()
        self.stdout.write(f"system roles: {seed_roles()} seeded")
