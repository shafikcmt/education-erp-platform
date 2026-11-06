"""Platform audit log (/api/v1/platform/audit-events/; plan §6.8, §6.9, §8).

IPs are masked by default (from the stored prefix). Decrypting one needs ``audit.event.view_ip``
(MFA + step-up) and writes ``audit.ip.revealed``. Exact-IP search uses the blind index (no
decryption) and is also limited to ``audit.event.view_ip`` holders.
"""

from datetime import datetime

from django.db.models import QuerySet
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.services import reveal_ip
from apps.core.ip_privacy import ip_search_index
from apps.core.net import mask_prefix, normalize_ip
from apps.core.pagination import StandardCursorPagination
from apps.identity.api.utils import CsrfProtectedView, get_or_404
from apps.identity.models import User
from apps.rbac.engine import has_perm
from apps.rbac.permissions import HasPermission

TAGS = ["platform-audit"]


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    ip_masked = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "occurred_at",
            "actor_user_id",
            "actor_type",
            "support_session_id",
            "action",
            "outcome",
            "target_type",
            "target_id",
            "metadata",
            "user_agent_summary",
            "request_id",
            "ip_masked",
        )
        read_only_fields = fields

    def get_ip_masked(self, obj: AuditEvent) -> str:
        side = getattr(obj, "ip", None)
        return mask_prefix(side.ip_prefix) if side is not None else ""


class RevealedIpSerializer(serializers.Serializer[None]):
    ip = serializers.CharField()


class AuditCursorPagination(StandardCursorPagination):
    ordering = ("-occurred_at", "-id")  # type: ignore[assignment]  # DRF accepts a tuple


def _parse_dt(value: str, name: str) -> datetime:
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError({name: "Use an ISO-8601 datetime."})
    return parsed


class AuditEventsView(CsrfProtectedView):
    permission_classes = [HasPermission("audit.event.view")]

    @extend_schema(
        tags=TAGS,
        summary="Platform audit events (cursor pagination)",
        parameters=[
            OpenApiParameter("action", OpenApiTypes.STR),
            OpenApiParameter("outcome", OpenApiTypes.STR),
            OpenApiParameter("actor_user_id", OpenApiTypes.UUID),
            OpenApiParameter("target_type", OpenApiTypes.STR),
            OpenApiParameter("target_id", OpenApiTypes.STR),
            OpenApiParameter("occurred_after", OpenApiTypes.DATETIME),
            OpenApiParameter("occurred_before", OpenApiTypes.DATETIME),
            OpenApiParameter("ip", OpenApiTypes.STR, description="Exact IP (needs view_ip)"),
        ],
        responses=AuditEventSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        # Platform scope only: tenant events (Phase 3) are never listed here.
        events: QuerySet[AuditEvent] = AuditEvent.objects.filter(
            tenant_id__isnull=True
        ).select_related("ip")
        params = request.query_params
        for name in ("action", "outcome", "target_type", "target_id"):
            if value := params.get(name):
                events = events.filter(**{name: value[:120]})
        if actor := params.get("actor_user_id"):
            events = events.filter(actor_user_id=get_or_404(User.objects.all(), actor).pk)
        if after := params.get("occurred_after"):
            events = events.filter(occurred_at__gte=_parse_dt(after, "occurred_after"))
        if before := params.get("occurred_before"):
            events = events.filter(occurred_at__lt=_parse_dt(before, "occurred_before"))
        if ip := params.get("ip"):
            if not has_perm(request.user, "audit.event.view_ip", target=request.scope_target):  # type: ignore[attr-defined]
                raise ValidationError({"ip": "Searching by IP requires audit.event.view_ip."})
            if not normalize_ip(ip):
                raise ValidationError({"ip": "Enter a valid IP address."})
            events = events.filter(ip__ip_index=ip_search_index(ip))
        paginator = AuditCursorPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class RevealIpView(CsrfProtectedView):
    permission_classes = [HasPermission("audit.event.view_ip")]

    @extend_schema(
        tags=TAGS,
        summary="Reveal an event's IP (step-up; audited)",
        request=None,
        responses=RevealedIpSerializer,
    )
    def post(self, request: Request, event_id: str) -> Response:
        event = get_or_404(AuditEvent.objects.filter(tenant_id__isnull=True), event_id)
        user = request.user
        assert isinstance(user, User)  # noqa: S101 - permission classes guarantee it
        return Response({"ip": reveal_ip(event, actor=user, request=request._request)})
