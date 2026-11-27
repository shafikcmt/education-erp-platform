"""Portal API (Phase 7 M8; ADR-069). Tenant host only, module ``parent_portal``.

``parent_portal.portal.use`` opens the portal; what it shows is decided by the relationship
selectors (children and self only). Anything else answers 404. Read-only.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.models import User
from apps.parent_portal import selectors
from apps.parent_portal.api import serializers as s
from apps.students.models import Student
from apps.tenancy.api.permissions import HasTenantPermission
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["portal"]
USE = "parent_portal.portal.use"


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _child(actor: User, student: Student) -> dict[str, Any]:
    return {
        "id": student.pk, "name": student.name, "number": student.number,
        "institution": student.institution_id, "status": student.status,
        "relation": selectors.relation(actor, student),
        "current": selectors.current_enrollment(student),
    }  # fmt: skip


class PortalView(TenantView):
    module_code = "parent_portal"
    permission_classes = [HasTenantPermission({"GET": USE})]


class ChildrenView(PortalView):
    @extend_schema(
        tags=TAGS, summary="My children (or myself): the portal's switcher",
        responses=s.ChildSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        actor = _actor(request)
        rows = [_child(actor, st) for st in selectors.children(actor)[:50]]
        return Response(s.ChildSerializer(rows, many=True).data)


class ChildDetailView(PortalView):
    @extend_schema(
        tags=TAGS, summary="A child's profile, enrollment and timetable",
        responses=s.ChildDetailSerializer,
    )  # fmt: skip
    def get(self, request: Request, student_id: str) -> Response:
        actor = _actor(request)
        student = selectors.child(actor, student_id)
        if student is None:
            raise NotFound()
        data = _child(actor, student)
        current = data["current"]
        data["date_of_birth"] = student.date_of_birth
        data["timetable"] = selectors.timetable(current["unit"] if current else None)
        return Response(s.ChildDetailSerializer(data).data)
