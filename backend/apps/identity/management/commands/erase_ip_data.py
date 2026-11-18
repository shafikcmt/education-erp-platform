"""Erase a person's stored IP data on request (ADR-036; procedure in docs/SECURITY.md).

Deletes the encrypted IP rows of every audit event the user performed, clears the IP fields
(including the prefix) of their session records and deletes their IP-derived device
fingerprints. The audit events themselves stay
(immutable); the erasure run is audited.
"""

import uuid
from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.audit.services import erase_ips_for_actor, record
from apps.identity.models import User
from apps.identity.services.maintenance import erase_seen_devices, erase_session_ips


class Command(BaseCommand):
    help = "Erase stored IP data for one user (data-subject request)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--user", required=True, help="User id (UUID)")
        parser.add_argument("--before", help="Only data recorded before this date (YYYY-MM-DD)")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            user_id = uuid.UUID(options["user"])
        except ValueError as exc:
            raise CommandError("--user must be a UUID") from exc
        if not User.objects.filter(pk=user_id).exists():
            raise CommandError("No such user.")
        before = None
        if options.get("before"):
            before = timezone.make_aware(datetime.strptime(options["before"], "%Y-%m-%d"))
        from apps.tenancy.iteration import in_every_scope

        # The subject's events can sit in the platform log and in any tenant's log, each
        # visible only in its own scope (Phase 3 M6): erase in every scope (mechanism I).
        audit_rows = in_every_scope(
            lambda: erase_ips_for_actor(user_id, before=before),
            operation="P13",
            reason="data-subject IP erasure",
        ).rows
        with transaction.atomic():
            session_rows = erase_session_ips(user_id, before=before)
            device_rows = erase_seen_devices(user_id, before=before)
            record(
                "audit.ip.erased",
                target_type="identity.user",
                target_id=user_id,
                metadata={
                    "subject_user_id": str(user_id),
                    "count": audit_rows + session_rows + device_rows,
                },
            )
        self.stdout.write(
            f"erased: {audit_rows} audit IP rows, {session_rows} session records, "
            f"{device_rows} device fingerprints"
        )
