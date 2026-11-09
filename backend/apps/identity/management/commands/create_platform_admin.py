"""Bootstrap the first Super Admin (Phase 2 plan §15, acceptance criterion 1).

Creates an **unactivated** account with no password and the ``super_admin`` platform role, then
sends the activation email. There are no default credentials and nothing secret is printed:
the owner activates through the emailed link (Mailpit in dev), then enrolls MFA.
Refuses to run when an active Super Admin already exists (use the platform console instead).

Runs as the runtime role and never writes the permission catalogue or system roles (O1): it
only checks that the owner-run ``migrate`` bootstrap has synchronized them, and refuses
otherwise.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.identity.services.accounts import create_user
from apps.rbac.seeding import catalog_drift
from apps.rbac.services import active_super_admin_count, bootstrap_super_admin


class Command(BaseCommand):
    help = "Create the first platform Super Admin and email an activation link."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="")
        parser.add_argument("--locale", default="en", choices=["en", "bn"])

    def handle(self, *args: Any, **options: Any) -> None:
        drift = catalog_drift()
        if drift:
            raise CommandError(
                "The permission catalogue / system roles are not synchronized "
                f"({'; '.join(drift[:5])}). Run the owner-level bootstrap first: "
                "`docker compose run --rm migrate`."
            )
        if active_super_admin_count() > 0:
            raise CommandError("A Super Admin already exists; use the platform console.")
        with transaction.atomic():
            user = create_user(
                actor=None,
                email=options["email"],
                display_name=options["name"],
                locale=options["locale"],
                source="bootstrap_command",
            )
            bootstrap_super_admin(user=user, reason="bootstrap: create_platform_admin")
        self.stdout.write(f"Super Admin created ({user.pk}); activation email sent.")
