"""``manage.py sync_tenant_roles``: platform operation P7 (run after ``seed_roles``)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.tenancy.services.system_roles import sync_all_tenants


class Command(BaseCommand):
    help = "Bring every tenant's read-only system role copies in line with the role templates."

    def handle(self, *args: Any, **options: Any) -> None:
        summary = sync_all_tenants()
        self.stdout.write(
            f"tenant system roles: {summary.tenants} tenants, {summary.changed} changed, "
            f"{summary.failed} failed"
        )
        if summary.failed:
            raise CommandError("Some tenants could not be synced; see the logs.")
