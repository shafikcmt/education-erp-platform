"""Test-only infrastructure (installed by ``config.settings.test``)."""

from collections.abc import Sequence
from typing import Any

from django.core.mail.backends.locmem import EmailBackend as LocmemEmailBackend

from apps.core.tenancy.keys import assert_no_open_tenant_transaction


class GuardedLocmemEmailBackend(LocmemEmailBackend):
    """The in-memory email backend, refusing to send inside an open tenant transaction
    (Phase 3 plan §8.4.3): emails must leave through ``on_commit`` or a Celery task."""

    def send_messages(self, email_messages: Sequence[Any]) -> int:
        assert_no_open_tenant_transaction("Sending email")
        return int(super().send_messages(email_messages))
