from typing import Any

from django.core.management.base import BaseCommand

from apps.rbac.seeding import seed_roles, sync_permissions


class Command(BaseCommand):
    help = (
        "Sync the permission catalogue, then create/refresh system platform roles and tenant "
        "role templates (idempotent). Owner role only: run by the migrate bootstrap step."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        synced = sync_permissions()
        seeded = seed_roles()
        self.stdout.write(
            f"permissions: {synced.created} created, {synced.updated} updated, "
            f"{synced.deprecated} deprecated"
        )
        self.stdout.write(
            f"system roles: {seeded.roles} seeded ({seeded.roles_created} created, "
            f"{seeded.permissions_added} permissions added, "
            f"{seeded.permissions_removed} removed)"
        )
