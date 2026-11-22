"""Notification inbox (Phase 5 M6; ADR-059): a member's own notifications, tenant host only."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.notifications_core.models import Notification
from apps.notifications_core.services import mark_read, unread_count
from apps.rbac.permissions import HasPermission
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["notifications"]


class NotificationSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    link = serializers.CharField()
    read_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class InboxSerializer(serializers.Serializer[Any]):
    unread = serializers.IntegerField()
    items = NotificationSerializer(many=True)


class MarkReadSerializer(serializers.Serializer[Any]):
    ids = serializers.ListField(child=serializers.UUIDField(), max_length=200)


def _membership_id(request: Request) -> Any:
    from apps.tenancy.models import Membership

    pk = (
        Membership.objects.filter(user_id=str(request.user.pk)).values_list("pk", flat=True).first()
    )
    if pk is None:
        raise NotFound()
    return pk


class InboxView(TenantView):
    module_code = "notifications_core"
    permission_classes = [HasPermission({"GET": "identity.account.view_own"})]

    @extend_schema(tags=TAGS, summary="My latest notifications", responses=InboxSerializer)
    def get(self, request: Request) -> Response:
        member = _membership_id(request)
        rows = Notification.objects.filter(membership_id=member).order_by("-created_at")[:50]
        data = {"unread": unread_count(member), "items": list(rows)}
        return Response(InboxSerializer(data).data)


class MarkReadView(TenantView):
    module_code = "notifications_core"
    permission_classes = [HasPermission({"POST": "identity.account.view_own"})]

    @extend_schema(
        tags=TAGS,
        summary="Mark my notifications as read",
        request=MarkReadSerializer,
        responses=InboxSerializer,
    )
    def post(self, request: Request) -> Response:
        form = MarkReadSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        member = _membership_id(request)
        mark_read(membership_id=member, notification_ids=form.validated_data["ids"])
        rows = Notification.objects.filter(membership_id=member).order_by("-created_at")[:50]
        return Response(InboxSerializer({"unread": unread_count(member), "items": list(rows)}).data)
