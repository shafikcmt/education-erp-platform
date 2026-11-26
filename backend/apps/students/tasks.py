"""Students tenant tasks (Phase 7 M4).

``students.convert_application`` turns an accepted application into a student in the tenant's
own transaction (queued by ``ADMISSIONS_ACCEPTED_HANDLERS`` after the acceptance commits). It is
refused for tenants without the ``students`` module.
"""

from __future__ import annotations

import uuid

from apps.tenancy.tasking import tenant_task


@tenant_task(name="students.convert_application", module="students")
def convert_application(*, tenant_id: uuid.UUID, application_id: str) -> str | None:
    from apps.students.conversion import convert

    student = convert(application_id)
    return str(student.pk) if student is not None else None
